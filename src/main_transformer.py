"""
Generic transformer orchestrator.
Routes transformation requests to appropriate transformer plugins.
"""
import json
from typing import Any, Dict
from src.transformers import TRANSFORMER_REGISTRY


class TransformerOrchestrator:
    """
    Orchestrator that delegates transformations to registered transformer plugins.
    
    This class remains lightweight (~50 lines) by delegating to the plugin registry.
    Each operation is handled by a specific transformer wrapper class.
    """
    
    def __init__(self):
        """Initialize the generic transformer with the plugin registry."""
        self.registry = TRANSFORMER_REGISTRY
    
    def transform(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute a transformation based on the operation specified in config.
        
        Args:
            data: Input data to transform (dict, list, or str)
            config: Transformation configuration containing:
                - operation: Name of the operation (must be in TRANSFORMER_REGISTRY)
                - target_fields: List of field paths to transform (optional)
                - parameters: Additional operation-specific parameters (optional)
            context: Runtime context (s3_client, bucket, execution_id, etc.)
            
        Returns:
            Transformed data
            
        Raises:
            ValueError: If operation is not specified or not found in registry
        """
        operation = config.get('operation')
        
        if not operation:
            raise ValueError("Configuration must specify 'operation' field")
        
        # Get the transformer class from registry
        transformer_class = self.registry.get(operation)
        
        if not transformer_class:
            available_ops = ', '.join(self.registry.keys())
            raise ValueError(
                f"Unknown operation '{operation}'. "
                f"Available operations: {available_ops}"
            )
        
        # Instantiate and execute the transformer
        transformer = transformer_class()
        return transformer.execute(data, config, context)
    
    def list_operations(self):
        """Return list of available operations."""
        return list(self.registry.keys())
