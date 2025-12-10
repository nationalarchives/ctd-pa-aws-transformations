"""
Specialized transformer for applying reference-based affixing with validation.
Primary use case: Y-naming conventions for archival references.
"""
import re
import copy
import json as _json
import logging
from typing import Any, Dict, Optional, List, Iterable, Set

from .base import BaseTransformer
from ..utils import get_by_path, set_by_path


class ReferenceAffixTransformer(BaseTransformer):
    """
    Applies prefix/suffix to validated reference-like strings.
    
    This transformer performs sophisticated validation before applying transformations:
    - Checks if strings match reference syntax patterns
    - Validates against a definitive reference set (optional)
    - Supports position-aware exclusion patterns (e.g., skip tokens in parenthetical notes)
    - Handles special case transformations
    - Supports embedded reference detection
    
    Config parameters:
        prefix: String to prepend to validated references (optional).
        suffix: String to append to validated references (optional).
        max_prefix_length: Maximum length of the prefix after affixing (e.g., 4 for Y-naming).
        definitive_refs: List of valid reference codes or path to load them from.
        exclusion_patterns: List of regex patterns indicating contexts where affixing should be skipped.
        special_cases: Dict mapping specific inputs to specific outputs (e.g., {"PARL": "YUKP"}).
        validation_rules: Dict of validation settings:
            - require_slash: bool (default True)
            - max_slashes: int (default 9)
            - first_token_alpha_only: bool (default True)
        target_fields: List of field paths to transform (optional, applies to all if None).
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def execute(self, data: Any, config: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Apply reference affixing with validation.
        
        Args:
            data: JSON dict to transform.
            config: Configuration dict with affixing rules and validation settings.
            context: Runtime context (storage client for loading refs, etc.).
            
        Returns:
            Transformed JSON dict.
        """
        logic = ReferenceAffixLogic(
            target_columns=config.get('target_fields'),
            prefix=config.get('prefix'),
            suffix=config.get('suffix'),
            max_prefix_length=config.get('max_prefix_length'),
            definitive_refs=config.get('definitive_refs'),
            exclusion_patterns=config.get('exclusion_patterns'),
            special_cases=config.get('special_cases'),
            validation_rules=config.get('validation_rules', {})
        )
        
        return logic.transform(data)


