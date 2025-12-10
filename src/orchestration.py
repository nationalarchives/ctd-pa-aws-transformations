"""
Orchestrates the execution of a single transformation step within the Lambda function.
"""
import os
import json
import logging
import io
import tarfile
import time
from typing import Dict, Any, Optional
from pathlib import Path

from main_transformer import TransformerOrchestrator
from src.storage import StorageClient, check_step_completed, load_json_from_prefix
from src.utils import load_transfer_register, filter_new_records, update_transfer_register_with_records

logger = logging.getLogger(__name__)


class LambdaOrchestrator:
    """
    Handles the logic for a single Step Functions transformation step.
    Includes transfer register checking and tarball creation.
    """
    def __init__(self, storage_client: StorageClient, transfer_register_key: Optional[str] = None):
        self.storage_client = storage_client
        self.transformer_orchestrator = TransformerOrchestrator()
        self.transfer_register_key = transfer_register_key or os.getenv('TRANSFER_REGISTER_KEY', 'registers/uploaded_records_transfer_register.json')
        self._transfer_register = None

    def run_step(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a single transformation step based on the event payload.

        Args:
            event: The event from Step Functions.

        Returns:
            A dictionary with the result of the step execution.
        """
        logger.info("Orchestrator running step")
        
        # Extract event parameters
        bucket = event['bucket']
        initial_key = event['key']
        transformation_config = event['transformation_config']
        transformation_index = event['transformation_index']
        execution_id = event['execution_id']
        
        step_key = str(transformation_index)
        if step_key not in transformation_config:
            raise ValueError(f"No configuration found for transformation step {step_key}")
        
        config = transformation_config[step_key]
        operation = config.get('operation', 'unknown')
        
        logger.info(
            "Executing step %d (operation: %s) for execution %s",
            transformation_index,
            operation,
            execution_id
        )
        
        # Check transfer register on first step to prevent duplicate processing
        if transformation_index == 1:
            skip_reason = self._check_transfer_register(bucket, initial_key, event)
            if skip_reason:
                logger.info("Skipping processing: %s", skip_reason)
                return {
                    "statusCode": 200,
                    "execution_id": execution_id,
                    "transformation_index": transformation_index,
                    "operation": operation,
                    "skipped": True,
                    "reason": skip_reason,
                    "message": f"Record already processed: {skip_reason}"
                }
        
        # Determine and load input data
        input_data = self._load_input_data(
            bucket, initial_key, execution_id, transformation_index
        )

        # Execute transformation
        transformation_context = {
            'storage_client': self.storage_client,
            'bucket': bucket,
            'execution_id': execution_id,
            'step': transformation_index
        }
        
        logger.info("Executing transformation with operation: %s", operation)
        output_data = self.transformer_orchestrator.transform(
            input_data, config, transformation_context
        )
        logger.info("Transformation completed successfully")
        
        # Store output data
        output_key, success_marker = self._store_output_data(
            bucket, initial_key, execution_id, transformation_index, output_data
        )
        
        logger.info("Step %d completed successfully", transformation_index)
        
        return {
            "statusCode": 200,
            "execution_id": execution_id,
            "transformation_index": transformation_index,
            "operation": operation,
            "output_key": output_key,
            "success_marker": success_marker,
            "message": f"Step {transformation_index} completed successfully"
        }

    def _check_transfer_register(self, bucket: str, initial_key: str, event: Dict[str, Any]) -> Optional[str]:
        """
        Check if records from this file have already been processed.
        Returns None if processing should continue, or a reason string if it should be skipped.
        """
        try:
            # Load transfer register from S3
            logger.info("Loading transfer register from %s", self.transfer_register_key)
            self._transfer_register = load_transfer_register(
                Path(self.transfer_register_key).name,
                self.storage_client.s3_client,
                bucket,
                str(Path(self.transfer_register_key).parent),
                logger
            )
            
            num_existing = len(self._transfer_register.get('records', {}))
            logger.info("Loaded transfer register with %d existing records", num_existing)
            
            # Extract record ID from the event or input file name
            # This will depend on your data structure - adjust as needed
            record_id = Path(initial_key).stem
            
            existing_records = self._transfer_register.get('records', {})
            if record_id in existing_records:
                return f"Record '{record_id}' already in transfer register"
            
            return None
            
        except Exception as e:
            logger.warning("Could not check transfer register: %s. Proceeding with processing.", e)
            return None
    
    def _load_input_data(self, bucket: str, initial_key: str, execution_id: str, transformation_index: int) -> Any:
        """Loads input data from the initial key or the previous step's output."""
        if transformation_index == 1:
            # First step: read from initial input location
            input_key = initial_key
            logger.info("Step 1: Reading from initial input: %s", input_key)
            
            input_bytes = self.storage_client.get_object(bucket, input_key)
            input_data = input_bytes.decode('utf-8')
            logger.info("Loaded XML input (%d bytes)", len(input_data))
            return input_data
        else:
            # Subsequent steps: read from previous step's output
            previous_step = transformation_index - 1
            input_prefix = f"processed/{execution_id}/step_{previous_step}/"
            
            logger.info("Step %d: Checking previous step %d at %s", 
                       transformation_index, previous_step, input_prefix)
            
            if not check_step_completed(self.storage_client, bucket, input_prefix):
                raise RuntimeError(f"Previous step {previous_step} has not completed.")
            
            input_data = load_json_from_prefix(self.storage_client, bucket, input_prefix)
            if not input_data:
                raise ValueError(f"No output found from step {previous_step}")
            
            logger.info("Loaded JSON from step %d", previous_step)
            return input_data

    def _store_output_data(self, bucket: str, initial_key: str, execution_id: str, transformation_index: int, output_data: Any) -> tuple:
        """Stores the output data and a success marker."""
        filename = os.path.splitext(os.path.basename(initial_key))[0]
        output_prefix = f"processed/{execution_id}/step_{transformation_index}/"
        output_key = f"{output_prefix}{filename}.json"
        success_marker = f"{output_prefix}_SUCCESS"
        
        logger.info("Writing output to: %s", output_key)
        self.storage_client.put_object(
            bucket,
            output_key,
            json.dumps(output_data, indent=2),
            'application/json'
        )
        
        logger.info("Writing success marker: %s", success_marker)
        self.storage_client.put_object(
            bucket,
            success_marker,
            '',
            'text/plain'
        )
        return output_key, success_marker

    def create_tarball(self, bucket: str, execution_id: str, final_step: int, tree_name: str, 
                       level_grouping: Optional[Dict[str, list]] = None) -> Dict[str, Any]:
        """
        Creates tarball archives from the final transformation output.
        
        Args:
            bucket: S3 bucket name
            execution_id: Unique execution identifier
            final_step: The final transformation step number
            tree_name: Name for the tarball files
            level_grouping: Optional dict mapping level names to lists of (filename, json_data) tuples
                           If None, will load all files from final step output
        
        Returns:
            Dict with status and tarball information
        """
        logger.info("Creating tarballs for execution %s", execution_id)
        
        # If no grouping provided, load all JSON files from the final step
        if level_grouping is None:
            level_grouping = self._load_final_output(bucket, execution_id, final_step)
        
        if not level_grouping:
            logger.warning("No data to create tarballs")
            return {"status": "skipped", "message": "No data for tarball creation"}
        
        tarball_info = []
        BATCH_SIZE = 10000  # Max files per tarball
        
        for level_name, files in level_grouping.items():
            total_files = len(files)
            logger.info("Level '%s' has %d files; batching into %d-file chunks",
                       level_name, total_files, BATCH_SIZE)
            
            # Create chunks
            chunks = [files[i:i + BATCH_SIZE] for i in range(0, total_files, BATCH_SIZE)]
            cumulative_count = 0
            
            for chunk_index, chunk in enumerate(chunks, start=1):
                cumulative_count += len(chunk)
                tarball_name = f"{tree_name}_{level_name}_{cumulative_count}.tar.gz"
                
                buf = io.BytesIO()
                try:
                    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                        for filename, json_data in chunk:
                            safe_name = f"{Path(filename).name}.json"
                            json_bytes = json.dumps(json_data, ensure_ascii=False, indent=2).encode("utf-8")
                            ti = tarfile.TarInfo(name=safe_name)
                            ti.size = len(json_bytes)
                            ti.mtime = int(time.time())
                            tar.addfile(ti, fileobj=io.BytesIO(json_bytes))
                    
                    buf.seek(0)
                    tar_bytes = buf.getvalue()
                    file_count = len(chunk)
                    logger.info("Created tarball: %s (%d files, %d bytes)",
                               tarball_name, file_count, len(tar_bytes))
                    
                    # Upload tarball to S3
                    output_key = f"tarballs/{execution_id}/{tarball_name}"
                    self.storage_client.put_object(
                        bucket,
                        output_key,
                        tar_bytes,
                        'application/gzip'
                    )
                    
                    tarball_info.append({
                        "name": tarball_name,
                        "level": level_name,
                        "file_count": file_count,
                        "size_bytes": len(tar_bytes),
                        "s3_key": output_key
                    })
                    
                except Exception as e:
                    logger.exception("Error creating tarball for level %s (chunk %d)", level_name, chunk_index)
                    return {
                        "status": "error",
                        "message": f"Failed to create tarball for level {level_name}: {str(e)}"
                    }
        
        # Update transfer register with successfully processed records
        if self._transfer_register is not None:
            try:
                # Extract all record IDs from the processed files
                all_records = {}
                for level_name, files in level_grouping.items():
                    for filename, json_data in files:
                        record_id = Path(filename).stem
                        all_records[record_id] = json_data
                
                self._transfer_register = update_transfer_register_with_records(
                    self._transfer_register,
                    all_records,
                    tree_name,
                    bucket,
                    str(Path(self.transfer_register_key).parent),
                    logger
                )
                
                # Save updated transfer register
                register_filename = Path(self.transfer_register_key).name
                from src.utils import save_transfer_register
                save_transfer_register(
                    register_filename,
                    self.storage_client.s3_client,
                    bucket,
                    str(Path(self.transfer_register_key).parent),
                    self._transfer_register,
                    logger
                )
                logger.info("Updated transfer register with %d total records", 
                           len(self._transfer_register.get('records', {})))
                
            except Exception as e:
                logger.warning("Failed to update transfer register: %s", e)
        
        return {
            "status": "success",
            "tarballs_created": len(tarball_info),
            "tarballs": tarball_info
        }
    
    def _load_final_output(self, bucket: str, execution_id: str, final_step: int) -> Dict[str, list]:
        """Load all JSON files from the final transformation step output."""
        output_prefix = f"processed/{execution_id}/step_{final_step}/"
        
        try:
            # This is a simplified implementation - you may need to adjust based on your storage structure
            json_data = load_json_from_prefix(self.storage_client, bucket, output_prefix)
            
            # Group by level if your data has level information
            # For now, return a single "default" level
            if isinstance(json_data, dict):
                filename = Path(output_prefix).stem
                return {"default": [(filename, json_data)]}
            elif isinstance(json_data, list):
                return {"default": [(f"record_{i}", item) for i, item in enumerate(json_data)]}
            else:
                return {}
        except Exception as e:
            logger.warning("Failed to load final output: %s", e)
            return {}
