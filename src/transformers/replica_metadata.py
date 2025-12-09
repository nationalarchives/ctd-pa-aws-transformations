"""
Replica metadata transformer wrapper.
Wraps the existing ReplicaDataTransformer class.
"""
from typing import Any, Dict
from .base import BaseTransformer
from ..transformers import ReplicaDataTransformer


class ReplicaMetadataTransformerWrapper(BaseTransformer):
    """
    Processes replica metadata for archival records.
    
    Config parameters:
        target_fields: List of field paths to transform
        parameters: Additional parameters for replica processing (optional)
    """
    
    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Apply replica metadata transformation.
        
        Args:
            data: JSON dict to transform
            config: Must contain 'target_fields' list
            context: Runtime context (not used)
            
        Returns:
            Transformed JSON dict
        """
        target_fields = config.get('target_fields', [])
        parameters = config.get('parameters', {})
        
        if not target_fields:
            raise ValueError("ReplicaMetadataTransformerWrapper requires 'target_fields' in config")
        
        # Instantiate the existing transformer
        transformer = ReplicaDataTransformer(target_fields=target_fields, **parameters)
        
        # Call the transform method
        return transformer.transform(data)
