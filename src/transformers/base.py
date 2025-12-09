"""
Base transformer interface for plugin registry pattern.
All transformer wrappers must inherit from this base class.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTransformer(ABC):
    """
    Abstract base class for all transformers.
    
    Each transformer plugin must implement the execute method which takes:
    - data: The input data to transform (dict, list, or str)
    - config: Configuration parameters specific to this transformation
    - context: Additional context (S3 client, execution_id, etc.)
    
    Returns:
        The transformed data in the same or compatible format
    """
    
    @abstractmethod
    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute the transformation.
        
        Args:
            data: Input data to transform
            config: Transformation-specific configuration
            context: Runtime context (s3_client, bucket, execution_id, etc.)
            
        Returns:
            Transformed data
        """
        pass
