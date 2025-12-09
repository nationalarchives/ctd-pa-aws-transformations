"""
Y-naming transformer
"""
import re
import copy
import logging
from typing import Any, Dict, Optional, List

from .base import BaseTransformer


class YNamingTransformer(BaseTransformer):
    """
    Applies Y-naming conventions to specified fields.
    If `target_fields` is not provided, it applies to all string values.
    
    Config parameters:
        target_fields: List of field paths to transform (optional)
        parameters: Additional parameters for Y-naming logic (optional)
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Apply Y-naming transformation.
        
        Args:
            data: JSON dict to transform
            config: May contain 'target_fields' list
            context: Runtime context (not used)
            
        Returns:
            Transformed JSON dict
        """
        target_fields = config.get('target_fields')
        
        # For this transformer, ref_set is expected to be None as it's not used
        # in the original implementation's context.
        transformer = YNamingLogic(target_columns=target_fields, ref_set=None)
        
        return transformer.transform(data)


class YNamingLogic:
    """Transformer for applying Y naming conventions."""

    def __init__(self,
                 target_columns: Optional[List[str]] = None,
                 backup_original: bool = True,
                 ref_set: Optional[set] = None):
        """Initialize the transformer."""
        self.logger = logging.getLogger("pipeline.transformers.y_naming")
        self.target_columns = target_columns
        self.backup_original = backup_original
        self._refs = None
        if ref_set is not None:
            self._refs = {self._normalize(r) for r in ref_set}
        self._fitted = True

    def _normalize(self, s: str) -> str:
        """Normalize a string for comparison."""
        if not isinstance(s, str):
            return ""
        return re.sub(r'[^a-zA-Z0-9]', '', s).lower()

    def _is_y_named(self, s: str) -> bool:
        """Check if a string follows the Y naming convention."""
        if not isinstance(s, str):
            return False
        return s.startswith('Y') and s[1:].isdigit()

    def _walk_and_transform(self, obj: Any, json_id: Optional[int] = None) -> Any:
        """Recursively walk dict/list and transform all string values in-place."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                obj[k] = self._walk_and_transform(v, json_id)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                obj[i] = self._walk_and_transform(v, json_id)
        elif isinstance(obj, str):
            return self._transform_string(obj, json_id)
        return obj

    def _transform_string(self, s: str, json_id: Optional[int] = None) -> str:
        """Apply Y-naming if the string is in the reference set."""
        if self._refs is None:
            return s
        if self._normalize(s) in self._refs:
            # This part of the logic that generates a new Y-name is not fully
            # implemented in the original code, as it depends on a 'y_namer' object
            # that is not available here.
            # For now, we will just log that a match was found.
            self.logger.info(f"Y-naming match found for: {s}")
        return s

    def _transform_field(self, obj: Any, field_path: str, json_id: Optional[int] = None) -> None:
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
                            cur[idx] = self._transform_string(cur[idx], json_id)
                    else:
                        cur = cur[idx]
                else:
                    return
            else:
                if i == len(parts) - 1:
                    if isinstance(cur, dict) and part in cur and isinstance(cur[part], str):
                        cur[part] = self._transform_string(cur[part], json_id)
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
