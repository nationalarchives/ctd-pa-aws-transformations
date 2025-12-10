"""
Generic transformer for attaching JSON data from S3 to a record.
"""
import json
import logging
from typing import Any, Dict, Optional, List

from botocore.exceptions import ClientError
from .base import BaseTransformer
from ..utils import get_by_path, set_by_path


class JsonAttachmentTransformer(BaseTransformer):
    """
    Fetches a JSON object from S3 and attaches it to the data.
    Can also promote fields from the attached JSON to the top-level data.

    Config parameters:
        source_bucket: The S3 bucket to fetch from.
        source_prefix: The S3 prefix (folder) (optional).
        source_id_path: Dot-notation path to the ID field in the data (e.g., "record.iaid").
        attachment_key: The key under which to attach the fetched JSON.
        promote_fields: A list of {'source': 'path', 'destination': 'path'} mappings (optional).
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Fetches, attaches, and promotes JSON data.

        Args:
            data: The JSON data to transform.
            config: Configuration for the attachment process.
            context: Must contain a 'storage' client with an 's3_client' attribute.

        Returns:
            The transformed JSON data.
        """
        source_id_path = config.get('source_id_path')
        attachment_key = config.get('attachment_key')
        storage_client = context.get('storage')

        if not all([source_id_path, attachment_key]):
            raise ValueError("JsonAttachmentTransformer requires 'source_id_path' and 'attachment_key' in config")
        if not storage_client or not hasattr(storage_client, 's3_client'):
            raise ValueError("JsonAttachmentTransformer requires a 'storage' client in context")

        source_id = get_by_path(data, source_id_path)
        if not source_id:
            self.logger.warning(f"Could not find source ID at path '{source_id_path}'")
            return data

        logic = JsonAttachmentLogic(
            s3_client=storage_client.s3_client,
            bucket_name=config.get('source_bucket'),
            prefix=config.get('source_prefix', '')
        )
        
        attached_json = logic.fetch_json(source_id)

        if attached_json:
            # Attach the fetched JSON
            set_by_path(data, attachment_key, attached_json)

            # Promote fields if specified
            promote_fields = config.get('promote_fields', [])
            for field_map in promote_fields:
                source_path = field_map.get('source')
                dest_path = field_map.get('destination')
                if source_path and dest_path:
                    value_to_promote = get_by_path(attached_json, source_path)
                    if value_to_promote is not None:
                        set_by_path(data, dest_path, value_to_promote)
        
        return data


class JsonAttachmentLogic:
    def __init__(self, s3_client: Any, bucket_name: str, prefix: str = ""):
        self.logger = logging.getLogger(__name__)
        self.s3 = s3_client
        self.bucket = bucket_name
        self.prefix = prefix.strip().strip('/') if prefix else ''

    def _get_object_key(self, source_id: str) -> str:
        if not source_id:
            return ''
        key = f"{source_id}.json"
        return f"{self.prefix}/{key}" if self.prefix else key

    def fetch_json(self, source_id: str) -> Optional[Dict[str, Any]]:
        if not self.s3 or not source_id or not self.bucket:
            if not self.bucket:
                self.logger.error("S3 bucket name is not configured.")
            return None
        
        key = self._get_object_key(source_id)
        self.logger.debug(f"Fetching JSON from s3://{self.bucket}/{key}")

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
                self.logger.debug(f"JSON object not found for id '{source_id}' at key '{key}'")
            else:
                self.logger.error(f"S3 ClientError fetching JSON for id '{source_id}': {e}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode JSON for id '{source_id}': {e}")
            return None
        except Exception as e:
            self.logger.error(f"An unexpected error occurred fetching JSON for id '{source_id}': {e}")
            return None
