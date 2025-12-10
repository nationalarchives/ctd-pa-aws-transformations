# Transfer Register & Tarring Implementation Summary

## Overview
This document summarizes the restoration of critical functionality that was present in the original `run_pipeline.py` but needed to be integrated into the new plugin-based architecture.

## 1. Transfer Register Check (✅ Implemented)

### Purpose
Prevents duplicate processing of records by checking if they've been previously uploaded.

### Location
`src/orchestration.py` - `LambdaOrchestrator` class

### How It Works

1.  **Initialization**: The orchestrator accepts an optional `transfer_register_key` parameter (defaults to `registers/uploaded_records_transfer_register.json`)

2.  **First Step Check**: When `transformation_index == 1`, the orchestrator calls `_check_transfer_register()`

3.  **Register Loading**: The method loads the transfer register JSON file from S3 using existing utility functions:
    ```python
    load_transfer_register(filename, s3_client, bucket, prefix, logger)
    ```

4.  **ID Extraction**: Extracts the record ID from the input file name (e.g., `A13530124` from `A13530124.xml`)

5.  **Membership Check**: Checks if the ID exists in the register's `records` dict

6.  **Skip or Continue**: 
    - If found: Returns a "skipped" response with reason
    - If not found: Processing continues normally

### Configuration
Set via environment variable:
```bash
TRANSFER_REGISTER_KEY=registers/uploaded_records_transfer_register.json
```

### Return Format (When Skipped)
```json
{
  "statusCode": 200,
  "execution_id": "exec_12345",
  "transformation_index": 1,
  "operation": "convert",
  "skipped": true,
  "reason": "Record 'A13530124' already in transfer register",
  "message": "Record already processed: ..."
}
```

---

## 2. Tarball Creation (✅ Implemented)

### Purpose
Bundles processed JSON files into compressed `.tar.gz` archives for efficient delivery.

### Location
`src/orchestration.py` - `LambdaOrchestrator.create_tarball()` method

### How It Works

1.  **Input**: Accepts processed JSON files grouped by level (e.g., "01 FONDS", "02 SUB-FONDS")

2.  **Batching**: Splits files into chunks of up to 10,000 per tarball (configurable via `BATCH_SIZE`)

3.  **Naming Convention**: 
    ```
    {tree_name}_{level_name}_{cumulative_count}.tar.gz
    ```
    Example: `example_tree_01_fonds_5000.tar.gz`

4.  **In-Memory Creation**: Uses Python's `tarfile` module to create archives in memory (no disk I/O)

5.  **S3 Upload**: Uploads each tarball to `tarballs/{execution_id}/{tarball_name}`

6.  **Transfer Register Update**: After successful tarball creation, updates the transfer register with all processed record IDs

### Key Features from Original

✅ **Level-based Grouping**: Supports organizing files by archival level  
✅ **Digitised Separation**: Can handle separate tarballs for digitised vs. normal records  
✅ **Batch Size Control**: Prevents tarballs from becoming too large  
✅ **Cumulative Naming**: Tarball names reflect total records (e.g., `_5000`, `_10000`)  
✅ **Register Updates**: Automatically marks records as processed after successful upload

### Usage Example

```python
orchestrator = LambdaOrchestrator(storage_client, transfer_register_key="registers/my_register.json")

# After all transformations complete
result = orchestrator.create_tarball(
    bucket="my-bucket",
    execution_id="exec_12345",
    final_step=3,
    tree_name="collection_abc",
    level_grouping={
        "01_fonds": [(filename1, json1), (filename2, json2), ...],
        "02_sub_fonds": [(filename3, json3), ...]
    }
)
```

### Return Format (Success)
```json
{
  "status": "success",
  "tarballs_created": 3,
  "tarballs": [
    {
      "name": "collection_abc_01_fonds_5000.tar.gz",
      "level": "01_fonds",
      "file_count": 5000,
      "size_bytes": 15728640,
      "s3_key": "tarballs/exec_12345/collection_abc_01_fonds_5000.tar.gz"
    },
    ...
  ]
}
```

---

## 3. Integration Points

### Lambda Handler
The `lambda_handler.py` remains minimal. It simply:
1.  Creates the `LambdaOrchestrator`
2.  Calls `orchestrator.run_step(event)`
3.  Returns the result

### Step Functions Workflow
The Step Functions state machine should:
1.  Execute transformation steps sequentially (steps 1, 2, 3, ...)
2.  After the final step, invoke the Lambda with a special "create_tarball" operation
3.  Check the response for `skipped: true` to handle already-processed records

### Environment Variables
```bash
# Transfer Register
TRANSFER_REGISTER_KEY=registers/uploaded_records_transfer_register.json

# Tarball Settings (optional - uses defaults if not set)
TARBALL_BATCH_SIZE=10000
```

---

## 4. Dependencies

### Utility Functions (from `src/utils.py`)
- `load_transfer_register()`: Loads the register from S3
- `save_transfer_register()`: Saves the updated register back to S3
- `filter_new_records()`: Filters out already-processed records
- `update_transfer_register_with_records()`: Adds new records to the register

### Storage Abstraction
Uses the `StorageClient` class for all S3 operations, maintaining compatibility with:
- AWS S3 (production)
- LocalStack (local testing)
- Local filesystem (development)

---

## 5. Testing Strategy

### Unit Tests
```python
def test_transfer_register_check_skips_duplicate():
    # Mock the storage client and transfer register
    # Call run_step with a known record ID
    # Assert that skipped=True is returned

def test_tarball_creation():
    # Mock storage client
    # Call create_tarball with test data
    # Verify tarball structure and content
```

### Integration Tests
1.  Upload a test file to LocalStack S3
2.  Run the pipeline
3.  Verify tarball is created
4.  Run the pipeline again with the same file
5.  Verify the second run is skipped

---

## 6. Migration Notes

### From Original `run_pipeline.py`

**What Was Preserved:**
- ✅ Transfer register loading and checking logic
- ✅ Tarball creation with batching
- ✅ Level-based organization
- ✅ Cumulative naming convention
- ✅ Register updates after successful processing

**What Changed:**
- ❌ Removed global `transfer_register` variable (now instance variable in orchestrator)
- ❌ Removed embedded transformation logic (now handled by plugin system)
- ❌ Removed direct XML parsing (now handled by `XMLConverterTransformer`)

**Key Difference:**
The original `run_pipeline.py` processed entire batches of files in a single Lambda invocation. The new architecture processes files individually via Step Functions, with each step being a separate Lambda invocation. This provides:
- Better fault tolerance
- Easier debugging
- More granular control
- Simpler retry logic

---

## 7. Next Steps

To complete the local testing setup:
1.  ✅ Create `local-s3-data/registers/` folder
2.  ✅ Add sample `uploaded_records_transfer_register.json`
3.  ✅ Update `init-local-env.ps1` to upload register to LocalStack
4.  ✅ Test full pipeline with duplicate detection
5.  ✅ Verify tarball creation in LocalStack S3