class ReferenceAffixLogic:
    """Core logic for reference-based affixing with validation."""

    def __init__(self,
                 target_columns: Optional[List[str]] = None,
                 prefix: Optional[str] = None,
                 suffix: Optional[str] = None,
                 max_prefix_length: Optional[int] = None,
                 definitive_refs: Optional[Any] = None,
                 exclusion_patterns: Optional[List[str]] = None,
                 special_cases: Optional[Dict[str, str]] = None,
                 validation_rules: Optional[Dict[str, Any]] = None):
        """Initialize the transformer."""
        self.logger = logging.getLogger("pipeline.transformers.reference_affix")
        self.target_columns = target_columns
        self.prefix = prefix or ""
        self.suffix = suffix or ""
        self.max_prefix_length = max_prefix_length
        self.special_cases = special_cases or {}
        
        # Validation rules
        rules = validation_rules or {}
        self.require_slash = rules.get('require_slash', True)
        self.max_slashes = rules.get('max_slashes', 9)
        self.first_token_alpha_only = rules.get('first_token_alpha_only', True)
        
        # Reference set and exclusions
        self._refs: Optional[Set[str]] = None
        self._exclusion_patterns: List[re.Pattern] = []
        
        if definitive_refs is not None:
            self.set_definitive_refs(definitive_refs)
        
        if exclusion_patterns:
            self.set_exclusions(exclusion_patterns)
        
        # Embedded token regex: requires at least one slash
        self._embedded_token_re = re.compile(r'([A-Z0-9-]+(?:/[A-Z0-9-]+)+/?)')

    def set_definitive_refs(self, refs: Optional[Any]):
        """Set/normalize the definitive reference set used for membership checks."""
        if refs is None:
            self._refs = None
            return self
        
        try:
            # Handle JSON string input
            if isinstance(refs, str):
                try:
                    parsed = _json.loads(refs)
                    return self.set_definitive_refs(parsed)
                except Exception:
                    # Not JSON; treat as single code string
                    refs = [refs]

            # Handle dict input
            if isinstance(refs, dict):
                for key in ('valid_department_codes', 'valid_dept_codes', 'valid_refs'):
                    if key in refs:
                        refs = refs[key]
                        break
                else:
                    if all(isinstance(k, str) for k in refs.keys()):
                        refs = list(refs.keys())
                    else:
                        vals = [v for v in refs.values() if isinstance(v, str) and v.strip()]
                        refs = vals

            # Normalize iterable of strings into a set
            self._refs = {r.strip().upper() for r in refs if isinstance(r, str) and r.strip()}
            self.logger.debug(f"Loaded {len(self._refs)} definitive reference codes")
        except Exception as e:
            self.logger.warning(f"Invalid refs provided: {e}; ignoring")
            self._refs = None
        return self

    def set_exclusions(self, exclusions: Optional[List[str]]):
        """Set exclusion patterns from a list of contextual phrases or regex strings."""
        self._exclusion_patterns = []
        if not exclusions:
            return self
        
        for ex in exclusions:
            if not ex or not isinstance(ex, str):
                continue
            try:
                # Compile as case-insensitive regex
                self._exclusion_patterns.append(re.compile(re.escape(ex), flags=re.IGNORECASE))
            except Exception as e:
                self.logger.warning(f"Failed to compile exclusion pattern '{ex}': {e}")
                continue
        
        self.logger.debug(f"Loaded {len(self._exclusion_patterns)} exclusion patterns")
        return self

    def _is_reference_like(self, s: str) -> bool:
        """Returns True if the string is syntactically similar to a citable reference."""
        if not isinstance(s, str):
            return False
        
        orig = s
        t = s.strip()
        if not t:
            return False
        
        # Reject if more than max_slashes
        if t.count('/') > self.max_slashes:
            return False
        
        # Handle bare tokens (1-4 uppercase letters, no slashes)
        if re.fullmatch(r'[A-Z]{1,4}', t):
            if self._refs is not None:
                return self._membership_ok(t)
            return False
        
        # Explicit exclusion: tokens starting with "APT/" (case-insensitive)
        if re.search(r'(?i)\bAPT/', orig):
            return False
        
        # Embedded short token inside other text
        m = re.search(r'\b([A-Z]{1,4})\b', t)
        if m and (m.group(1) != t):
            token = m.group(1).upper()
            if self._refs is not None:
                return self._membership_ok(token)
            return True
        
        # Check slash count requirement
        slash_count = s.count('/')
        if self.require_slash and slash_count < 1:
            return False
        if slash_count > self.max_slashes:
            return False
        
        raw_toks = s.split('/')
        toks = [tok.strip() for tok in raw_toks]
        
        if len(toks) < 2 or len(toks) > 10:
            return False
        
        # Reject if any token had leading/trailing whitespace or is empty
        for raw, tok in zip(raw_toks, toks):
            if raw != tok or tok == '':
                return False
            if not re.match(r'^[A-Za-z0-9-]+$', tok):
                return False
        
        # First token validation
        if self.first_token_alpha_only and not re.match(r'^[A-Za-z]+$', toks[0]):
            return False
        
        # Prefix must be at least 1 alphabetic character
        return (len(toks[0]) > 1) or (toks[0] == 'S')

    def _membership_ok(self, token: str) -> bool:
        """Check if token is in the definitive reference set."""
        if not isinstance(token, str):
            return False
        t = token.strip().upper()
        if not t:
            return False
        
        # Handle special cases first
        if t in self.special_cases:
            return True
        
        if self._refs is None:
            return False
        return t in self._refs

    def _apply_affixing(self, text: str) -> str:
        """Apply prefix/suffix with special case handling and length constraints."""
        if not isinstance(text, str) or not text.strip():
            return text

        ref = text.strip()
        if not ref:
            return text

        # Check for special cases first
        ref_upper = ref.upper()
        if ref_upper in self.special_cases:
            return self.special_cases[ref_upper]

        # Split by slash to get the prefix (letter code)
        parts = ref.split('/')
        if len(parts) == 0:
            return text

        prefix_part = parts[0].strip().upper()
        suffix_part = '/' + '/'.join(parts[1:]) if len(parts) > 1 else ''

        # Only apply affixing for purely alphabetic prefixes
        if not parts[0].strip().isalpha():
            return text

        # Check if already has the prefix to avoid double-application
        if self.prefix and prefix_part.startswith(self.prefix.upper()):
            new_prefix = prefix_part
        else:
            # Add prefix
            temp_prefix = self.prefix.upper() + prefix_part
            
            # Apply max_prefix_length constraint if specified
            if self.max_prefix_length and len(temp_prefix) > self.max_prefix_length:
                new_prefix = temp_prefix[:self.max_prefix_length]
            else:
                new_prefix = temp_prefix

        # Apply suffix (typically empty for Y-naming)
        result = new_prefix + suffix_part + self.suffix
        return result

    def _get_exclusion_spans(self, text: str) -> List[tuple]:
        """Build list of exclusion spans (start, end positions) in the text."""
        exclusion_spans = []
        if self._exclusion_patterns:
            for pattern in self._exclusion_patterns:
                try:
                    for match in pattern.finditer(text):
                        exclusion_spans.append((match.start(), match.end()))
                except Exception:
                    continue
        return exclusion_spans

    def _is_position_excluded(self, match_start: int, match_end: int, exclusion_spans: List[tuple]) -> bool:
        """Check if a match position overlaps any exclusion span."""
        for ex_start, ex_end in exclusion_spans:
            if not (match_end <= ex_start or match_start >= ex_end):
                return True
        return False

    def apply_if_reference(self, text: str) -> str:
        """
        If text is syntactically reference-like and valid, apply affixing.
        Uses position-aware exclusion checking.
        """
        if not isinstance(text, str):
            return text
        
        # Build exclusion spans
        exclusion_spans = self._get_exclusion_spans(text)
        
        # Check if the whole field is a canonical reference
        if self._is_reference_like(text):
            # Check if entire text is excluded
            if exclusion_spans and any(start == 0 and end >= len(text) for start, end in exclusion_spans):
                return text
            
            # If no definitive set loaded, treat syntactic matches as references
            if self._refs is None:
                return self._apply_affixing(text)
            
            # Check membership
            normalized_whole = text.strip().upper()
            if self._membership_ok(normalized_whole):
                return self._apply_affixing(text)
        
        # Attempt to find embedded reference-like tokens
        try:
            new_text = self._replace_embedded_references(text, exclusion_spans)
            if new_text != text:
                self.logger.debug(f"Applied affixing to embedded references")
            return new_text
        except Exception as e:
            self.logger.warning(f"Error processing embedded references: {e}")
            return text

    def _replace_embedded_references(self, text: str, exclusion_spans: List[tuple]) -> str:
        """Find embedded reference-like tokens and replace with affixed equivalents."""
        if not isinstance(text, str):
            return text
        
        def repl(m: re.Match) -> str:
            token = m.group(1)
            # Check if this token's position is within an excluded span
            if self._is_position_excluded(m.start(), m.end(), exclusion_spans):
                return token
            
            if not self._is_reference_like(token):
                return token
            
            # Membership check if definitive set loaded
            if self._refs is not None:
                if self._membership_ok(token):
                    return self._apply_affixing(token)
                return token
            
            # No definitive set: apply algorithmic transform
            return self._apply_affixing(token)

        # Replace tokens with at least one slash
        out = self._embedded_token_re.sub(repl, text)

        # If we have definitive refs, also replace short bare tokens
        if self._refs:
            short_re = re.compile(r'\b([A-Z]{1,4})\b')

            def repl_short(m: re.Match) -> str:
                tok = m.group(1)
                if self._is_position_excluded(m.start(), m.end(), exclusion_spans):
                    return tok
                
                if self._membership_ok(tok) and self._is_reference_like(tok):
                    return self._apply_affixing(tok)
                return tok

            out = short_re.sub(repl_short, out)

        return out

    def transform(self, data: dict, **kwargs) -> dict:
        """Apply reference affixing to a JSON dict."""
        obj = copy.deepcopy(data)

        # If no target_columns specified, apply to all strings
        if self.target_columns is None:
            self._transform_all_strings(obj)
            return obj

        # Apply to specific fields
        for field in self.target_columns:
            candidates = [field]
            if field.startswith('record.'):
                candidates.append(field[len('record.'):])
            else:
                candidates.append('record.' + field)

            for candidate in candidates:
                if self._transform_target_path(obj, candidate):
                    break
        
        return obj

    def _transform_all_strings(self, obj: Any) -> None:
        """Recursively apply affixing to all string values."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str):
                    obj[key] = self.apply_if_reference(value)
                else:
                    self._transform_all_strings(value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str):
                    obj[i] = self.apply_if_reference(item)
                else:
                    self._transform_all_strings(item)

    def _transform_target_path(self, obj: dict, path: str) -> bool:
        """Apply transformation at a dotted path. Returns True if successful."""
        parts = path.split('.')
        cur = obj
        for i, part in enumerate(parts):
            last = (i == len(parts) - 1)
            if not isinstance(cur, dict) or part not in cur:
                return False
            val = cur[part]
            if last:
                if isinstance(val, str):
                    new_val = self.apply_if_reference(val)
                    if new_val != val:
                        cur[part] = new_val
                        return True
                    return False
                if isinstance(val, (dict, list)):
                    before = _json.dumps(val, ensure_ascii=False, sort_keys=True) if isinstance(val, dict) else str(val)
                    self._transform_all_strings(val)
                    after = _json.dumps(val, ensure_ascii=False, sort_keys=True) if isinstance(val, dict) else str(val)
                    return before != after
                return False
            else:
                cur = val
        return False
