"""
Generic text replacement transformer.
"""
import re
import copy
from typing import Any, Dict, Optional, Iterable

from .base import BaseTransformer


class TextReplaceTransformer(BaseTransformer):
    """
    Replaces text in specified fields based on a regex pattern.
    If `target_fields` is not provided, it applies to all string values.
    
    Config parameters:
        match: The regex pattern to search for.
        replace: The string to replace matches with.
        target_fields: List of field paths to transform (optional).
    """

    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Apply text replacement.
        
        Args:
            data: JSON dict to transform.
            config: Must contain 'match' and 'replace'. Can contain 'target_fields'.
            context: Runtime context (not used).
            
        Returns:
            Transformed JSON dict.
        """
        target_fields = config.get('target_fields')
        match = config.get('match')
        replace = config.get('replace')

        if match is None or replace is None:
            raise ValueError("TextReplaceTransformer requires 'match' and 'replace' in config")
        
        logic = TextReplaceLogic(
            target_columns=target_fields,
            match=match,
            replace=replace
        )
        
        return logic.transform(data)


class TextReplaceLogic:
    def __init__(self, target_columns: Optional[Iterable[str]] = None, match: str = "", replace: str = ""):
        self.target_columns = target_columns
        self.match = match
        self.replace = replace
        self.regex = re.compile(self.match)

    def _transform_string(self, s: str) -> str:
        """Apply the replacement policy to a single string."""
        if not isinstance(s, str):
            return s
        
        # Normalize line endings to handle cross-platform variations
        text = s.replace('\r\n', '\n').replace('\r', '\n')
        
        try:
            return self.regex.sub(self.replace, text)
        except re.error as e:
            # Log the error and fall back to a simple string replacement
            # This handles cases where the 'match' string is not a valid regex
            print(f"Regex error: {e}. Falling back to simple string replacement.")
            return text.replace(self.match, self.replace)


    def _walk_and_transform(self, obj):
        """Recursively walk dict/list and transform all string values in-place."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                obj[k] = self._walk_and_transform(v)
            return obj
        if isinstance(obj, list):
            for i, v in enumerate(obj):
                obj[i] = self._walk_and_transform(v)
            return obj
        if isinstance(obj, str):
            return self._transform_string(obj)
        return obj

    @staticmethod
    def _parse_part(part: str):
        m = re.match(r'^([^\[]+)(?:\[(\d+)\])?$', part)
        if not m:
            return part, None
        key = m.group(1)
        idx = int(m.group(2)) if m.group(2) is not None else None
        return key, idx

    def set_by_path(self, obj: Any, path: str, value: Any) -> bool:
        """Set value at dotted/bracket path."""
        cur = obj
        parts = path.split('.')
        for i, part in enumerate(parts):
            key, idx = self._parse_part(part)
            last = (i == len(parts) - 1)
            if not isinstance(cur, dict):
                return False
            if last:
                if idx is None:
                    if key in cur:
                        cur[key] = value
                        return True
                else:
                    lst = cur.get(key)
                    if isinstance(lst, list) and 0 <= idx < len(lst):
                        lst[idx] = value
                        return True
                return False
            
            cur = cur.get(key)
            if cur is None:
                return False
            if idx is not None:
                if not isinstance(cur, list) or not (0 <= idx < len(cur)):
                    return False
                cur = cur[idx]
        return False

    def get_by_path(self, obj: Any, path: str, default: Any = None) -> Any:
        """Return value at dotted/bracket path or default if not found."""
        cur = obj
        for part in path.split('.'):
            key, idx = self._parse_part(part)
            if not isinstance(cur, dict):
                return default
            cur = cur.get(key, default)
            if cur is default:
                return default
            if idx is not None:
                if not isinstance(cur, list) or idx < 0 or idx >= len(cur):
                    return default
                cur = cur[idx]
        return cur

    def transform(self, data: dict, **kwargs) -> dict:
        """
        If target_columns is None, apply transformation to every string value.
        If target_columns is provided, apply only to those fields.
        """
        payload = copy.deepcopy(data)

        if self.target_columns is None:
            return self._walk_and_transform(payload)

        for field_path in self.target_columns:
            current_value = self.get_by_path(payload, field_path)
            if isinstance(current_value, str):
                new_value = self._transform_string(current_value)
                if new_value != current_value:
                    self.set_by_path(payload, field_path, new_value)
        return payload
