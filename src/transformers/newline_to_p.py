"""
Newline to paragraph transformer wrapper.
Wraps the existing NewlineToPTransformer class.
"""
from typing import Any, Dict
from .base import BaseTransformer
from ..transformers import NewlineToPTransformer


class NewlineToPTransformerWrapper(BaseTransformer):
    """
    Replaces newlines with <p> tags in specified fields.
    
    Config parameters:
        target_fields: List of field paths to transform (e.g., ["scopecontent.p"])
    """
    
    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Apply newline to paragraph transformation.
        
        Args:
            data: JSON dict to transform
            config: Must contain 'target_fields' list
            context: Runtime context (not used)
            
        Returns:
            Transformed JSON dict
        """
        target_fields = config.get('target_fields', [])
        
        if not target_fields:
            raise ValueError("NewlineToPTransformerWrapper requires 'target_fields' in config")
        
        # Instantiate the existing transformer with target fields
        transformer = NewlineToPTransformer(target_fields=target_fields)
        
        # Call the transform method
        return transformer.transform(data)
