"""
XML to JSON converter transformer wrapper.
Wraps the existing convert_to_json function.
"""
from typing import Any, Dict
from .base import BaseTransformer
from ..transformers import convert_to_json


class XMLConverterTransformer(BaseTransformer):
    """
    Converts XML data to JSON format.
    
    Config parameters:
        None required - uses default conversion logic
    """
    
    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Convert XML string to JSON dict.
        
        Args:
            data: XML string to convert
            config: Not used for this transformer
            context: Runtime context (not used)
            
        Returns:
            Dict representing the JSON conversion of the XML
        """
        if isinstance(data, str):
            # convert_to_json expects XML string
            return convert_to_json(data)
        else:
            raise ValueError(f"XMLConverterTransformer expects string input, got {type(data)}")
