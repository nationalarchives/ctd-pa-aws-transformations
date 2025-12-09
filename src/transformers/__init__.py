"""
Transformer plugin registry.
Maps operation names to transformer classes.
"""
from .base import BaseTransformer
from .xml_converter import XMLConverterTransformer
from .newline_to_p import NewlineToPTransformer
from .y_naming import YNamingTransformer
from .replica_metadata import ReplicaMetadataTransformer


# Plugin registry mapping operation names to transformer classes
TRANSFORMER_REGISTRY = {
    'convert': XMLConverterTransformer,
    'newline_to_p': NewlineToPTransformer,
    'y_naming': YNamingTransformer,
    'replica_metadata': ReplicaMetadataTransformer,
}


__all__ = [
    'BaseTransformer',
    'TRANSFORMER_REGISTRY',
    'XMLConverterTransformer',
    'NewlineToPTransformer',
    'YNamingTransformer',
    'ReplicaMetadataTransformer',
]
