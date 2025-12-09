"""
Y-naming transformer wrapper.
Wraps the existing YNamingTransformer class.
"""
from typing import Any, Dict
from .base import BaseTransformer
from ..transformers import YNamingTransformer


class YNamingTransformerWrapper(BaseTransformer):
    """
    Applies Y-naming conventions to specified fields.
    
    Config parameters:
        target_fields: List of field paths to transform
        parameters: Additional parameters for Y-naming logic (optional)
    """
    
    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Apply Y-naming transformation.
        
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
            raise ValueError("YNamingTransformerWrapper requires 'target_fields' in config")
        
        # Instantiate the existing transformer
        transformer = YNamingTransformer(target_fields=target_fields, **parameters)
        
        # Call the transform method
        return transformer.transform(data)
