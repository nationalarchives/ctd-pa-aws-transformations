"""
Replica metadata transformer.
"""
import json
import logging
from typing import Any, Dict, Optional

from botocore.exceptions import ClientError
from .base import BaseTransformer


class ReplicaMetadataTransformer(BaseTransformer):
    """
    Enriches a record with replica metadata from an S3 object.

    Config parameters:
        bucket: The S3 bucket where replica metadata is stored.
        prefix: The S3 prefix (folder) within the bucket (optional, defaults to 'replica').
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Fetches replica metadata and attaches it to the record.

        Args:
            data: The JSON record to transform (expects {"record": {"iaid": ...}}).
            config: Must contain 'bucket'. Can contain 'prefix'.
            context: Must contain 'storage' client with an 's3_client' attribute.

        Returns:
            The transformed JSON record, or the original if metadata is not found.
        """
        if 'record' not in data or 'iaid' not in data.get('record', {}):
            self.logger.warning("Input data does not have the expected structure with 'record' and 'iaid'.")
            return data

        iaid = data['record']['iaid']
        bucket = config.get('bucket')
        prefix = config.get('prefix', 'replica')
        storage_client = context.get('storage')

        if not bucket:
            raise ValueError("ReplicaMetadataTransformer requires 'bucket' in config")
        if not storage_client or not hasattr(storage_client, 's3_client'):
            raise ValueError("ReplicaMetadataTransformer requires a 'storage' client in context")

        s3_client = storage_client.s3_client
        
        logic = ReplicaMetadataLogic(s3_client, bucket, prefix)
        metadata = logic.fetch_metadata(iaid)

        if metadata:
            data['replica'] = metadata
            if 'replicaId' in metadata:
                data['record']['replicaId'] = metadata['replicaId']
        
        return data


class ReplicaMetadataLogic:
    def __init__(self, s3_client: Any, bucket_name: str, prefix: str = "replica"):
        self.logger = logging.getLogger(__name__)
        self.s3 = s3_client
        self.bucket = bucket_name
        self.prefix = prefix.strip().strip('/') if prefix else ''

    def _get_object_key(self, iaid: str) -> str:
        if not iaid:
            return ''
        if self.prefix:
            return f"{self.prefix}/{iaid}.json"
        return f"{iaid}.json"

    def fetch_metadata(self, iaid: str) -> Optional[Dict[str, Any]]:
        if not self.s3 or not iaid:
            return None
        
        key = self._get_object_key(iaid)
        self.logger.debug(f"Fetching replica metadata from s3://{self.bucket}/{key}")

        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            body = response.get('Body')
            if not body:
                return None
            
            raw_content = body.read()
            if not raw_content:
                return None
                
            return json.loads(raw_content.decode('utf-8'))

        except ClientError as e:
            if e.response['Error']['Code'] in ("NoSuchKey", "404"):
                self.logger.debug(f"Replica metadata not found for iaid '{iaid}' at key '{key}'")
            else:
                self.logger.error(f"S3 ClientError fetching replica metadata for '{iaid}': {e}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode JSON for replica metadata '{iaid}': {e}")
            return None
        except Exception as e:
            self.logger.error(f"An unexpected error occurred fetching replica metadata for '{iaid}': {e}")
            return None
