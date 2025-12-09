"""
Task-agnostic Lambda handler for Step Functions orchestrated transformations.
Handles a single transformation step per invocation.

Expected Step Functions Event Structure:
{
    "bucket": "ctd-pa-elt-data-processing-bucket",
    "key": "xml_input/file.xml",
    "transformation_index": 1,
    "transformation_config": {
        "1": {
            "operation": "convert",
            "target_fields": [],
            "parameters": {}
        },
        "2": {
            "operation": "newline_to_p",
            "target_fields": ["scopecontent.p"],
            "parameters": {}
        },
        "3": {
            "operation": "y_naming",
            "target_fields": ["department"],
            "parameters": {}
        }
    },
    "execution_id": "step-functions-execution-id"
}
"""

import json
import os
import logging
import sys
from pathlib import Path
from typing import Dict, Any

# Add the src directory to path for imports
repo_root = Path(__file__).resolve().parent
sys.path.insert(0, str(repo_root))

from src.generic_transformer import TransformerOrchestrator
from src.storage import StorageClient, check_step_completed, load_json_from_prefix

# Configure logger
log_level = os.getenv("CTD_LOG_LEVEL", "INFO").upper()
numeric_level = getattr(logging, log_level, logging.INFO)
logging.basicConfig(
    level=numeric_level,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize storage client (auto-detects local vs S3)
storage_client = StorageClient()


def transformations(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for task-agnostic transformation execution.
    
    Args:
        event: Event from Step Functions containing:
            - bucket: S3 bucket name
            - key: S3 object key (initial XML file path)
            - transformation_index: Current transformation step to execute
            - transformation_config: Configuration for all transformations
            - execution_id: Step Functions execution ID
        context: Lambda context object
        
    Returns:
        dict: Result containing statusCode, execution_id, output_key, and success_marker
    """
    logger.info("Lambda handler invoked")
    logger.info("Event: %s", json.dumps(event, default=str))
    
    try:
        # Extract event parameters
        bucket = event['bucket']
        initial_key = event['key']
        transformation_config = event['transformation_config']
        transformation_index = event['transformation_index']
        execution_id = event['execution_id']
        
        # Convert index to string for config lookup
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
        
        # Determine input location
        if transformation_index == 1:
            # First step: read from initial input location
            input_key = initial_key
            logger.info("Step 1: Reading from initial input: %s", input_key)
            
            # Read XML from storage
            input_bytes = storage_client.get_object(bucket, input_key)
            input_data = input_bytes.decode('utf-8')
            logger.info("Loaded XML input (%d bytes)", len(input_data))
            
        else:
            # Subsequent steps: read from previous step's output
            previous_step = transformation_index - 1
            input_prefix = f"processed/{execution_id}/step_{previous_step}/"
            
            logger.info("Step %d: Checking previous step %d at %s", 
                       transformation_index, previous_step, input_prefix)
            
            # Check if previous step completed
            if not check_step_completed(storage_client, bucket, input_prefix):
                logger.warning("Step %d not yet complete", previous_step)
                return {
                    "statusCode": 202,  # Accepted but not ready
                    "message": f"Waiting for step {previous_step} to complete",
                    "execution_id": execution_id,
                    "transformation_index": transformation_index
                }
            
            # Load JSON from previous step
            input_data = load_json_from_prefix(storage_client, bucket, input_prefix)
            if not input_data:
                raise ValueError(f"No output found from step {previous_step}")
            
            logger.info("Loaded JSON from step %d", previous_step)
        
        # Execute transformation
        transformer = TransformerOrchestrator()
        transformation_context = {
            'storage_client': storage_client,
            'bucket': bucket,
            'execution_id': execution_id,
            'step': transformation_index
        }
        
        logger.info("Executing transformation with operation: %s", operation)
        output_data = transformer.transform(input_data, config, transformation_context)
        logger.info("Transformation completed successfully")
        
        # Determine output location
        filename = os.path.splitext(os.path.basename(initial_key))[0]
        output_prefix = f"processed/{execution_id}/step_{transformation_index}/"
        output_key = f"{output_prefix}{filename}.json"
        success_marker = f"{output_prefix}_SUCCESS"
        
        # Write output to storage
        logger.info("Writing output to: %s", output_key)
        storage_client.put_object(
            bucket,
            output_key,
            json.dumps(output_data, indent=2),
            'application/json'
        )
        
        # Write success marker
        logger.info("Writing success marker: %s", success_marker)
        storage_client.put_object(
            bucket,
            success_marker,
            '',
            'text/plain'
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
        
    except Exception as e:
        logger.exception("Error in transformation")
        return {
            "statusCode": 500,
            "error": str(e),
            "error_type": type(e).__name__,
            "execution_id": event.get('execution_id'),
            "transformation_index": event.get('transformation_index')
        }


# For local testing
if __name__ == "__main__":
    # Sample test event
    test_event = {
        "bucket": "test-bucket",
        "key": "xml_input/test.xml",
        "transformation_index": 1,
        "transformation_config": {
            "1": {
                "operation": "convert",
                "target_fields": [],
                "parameters": {}
            },
            "2": {
                "operation": "newline_to_p",
                "target_fields": ["scopecontent.p"],
                "parameters": {}
            },
            "3": {
                "operation": "y_naming",
                "target_fields": ["department"],
                "parameters": {}
            }
        },
        "execution_id": "test-execution-123"
    }
    
    class MockContext:
        function_name = "test-function"
        function_version = "1"
        aws_request_id = "test-request-123"
        memory_limit_in_mb = 1024
        
        def get_remaining_time_in_millis(self):
            return 300000  # 5 minutes
    
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))
