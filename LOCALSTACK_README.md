# CTD Transformation Pipeline - Local Testing with LocalStack

Complete local simulation of AWS Lambda + Step Functions using your actual code (ZIP contents).

## Quick Start (5 minutes)

```powershell
# 1. Start LocalStack
docker-compose up -d

# 2. Initialize AWS resources (S3, Lambda, Step Functions)
.\init-localstack.ps1

# 3. Run the pipeline
.\run-local-pipeline.ps1

# 4. View results
aws s3 ls s3://ctd-pa-elt-data-processing-bucket/processed/ --recursive --endpoint-url http://localhost:4566
```

## What You Get

✅ **Step Functions** orchestrating your pipeline  
✅ **Lambda function** running your actual Python code  
✅ **S3** for data storage  
✅ **Python 3.12** runtime (matches AWS Lambda)  
✅ **Same code** used locally and in AWS (ZIP deployment)

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ LocalStack Container (Docker)                       │
│                                                     │
│  ┌──────────────────────────────────────────────┐ │
│  │ Step Functions State Machine                  │ │
│  │  - ctd-transformation-pipeline                │ │
│  └────────────┬─────────────────────────────────┘ │
│               │ invokes                             │
│               ▼                                     │
│  ┌──────────────────────────────────────────────┐ │
│  │ Lambda Function                               │ │
│  │  - ctd-transformer                            │ │
│  │  - Python 3.12                                │ │
│  │  - Your lambda_handler.py + src/              │ │
│  └────────────┬─────────────────────────────────┘ │
│               │ reads/writes                        │
│               ▼                                     │
│  ┌──────────────────────────────────────────────┐ │
│  │ S3 Bucket                                     │ │
│  │  - ctd-pa-elt-data-processing-bucket          │ │
│  │  - xml_input/                                 │ │
│  │  - processed/<execution_id>/step_N/           │ │
│  └──────────────────────────────────────────────┘ │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Transformation Pipeline

```
XML Input (xml_input/sample_file.xml)
    ↓
Step 1: Convert XML → JSON
    → Lambda invoked by Step Functions
    → Output: processed/<exec_id>/step_1/sample_file.json
    ↓
Step 2: Newline to <p> tags
    → Lambda invoked by Step Functions
    → Output: processed/<exec_id>/step_2/sample_file.json
    ↓
Step 3: Y-naming transformation
    → Lambda invoked by Step Functions
    → Output: processed/<exec_id>/step_3/sample_file.json
    ↓
Success!
```

## Files Overview

### Core Files
- **`lambda_handler.py`** - Task-agnostic Lambda handler
- **`src/transformers/`** - Transformer plugins
- **`src/storage.py`** - S3/LocalStack abstraction
- **`src/generic_transformer.py`** - Transformation orchestrator

### Local Testing
- **`docker-compose.yml`** - LocalStack setup
- **`init-localstack.ps1`** - Initialize AWS resources
- **`run-local-pipeline.ps1`** - Execute Step Functions pipeline
- **`test-data/sample_file.xml`** - Test data

### Deployment
- **`build/build.ps1`** - Package Lambda function + layer as ZIPs
- **`dist/`** - Output ZIPs for AWS deployment

## Key Features

### 1. Identical to AWS
- Same Lambda code runs locally and in AWS
- Same Step Functions state machine definition
- Same S3 folder structure
- Python 3.12 runtime (matches AWS Lambda)

### 2. Fast Iteration
- No AWS deployment needed for testing
- Instant feedback on code changes
- Re-run: `.\init-localstack.ps1` → `.\run-local-pipeline.ps1`

### 3. Task-Agnostic Lambda
- Single Lambda function handles all transformation types
- Configuration-driven (via `transformation_config`)
- Easy to add new transformers (plugin registry pattern)

### 4. Step-by-Step Processing
- Each step reads from previous step's output
- `_SUCCESS` markers ensure data availability
- S3 folder structure: `processed/<exec_id>/step_N/`

## Common Commands

```powershell
# Start LocalStack
docker-compose up -d

# Initialize resources (first time or after changes)
.\init-localstack.ps1

# Run pipeline
.\run-local-pipeline.ps1

# Run with custom XML file
aws s3 cp "myfile.xml" s3://ctd-pa-elt-data-processing-bucket/xml_input/ --endpoint-url http://localhost:4566
.\run-local-pipeline.ps1 -InputFile "myfile.xml"

# View S3 contents
aws s3 ls s3://ctd-pa-elt-data-processing-bucket/ --recursive --endpoint-url http://localhost:4566

# Download output
aws s3 cp s3://ctd-pa-elt-data-processing-bucket/processed/exec-123/step_3/sample_file.json - --endpoint-url http://localhost:4566

# Check Lambda logs
docker-compose logs localstack | Select-String "ctd-transformer"

# View Step Functions executions
aws stepfunctions list-executions --state-machine-arn "arn:aws:states:us-east-1:000000000000:stateMachine:ctd-transformation-pipeline" --endpoint-url http://localhost:4566

# Stop LocalStack
docker-compose down
```

## Deployment to AWS

```powershell
# 1. Build ZIPs
.\build\build.ps1

# 2. Deploy function
aws lambda create-function \
  --function-name ctd-transformer \
  --runtime python3.12 \
  --role arn:aws:iam::ACCOUNT:role/lambda-role \
  --handler lambda_handler.lambda_handler \
  --zip-file fileb://dist/lambda_function.zip

# 3. Create layer
aws lambda publish-layer-version \
  --layer-name ctd-dependencies \
  --zip-file fileb://dist/lambda_layer.zip \
  --compatible-runtimes python3.12

# 4. Attach layer
aws lambda update-function-configuration \
  --function-name ctd-transformer \
  --layers arn:aws:lambda:REGION:ACCOUNT:layer:ctd-dependencies:1

# 5. Create Step Functions state machine
# (Use definition from init-localstack.ps1, replace ARNs)
```

## Troubleshooting

### LocalStack not starting
```powershell
docker-compose down
docker-compose up -d
docker-compose logs localstack
```

### Lambda errors
```powershell
# View logs
docker-compose logs localstack | Select-String "ERROR"

# Reinitialize
.\init-localstack.ps1
```

### Step Functions failures
```powershell
# Get execution details
$execArn = "arn:aws:states:us-east-1:000000000000:execution:ctd-transformation-pipeline:exec-123"
aws stepfunctions describe-execution --execution-arn $execArn --endpoint-url http://localhost:4566
```

## Documentation

- **`QUICKSTART_LOCAL.md`** - Detailed local testing guide
- **`LOCAL_TESTING.md`** - Advanced testing scenarios
- **`DEPLOYMENT.md`** - AWS deployment instructions

## Requirements

- Docker Desktop
- PowerShell 5.1+
- AWS CLI
- Python 3.12 (for local development)

## Next Steps

1. Test locally: `.\init-localstack.ps1` → `.\run-local-pipeline.ps1`
2. Add your XML files to `test-data/`
3. Deploy to AWS when ready
4. Set up CI/CD pipeline
