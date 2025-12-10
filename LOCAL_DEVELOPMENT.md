# Local Development Guide

This guide provides a complete walkthrough for setting up and running the transformation pipeline locally using Docker and LocalStack. This setup fully simulates the AWS environment on your machine.

## Overview

The local environment uses Docker to run a LocalStack container, which provides local implementations of AWS services, including:
- **S3**: For storing input data, configurations, and output results.
- **Lambda**: For running the transformation function.
- **Step Functions**: For orchestrating the multi-step pipeline.

Your actual Python code from the `src` directory is packaged and deployed to the LocalStack Lambda, ensuring the local execution environment is as close to production as possible.

## Prerequisites

- **Docker Desktop**: Must be installed and running.
- **PowerShell**: For running the local orchestration scripts.
- **AWS CLI**: For interacting with the LocalStack container (e.g., viewing S3 contents).
- **Python 3.12**: For local development and to match the Lambda runtime.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ Your Local Machine                                  │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │ PowerShell Scripts                            │   │
│  │  - init-local-env.ps1 (Setup)                │   │
│  │  - run-local-pipeline.ps1 (Execute)          │   │
│  └────────────┬─────────────────────────────────┘   │
│               │ interacts with                      │
│               ▼                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │ Docker / LocalStack Container                 │   │
│  │                                               │   │
│  │   ▶ S3 (for data and config)                  │   │
│  │   ▶ Lambda (runs your Python code)            │   │
│  │   ▶ Step Functions (manages the workflow)     │   │
│  │                                               │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Step-by-Step Setup

### 1. Start the Local Environment

This single command starts the LocalStack container in the background.

```powershell
docker-compose up -d
```

To check that it's running, use `docker-compose ps`. You should see the `localstack` service in the 'running' state.

### 2. Initialize LocalStack Resources

This script sets up the entire AWS environment inside LocalStack. It's safe to run this script multiple times.

```powershell
.\init-local-env.ps1
```

This script will:
- ✅ Create the S3 bucket (`ctd-pa-elt-data-processing-bucket`).
- ✅ Sync local test data and configurations from `local-s3-data/` to the S3 bucket. This includes test XML, transformer configurations, and the transfer register.
- ✅ Build and package the Python code from `src/` and `lambda_handler.py`.
- ✅ Create the `ctd-transformer` Lambda function with a Python 3.12 runtime.
- ✅ Create the `ctd-transformation-pipeline` Step Functions state machine.

### 3. Run the Transformation Pipeline

This script starts an execution of the Step Functions state machine, which will trigger the Lambda function for each step in the transformation process.

```powershell
.\run-local-pipeline.ps1
```

You can also run the pipeline for a specific input file:

```powershell
.\run-local-pipeline.ps1 -InputFile "your-file-name.xml"
```

The script will display the real-time status of the execution and show the final output upon completion.

### 4. Check the Results

You can use the AWS CLI to inspect the contents of the LocalStack S3 bucket.

```powershell
# List all files in the output directory
aws s3 ls s3://ctd-pa-elt-data-processing-bucket/processed/ --recursive --endpoint-url http://localhost:4566

# Download and view the final transformed JSON file
# (Replace the execution ID with the one from your pipeline output)
$execId = "exec-..."
aws s3 cp s3://ctd-pa-elt-data-processing-bucket/processed/$execId/step_3/sample_file.json - --endpoint-url http://localhost:4566
```

## Local S3 Data Structure

The `local-s3-data` directory on your local filesystem is a mirror of the S3 bucket structure used for testing. The `init-local-env.ps1` script automatically syncs its contents into LocalStack's S3 service.

```
local-s3-data/
└── ctd-pa-elt-data-processing-bucket/
    ├── input/
    │   └── sample_file.xml         # Sample input data
    ├── config/
    │   ├── y_naming_config.yml     # Config for the ReferenceAffixTransformer
    │   └── definitive_refs.json    # Validation data for Y-naming
    ├── registers/
    │   └── uploaded_records_transfer_register.json # Prevents duplicate processing
    └── processed/
        └── <execution_id>/         # Each run gets a unique folder
            ├── step_1/
            │   └── sample_file.json
            └── ...
```

To add new test files or update configurations, simply modify the contents of the `local-s3-data` directory and re-run `.\init-local-env.ps1`.

## Troubleshooting

### "LocalStack is not running" or "Cannot connect to the Docker daemon"
- Ensure Docker Desktop is running.
- Run `docker-compose ps` to check the container status.
- View container logs with `docker-compose logs localstack`.

### Lambda or Step Functions Errors
- **Re-initialize**: The most common fix is to re-run the initialization script to ensure all resources are correctly configured: `.\init-local-env.ps1`.
- **Check Lambda Logs**: View the LocalStack container logs and filter for Lambda output: `docker-compose logs localstack | Select-String "ctd-transformer"`.
- **Check Step Functions History**: Get the execution ARN from the pipeline output and inspect the history:
  ```powershell
  $execArn = "arn:aws:states:us-east-1:000000000000:execution:ctd-transformation-pipeline:exec-..."
  aws stepfunctions get-execution-history --execution-arn $execArn --endpoint-url http://localhost:4566
  ```

## Cleanup

```powershell
# Stop and remove the LocalStack container
docker-compose down

# To perform a full cleanup, including all data stored by LocalStack:
docker-compose down --volumes
```
