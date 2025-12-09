"""
Transformer plugin registry.
Maps operation names to transformer classes.
"""
from .base import BaseTransformer
from .xml_converter import XMLConverterTransformer
from .newline_to_p import NewlineToPTransformerWrapper
from .y_naming import YNamingTransformerWrapper
from .replica_metadata import ReplicaMetadataTransformerWrapper


# Plugin registry mapping operation names to transformer classes
TRANSFORMER_REGISTRY = {
    'convert': XMLConverterTransformer,
    'newline_to_p': NewlineToPTransformerWrapper,
    'y_naming': YNamingTransformerWrapper,
    'replica_metadata': ReplicaMetadataTransformerWrapper,
}


__all__ = [
    'BaseTransformer',
    'TRANSFORMER_REGISTRY',
    'XMLConverterTransformer',
    'NewlineToPTransformerWrapper',
    'YNamingTransformerWrapper',
    'ReplicaMetadataTransformerWrapper',
]
