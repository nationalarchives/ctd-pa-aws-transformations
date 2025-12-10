# Transformer Architecture

This document explains the hybrid transformer architecture that balances generic reusability with specialized domain logic.

## Overview

The transformer system is organized into three tiers:

1. **Generic Transformers**: Pure, configuration-driven operations with no domain-specific logic
2. **Specialized Transformers**: Domain-specific operations with sophisticated validation and business rules
3. **Legacy Reference**: Original implementations preserved for comparison and migration support

## Transformer Tiers

### Tier 1: Generic Transformers

These transformers are completely generic and work for any use case through configuration alone.

#### `TextReplaceTransformer` (`text_replace.py`)
- **Purpose**: Regex-based text replacement
- **Use Cases**: Newline to `<p>` conversion, any pattern-based text substitution
- **Config Example**:
  ```yaml
  newline_to_p:
    type: replace_text
    params:
      match: "\\n"
      replace: "<p>"
      target_fields: null  # Apply to all strings
  ```

#### `SimpleAffixTransformer` (`simple_affix.py`)
- **Purpose**: Add prefix/suffix to strings without validation
- **Use Cases**: Adding labels, decorators, or simple text wrapping
- **Config Example**:
  ```yaml
  add_label:
    type: add_affix
    params:
      prefix: "Original filepath: "
      suffix: ""
      target_fields:
        - "record.client_filepath"
  ```

#### `JsonAttachmentTransformer` (`json_attachment.py`)
- **Purpose**: Fetch JSON from S3 and attach to records
- **Use Cases**: Enriching records with replica metadata, external data sources
- **Config Example**:
  ```yaml
  attach_replica:
    type: attach_json
    params:
      source_bucket: "my-bucket"
      source_prefix: "metadata"
      source_id_path: "record.iaid"
      attachment_key: "replica"
      promote_fields:
        - source: "replicaId"
          destination: "record.replicaId"
  ```

#### `XMLConverterTransformer` (`xml_converter.py`)
- **Purpose**: Convert XML to JSON with field mappings
- **Use Cases**: Initial data ingestion from XML sources

---

### Tier 2: Specialized Transformers

These transformers contain sophisticated domain logic and validation rules.

#### `ReferenceAffixTransformer` (`reference_affix.py`)
- **Purpose**: Apply prefix/suffix to validated archival references with complex business rules
- **Primary Use Case**: Y-naming for The National Archives department codes
- **Key Features**:
  - **Syntax Validation**: Checks if strings match reference patterns (e.g., `ABC/123/456`)
  - **Definitive Reference Set**: Validates against a list of known valid department codes
  - **Position-Aware Exclusions**: Skips tokens in specific contexts like `(their ref: XYZ)`
  - **Special Case Handling**: e.g., `PARL` → `YUKP`
  - **Length Constraints**: Enforces maximum prefix length (e.g., 4 characters)
  - **Embedded Token Detection**: Finds and transforms references within larger text
  - **Double-Application Prevention**: Won't add `Y` if already present

- **Config Example** (Y-Naming):
  ```yaml
  y_naming:
    type: reference_affix
    params:
      prefix: "Y"
      suffix: ""
      max_prefix_length: 4
      special_cases:
        PARL: "YUKP"
      validation_rules:
        require_slash: true
        max_slashes: 9
        first_token_alpha_only: true
      definitive_refs:
        - "ADM"
        - "AIR"
        - "BBK"
        # ... more codes
      exclusion_patterns:
        - "\\(their ref:.*?\\)"
        - "\\(see also.*?\\)"
      target_fields: null
  ```

---

## Architecture Decision: Why Hybrid?

### The Problem
The original `transformers.py` contained:
1. **Generic operations** (text replacement) → Easy to generalize
2. **Sophisticated domain logic** (Y-naming with validation) → Difficult to generalize without losing critical functionality

### The Solution
Rather than forcing everything into a one-size-fits-all generic pattern, we adopted a **hybrid approach**:

- **Generic transformers** handle common operations through configuration
- **Specialized transformers** preserve complex domain logic while remaining configuration-driven
- Both share the same plugin interface, so the orchestrator doesn't need to know the difference

