"""
Generic affix transformer to add prefixes or suffixes to strings.
"""
import copy
import logging
from typing import Any, Dict, Optional, List

from .base import BaseTransformer


class SimpleAffixTransformer(BaseTransformer):
    """
    Adds a simple prefix and/or suffix to string fields without validation.
    If `target_fields` is not provided, it applies to all string values.
    
    Use this for straightforward text prepending/appending.
    For reference-based affixing with validation (like Y-naming), use ReferenceAffixTransformer.
    
    Config parameters:
        prefix: String to prepend (optional).
        suffix: String to append (optional).
        target_fields: List of field paths to transform (optional).
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Apply simple affix transformation.
        
        Args:
            data: JSON dict to transform.
            config: May contain 'prefix', 'suffix', 'target_fields'.
            context: Runtime context (not used).
            
        Returns:
            Transformed JSON dict.
        """
        target_fields = config.get('target_fields')
        prefix = config.get('prefix')
        suffix = config.get('suffix')

        if not prefix and not suffix:
            raise ValueError("AffixTransformer requires 'prefix' and/or 'suffix' in config")
        
        logic = AffixLogic(
            target_columns=target_fields,
            prefix=prefix,
            suffix=suffix
        )
        
        return logic.transform(data)


class AffixLogic:
    """Logic for applying prefixes and suffixes."""

    def __init__(self,
                 target_columns: Optional[List[str]] = None,
                 prefix: Optional[str] = None,
                 suffix: Optional[str] = None):
        """Initialize the transformer."""
        self.logger = logging.getLogger("pipeline.transformers.affix")
        self.target_columns = target_columns
        self.prefix = prefix or ""
        self.suffix = suffix or ""

    def _walk_and_transform(self, obj: Any) -> Any:
        """Recursively walk dict/list and transform all string values in-place."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                obj[k] = self._walk_and_transform(v)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                obj[i] = self._walk_and_transform(v)
        elif isinstance(obj, str):
            return self._transform_string(obj)
        return obj

    def _transform_string(self, s: str) -> str:
        """Apply prefix and/or suffix to the string."""
        return f"{self.prefix}{s}{self.suffix}"

    def _transform_field(self, obj: Any, field_path: str) -> None:
        """Transform a single field specified by its path."""
        parts = field_path.split('.')
        cur = obj
        for i, part in enumerate(parts):
            if '[' in part and part.endswith(']'):
                name, idx_str = part[:-1].split('[')
                try:
                    idx = int(idx_str)
                except ValueError:
                    return
                
                if name:
                    cur = cur.get(name) if isinstance(cur, dict) else None
                
                if isinstance(cur, list) and 0 <= idx < len(cur):
                    if i == len(parts) - 1:
                        if isinstance(cur[idx], str):
                            cur[idx] = self._transform_string(cur[idx])
                    else:
                        cur = cur[idx]
                else:
                    return
            else:
                if i == len(parts) - 1:
                    if isinstance(cur, dict) and part in cur and isinstance(cur[part], str):
                        cur[part] = self._transform_string(cur[part])
                else:
                    cur = cur.get(part) if isinstance(cur, dict) else None
            
            if cur is None:
                return


    def transform(self, data: Any, json_id: Optional[int] = None, **kwargs) -> Any:
        """Transform a JSON-like object."""
        obj = copy.deepcopy(data)

        if self.target_columns:
            for field in self.target_columns:
                self._transform_field(obj, field, json_id)
        else:
            self._walk_and_transform(obj, json_id)
        
        return obj
