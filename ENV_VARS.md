# Environment Variables Reference

This document provides a reference for the environment variables used to configure the transformation pipeline.

## Core Pipeline Configuration (Lambda & Local)

These variables are essential for both the deployed AWS Lambda function and the local testing environment.

### `S3_OUTPUT_DIR`
- **Default**: `json_outputs`
- **Description**: The top-level prefix (folder) within the S3 bucket where final output tarballs and manifests will be stored.

### `TRANSFER_REGISTER_KEY`
- **Default**: `registers/uploaded_records_transfer_register.json`
- **Description**: The full S3 key for the transfer register file. This file is used to prevent duplicate processing of records.

### `CTD_LOG_LEVEL`
- **Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- **Default**: `INFO`
- **Description**: Controls the logging verbosity of the application. Set to `DEBUG` for detailed local troubleshooting.

### `TARBALL_BATCH_SIZE`
- **Default**: `10000`
- **Description**: The maximum number of individual record files to include in a single output `.tar.gz` archive.

---

## Local Development & Testing

These variables are primarily for use with the local development environment scripts (`init-local-env.ps1`, `run-local-pipeline.ps1`).

### `TEST_MODE`
- **Values**: `1`, `true`, `yes` (case-insensitive)
- **Description**: Enables a testing mode that typically uses a dedicated S3 prefix to avoid interfering with production data.
- **Note**: The `lambda_handler` uses this to direct outputs to the `S3_TEST_FOLDER`.

### `S3_TEST_FOLDER`
- **Example**: `testing`
- **Description**: When `TEST_MODE` is enabled, this S3 prefix is used for both input and output, isolating test runs.

### `AWS_ENDPOINT_URL`
- **Default**: `http://localhost:4566`
- **Description**: **(Set automatically by scripts)**. The endpoint URL for the LocalStack container. The `StorageClient` and AWS CLI use this to connect to LocalStack instead of AWS.

### `AWS_ACCESS_KEY_ID` & `AWS_SECRET_ACCESS_KEY`
- **Default**: `test`
- **Description**: **(Set automatically by scripts)**. Dummy credentials for authenticating with the local LocalStack instance.

---

## Transformer-Specific Variables

These variables are used to configure the behavior of specific transformers. They are typically passed within the `transformation_config` in the Step Functions event, but can be set as environment variables for global overrides.

### `ENABLE_REPLICA_METADATA`
- **Values**: `1`, `true`, `y` (or `0`, `false`)
- **Default**: `0`
- **Description**: Enables the `JsonAttachmentTransformer` to enrich records with replica metadata.

### `REPLICA_METADATA_BUCKET`
- **Description**: The S3 bucket where the per-record replica metadata JSON files are located. If not set, it defaults to the same bucket as the input data.

### `REPLICA_METADATA_PREFIX`
- **Default**: `replica`
- **Description**: The S3 prefix (folder) within the `REPLICA_METADATA_BUCKET` where the metadata files (e.g., `<IAID>.json`) are stored.

