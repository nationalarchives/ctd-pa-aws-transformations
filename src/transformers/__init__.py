"""
Transformer plugin registry.
Maps operation names to transformer classes.
"""
from .base import BaseTransformer
from .specialized.xml_converter import XMLConverterTransformer
from .generic.text_replace import TextReplaceTransformer
from .generic.simple_affix import SimpleAffixTransformer
from .specialized.reference_affix import ReferenceAffixTransformer
from .generic.json_attachment import JsonAttachmentTransformer


# Plugin registry mapping operation names to transformer classes
TRANSFORMER_REGISTRY = {
    'convert': XMLConverterTransformer,
    'replace_text': TextReplaceTransformer,
    'add_affix': SimpleAffixTransformer,
    'reference_affix': ReferenceAffixTransformer,
    'attach_json': JsonAttachmentTransformer,
}


__all__ = [
    'BaseTransformer',
    'TRANSFORMER_REGISTRY',
    'XMLConverterTransformer',
    'TextReplaceTransformer',
    'SimpleAffixTransformer',
    'ReferenceAffixTransformer',
    'JsonAttachmentTransformer',
]
