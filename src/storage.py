"""
Storage abstraction layer - works with both S3 and local filesystem.
Allows Lambda to run locally for testing.
"""
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
import logging
import boto3
import tempfile

logger = logging.getLogger(__name__)


class StorageClient:
    """Abstraction for S3 or local filesystem storage."""
    
    def __init__(self):
        """Initialize storage client - auto-detects LocalStack, local filesystem, or AWS S3."""
        
        # Check for LocalStack endpoint
        endpoint_url = os.getenv('AWS_ENDPOINT_URL') or os.getenv('LOCALSTACK_ENDPOINT')

        # Determine the platform-agnostic path for local testing
        local_s3_root = Path(tempfile.gettempdir()) / 'local-s3-data'
        
        if endpoint_url:
            # LocalStack mode
            logger.info("Running in LOCALSTACK mode - endpoint: %s", endpoint_url)
            self.s3_client = boto3.client(
                's3',
                endpoint_url=endpoint_url,
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID', 'test'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY', 'test'),
                region_name=os.getenv('AWS_DEFAULT_REGION', 'eu-west-2')
            )
            self.local_mode = False
            self.local_root = None
        elif os.path.exists(local_s3_root):
            # Local filesystem mode
            logger.info("Running in LOCAL FILESYSTEM mode - using %s", local_s3_root)
            print(f"\n[LOCAL MODE] Your data folder is located at: {local_s3_root}\n")
            self.local_mode = True
            self.local_root = local_s3_root
            self.s3_client = None
        else:
            # AWS mode
            logger.info("Running in AWS mode - using S3")
            self.s3_client = boto3.client('s3')
            self.local_mode = False
            self.local_root = None
    
    def get_object(self, bucket: str, key: str) -> bytes:
        """
        Read object from storage.
        
        Args:
            bucket: Bucket name
            key: Object key
            
        Returns:
            bytes: Object content
        """
        if self.local_mode:
            file_path = self.local_root / bucket / key
            logger.info("Reading from local: %s", file_path)
            
            if not file_path.exists():
                raise FileNotFoundError(f"Local file not found: {file_path}")
            
            return file_path.read_bytes()
        else:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return response['Body'].read()
    
    def put_object(self, bucket: str, key: str, body: str, content_type: str = 'application/json'):
        """
        Write object to storage.
        
        Args:
            bucket: Bucket name
            key: Object key
            body: Content to write
            content_type: MIME type
        """
        if self.local_mode:
            file_path = self.local_root / bucket / key
            logger.info("Writing to local: %s", file_path)
            
            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content
            if isinstance(body, str):
                file_path.write_text(body, encoding='utf-8')
            else:
                file_path.write_bytes(body)
        else:
            self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                ContentType=content_type
            )
    
    def head_object(self, bucket: str, key: str) -> bool:
        """
        Check if object exists.
        
        Args:
            bucket: Bucket name
            key: Object key
            
        Returns:
            bool: True if exists, False otherwise
        """
        if self.local_mode:
            file_path = self.local_root / bucket / key
            return file_path.exists()
        else:
            try:
                self.s3_client.head_object(Bucket=bucket, Key=key)
                return True
            except:
                return False
    
    def list_objects(self, bucket: str, prefix: str) -> list:
        """
        List objects with prefix.
        
        Args:
            bucket: Bucket name
            prefix: Key prefix
            
        Returns:
            list: List of object keys
        """
        if self.local_mode:
            dir_path = self.local_root / bucket / prefix
            if not dir_path.exists():
                return []
            
            # Return relative paths from bucket root
            bucket_root = self.local_root / bucket
            return [
                str(p.relative_to(bucket_root))
                for p in dir_path.rglob('*')
                if p.is_file()
            ]
        else:
            response = self.s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            if 'Contents' not in response:
                return []
            return [obj['Key'] for obj in response['Contents']]


def check_step_completed(storage: StorageClient, bucket: str, prefix: str) -> bool:
    """
    Check if a transformation step has completed by looking for _SUCCESS marker.
    
    Args:
        storage: Storage client
        bucket: S3 bucket name
        prefix: Step prefix (e.g., "processed/exec-123/step_1/")
        
    Returns:
        True if _SUCCESS marker exists, False otherwise
    """
    success_marker = f"{prefix}_SUCCESS"
    return storage.head_object(bucket, success_marker)


def load_json_from_prefix(storage: StorageClient, bucket: str, prefix: str) -> Optional[Dict[str, Any]]:
    """
    Load JSON output from a step's output folder.
    
    Args:
        storage: Storage client
        bucket: S3 bucket name
        prefix: Step prefix (e.g., "processed/exec-123/step_1/")
        
    Returns:
        Parsed JSON data or None if not found
    """
    try:
        # List objects in the prefix
        keys = storage.list_objects(bucket, prefix)
        
        if not keys:
            return None
        
        # Find the JSON file (not _SUCCESS marker)
        for key in keys:
            if key.endswith('.json') and not key.endswith('_SUCCESS'):
                # Read and parse the JSON file
                content = storage.get_object(bucket, key)
                return json.loads(content.decode('utf-8'))
        
        return None
        
    except Exception as e:
        logger.exception("Error loading JSON from %s", prefix)
        return None