### Benefits
1. **No Loss of Functionality**: All original Y-naming logic preserved (reference validation, exclusions, special cases)
2. **Maximum Reusability**: Generic transformers can be used for any project
3. **Clear Separation**: Developers immediately understand which transformers have complex logic
4. **Maintainability**: Domain experts can focus on specialized transformers; platform engineers on generic ones
5. **Extensibility**: Easy to add new transformers in either tier

---

## Migration from Legacy Code

### Original `transformers.py` Mapping

| Legacy Class | New Architecture | Notes |
|-------------|------------------|-------|
| `NewlineToPTransformer` | `TextReplaceTransformer` | Fully generalized |
| `YNamingTransformer` | `ReferenceAffixTransformer` | Specialized with all original logic |
| `ReplicaDataTransformer` | `JsonAttachmentTransformer` | Fully generalized |
| `convert_to_json()` function | `XMLConverterTransformer` | Data ingestion, not transformation |

### Key Improvements
1. **Configuration-Driven**: All behavior now controlled via YAML/JSON config
2. **Type Safety**: Explicit parameter validation
3. **Better Logging**: Structured logging throughout
4. **Testability**: Logic separated from orchestration
5. **Composability**: Mix and match transformers in any order

---

## Adding New Transformers

### When to Create a Generic Transformer
Create a generic transformer if the operation:
- Has no domain-specific validation logic
- Can be fully described by simple parameters
- Works on any data structure

**Example**: A transformer that formats dates, converts units, or applies mathematical operations.

### When to Create a Specialized Transformer
Create a specialized transformer if the operation:
- Requires complex validation rules
- Has special case handling
- Contains business logic specific to your domain
- Needs contextual awareness (like position-based exclusions)

**Example**: Department code validation, legal compliance checks, domain-specific normalization.

### Steps to Add a Transformer

1. **Create the transformer file**:
   ```python
   # src/transformers/my_transformer.py
   from .base import BaseTransformer
   
   class MyTransformer(BaseTransformer):
       def execute(self, data, config, context):
           # Your logic here
           return transformed_data
   ```

2. **Register in `__init__.py`**:
   ```python
   from .my_transformer import MyTransformer
   
   TRANSFORMER_REGISTRY = {
       # ... existing transformers
       'my_operation': MyTransformer,
   }
   ```

3. **Use in configuration**:
   ```yaml
   tasks:
     my_task:
       type: my_operation
       params:
         # Your parameters
   ```

---

## Testing Strategy

### Unit Tests for Logic
Test the core logic classes separately:
```python
from src.transformers.reference_affix import ReferenceAffixLogic

def test_y_naming():
    logic = ReferenceAffixLogic(
        prefix="Y",
        max_prefix_length=4,
        definitive_refs=["ADM", "FO"]
    )
    assert logic.apply_if_reference("ADM/123") == "YADM/123"
    assert logic.apply_if_reference("Invalid") == "Invalid"
```

### Integration Tests
Test via the full orchestration pipeline with real configurations.

---

## Configuration Examples

See `config/example_y_naming_config.yml` for a comprehensive Y-naming configuration that replicates the original `transformers.py` behavior.

---

## Performance Considerations

- **Definitive Reference Sets**: Loading large reference sets from S3/SSM happens once at startup
- **Regex Compilation**: Patterns are compiled once during initialization
- **Deep Copying**: Transformers work on copies to prevent mutation of input data
- **Lazy Evaluation**: Exclusion spans only computed when needed

---

## Future Enhancements

Potential improvements to consider:
1. **Reference Set Caching**: Cache definitive refs in Lambda memory between invocations
2. **Async S3 Operations**: Parallel fetching for JSON attachments
3. **Transformer Composition**: Allow transformers to call other transformers
4. **Conditional Execution**: Skip transformers based on runtime conditions
5. **Metrics & Observability**: Track transformation success rates, execution times

---

## Questions & Support

For questions about:
- **Generic transformers**: Contact platform engineering team
- **Specialized transformers**: Contact domain experts (e.g., archival specialists for Y-naming)
- **Plugin architecture**: See `src/main_transformer.py` and `src/orchestration.py`
