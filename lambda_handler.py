"""
Task-agnostic Lambda handler for Step Functions orchestrated transformations.
This handler is a lightweight entry point that delegates to the LambdaOrchestrator.
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

from src.orchestration import LambdaOrchestrator
from src.storage import StorageClient

# Configure logger
log_level = os.getenv("CTD_LOG_LEVEL", "INFO").upper()
numeric_level = getattr(logging, log_level, logging.INFO)
logging.basicConfig(
    level=numeric_level,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize clients
storage_client = StorageClient()
orchestrator = LambdaOrchestrator(storage_client)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler that delegates to the LambdaOrchestrator.
    
    Args:
        event: Event from Step Functions.
        context: Lambda context object.
        
    Returns:
        A dictionary with the result of the step execution.
    """
    logger.info("Lambda handler invoked with event: %s", json.dumps(event, default=str))
    
    try:
        result = orchestrator.run_step(event)
        logger.info("Lambda handler completed successfully.")
        return result
        
    except Exception as e:
        logger.exception("Error during lambda execution")
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
            },
            "2": {
                "operation": "replace_text",
                "match": "\\n",
                "replace": "<p>",
                "target_fields": ["record.scopeContent.description"]
            },
            "3": {
                "operation": "add_affix",
                "prefix": "DEPT-",
                "target_fields": ["record.formerReferenceDep"]
            },
            "4": {
                "operation": "attach_json",
                "source_bucket": "test-bucket",
                "source_prefix": "replica_metadata",
                "source_id_path": "record.iaid",
                "attachment_key": "replica",
                "promote_fields": [
                    {"source": "replicaId", "destination": "record.replicaId"}
                ]
            }
        },
        "execution_id": "local-test-exec-123"
    }
    
    class MockContext:
        function_name = "test-function"
        function_version = "1"
        aws_request_id = "local-test-req-123"
        memory_limit_in_mb = 1024
        
        def get_remaining_time_in_millis(self):
            return 300000  # 5 minutes
    
    # You would need to mock storage interactions for a local run here
    # For example, create dummy input files in a 'local-s3-data' directory
    
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))

