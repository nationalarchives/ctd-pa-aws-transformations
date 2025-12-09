# Quick Start - Local Testing with LocalStack

This guide will get you up and running locally with Step Functions in **5 minutes**.

## Overview

This setup simulates the complete AWS environment locally:
- **LocalStack** provides S3, Lambda, and Step Functions
- Your actual Lambda code (ZIP contents) runs in LocalStack
- Step Functions orchestrates the 3-step transformation pipeline
- All data stored in LocalStack's S3

## Prerequisites

- **Docker Desktop** installed and running
- **PowerShell 5.1+** or PowerShell Core 7+
- **AWS CLI** installed
- **Python 3.12** (for local development)

## Architecture

```
Step Functions (LocalStack)
    ↓ invokes
Lambda Function (your code running in LocalStack)
    ↓ reads/writes
S3 (LocalStack)
```

## Folder Structure

LocalStack S3 stores data internally. You can view it using AWS CLI:

```powershell
# List S3 contents
aws s3 ls s3://ctd-pa-elt-data-processing-bucket/ --recursive --endpoint-url http://localhost:4566

# Expected structure after running pipeline:
# xml_input/sample_file.xml
# processed/<execution-id>/step_1/sample_file.json
# processed/<execution-id>/step_1/_SUCCESS
# processed/<execution-id>/step_2/sample_file.json
# processed/<execution-id>/step_2/_SUCCESS
# processed/<execution-id>/step_3/sample_file.json
# processed/<execution-id>/step_3/_SUCCESS
```

## Step-by-Step Setup

### 1. Start LocalStack

```powershell
# Start LocalStack container
docker-compose up -d

# Check it's running
docker-compose ps
```

You should see `localstack` running on port 4566.

### 2. Initialize LocalStack

```powershell
# This creates S3 bucket, Lambda function, and Step Functions state machine
.\init-localstack.ps1
```

This will:
- ✅ Create S3 bucket `ctd-pa-elt-data-processing-bucket`
- ✅ Package your Lambda code (lambda_handler.py + src/)
- ✅ Create Lambda function `ctd-transformer` with Python 3.12 runtime
- ✅ Create Step Functions state machine `ctd-transformation-pipeline`
- ✅ Upload test XML file to S3

### 3. Run the Pipeline

```powershell
# Execute the transformation pipeline
.\run-local-pipeline.ps1
```

This will:
1. Start a Step Functions execution
2. Step Functions invokes Lambda for Step 1 (XML → JSON)
3. Step Functions invokes Lambda for Step 2 (Newline to `<p>`)
4. Step Functions invokes Lambda for Step 3 (Y-naming)
5. Show execution status in real-time
6. Display results when complete

### 4. Check the Results

```powershell
# List all outputs
aws s3 ls s3://ctd-pa-elt-data-processing-bucket/processed/ --recursive --endpoint-url http://localhost:4566

# Download final output
$execId = "exec-20251209-143022"  # Use actual execution ID from pipeline output
aws s3 cp s3://ctd-pa-elt-data-processing-bucket/processed/$execId/step_3/sample_file.json - --endpoint-url http://localhost:4566
```

## What's Happening?

### Step Functions State Machine

The state machine orchestrates the pipeline:

```
Start Execution
    ↓
Transform_Step_1 (Lambda Task)
    → Invokes: ctd-transformer Lambda
    → Input: xml_input/sample_file.xml
    → Output: processed/<exec_id>/step_1/sample_file.json
    → Success Marker: processed/<exec_id>/step_1/_SUCCESS
    ↓
Check_Step_1 (Choice State)
    → If statusCode == 200 → Continue
    → Otherwise → Pipeline_Failed
    ↓
Transform_Step_2 (Lambda Task)
    → Invokes: ctd-transformer Lambda
    → Input: processed/<exec_id>/step_1/sample_file.json
    → Output: processed/<exec_id>/step_2/sample_file.json
    → Success Marker: processed/<exec_id>/step_2/_SUCCESS
    ↓
Check_Step_2 (Choice State)
    → If statusCode == 200 → Continue
    → Otherwise → Pipeline_Failed
    ↓
Transform_Step_3 (Lambda Task)
    → Invokes: ctd-transformer Lambda
    → Input: processed/<exec_id>/step_2/sample_file.json
    → Output: processed/<exec_id>/step_3/sample_file.json
    → Success Marker: processed/<exec_id>/step_3/_SUCCESS
    ↓
Check_Step_3 (Choice State)
    → If statusCode == 200 → Pipeline_Success
    → Otherwise → Pipeline_Failed
```

### Lambda Function

Your `lambda_handler.py` runs inside LocalStack and receives events from Step Functions:

**Event from Step Functions:**
```json
{
  "bucket": "ctd-pa-elt-data-processing-bucket",
  "key": "xml_input/sample_file.xml",
  "transformation_index": 1,
  "transformation_config": {
    "1": {"operation": "convert", ...},
    "2": {"operation": "newline_to_p", ...},
    "3": {"operation": "y_naming", ...}
  },
  "execution_id": "exec-20251209-143022"
}
```

**Lambda Returns:**
```json
{
  "statusCode": 200,
  "execution_id": "exec-20251209-143022",
  "transformation_index": 1,
  "operation": "convert",
  "output_key": "processed/exec-20251209-143022/step_1/sample_file.json",
  "success_marker": "processed/exec-20251209-143022/step_1/_SUCCESS",
  "message": "Step 1 completed successfully"
}
```

The `StorageClient` in `src/storage.py` automatically detects LocalStack via the `AWS_ENDPOINT_URL` environment variable.

## Testing with Your Own XML

```powershell
# Upload your XML to LocalStack S3
aws s3 cp "C:\path\to\your\file.xml" s3://ctd-pa-elt-data-processing-bucket/xml_input/ --endpoint-url http://localhost:4566

# Run pipeline with your file
.\run-local-pipeline.ps1 -InputFile "your_file.xml"
```

## Troubleshooting

### "LocalStack is not running"

```powershell
# Check container status
docker-compose ps

# View logs
docker-compose logs localstack

# Restart
docker-compose restart localstack
```

### "Step Functions not available"

```powershell
# Re-initialize LocalStack
.\init-localstack.ps1
```

### "Lambda function not found"

```powershell
# Verify Lambda exists
aws lambda list-functions --endpoint-url http://localhost:4566

# Recreate if missing
.\init-localstack.ps1
```

### View Lambda execution logs

```powershell
# Check LocalStack logs for Lambda output
docker-compose logs localstack | Select-String "lambda"

# Or get logs for specific function
aws logs tail /aws/lambda/ctd-transformer --endpoint-url http://localhost:4566
```

### View Step Functions execution history

```powershell
# Get execution ARN from run-local-pipeline.ps1 output
$execArn = "arn:aws:states:us-east-1:000000000000:execution:ctd-transformation-pipeline:exec-20251209-143022"

# View execution history
aws stepfunctions get-execution-history --execution-arn $execArn --endpoint-url http://localhost:4566
```

## Cleanup

```powershell
# Stop LocalStack
docker-compose down

# Full cleanup (removes all LocalStack data)
docker-compose down --volumes

# Remove Docker images
docker-compose down --rmi all --volumes
```

## Deployment to AWS

Once local testing works, deploy to AWS:

### 1. Build ZIP packages

```powershell
# Build Lambda function and layer ZIPs
.\build\build.ps1
```

This creates:
- `dist/lambda_function.zip` - Lambda handler
- `dist/lambda_layer.zip` - Dependencies and src/

### 2. Deploy to AWS

```powershell
# Upload function
aws lambda create-function \
  --function-name ctd-transformer \
  --runtime python3.12 \
  --role arn:aws:iam::YOUR_ACCOUNT:role/lambda-execution-role \
  --handler lambda_handler.lambda_handler \
  --zip-file fileb://dist/lambda_function.zip

# Create layer
aws lambda publish-layer-version \
  --layer-name ctd-transformer-dependencies \
  --zip-file fileb://dist/lambda_layer.zip \
  --compatible-runtimes python3.12

# Attach layer to function
aws lambda update-function-configuration \
  --function-name ctd-transformer \
  --layers arn:aws:lambda:REGION:ACCOUNT:layer:ctd-transformer-dependencies:1
```

### 3. Create Step Functions state machine

Use the same state machine definition from `init-localstack.ps1` but replace LocalStack ARNs with real AWS ARNs.

## Next Steps

1. ✅ **Test with real XML files** - Upload actual Parliamentary Archives data
2. ✅ **Add more transformers** - Create new transformer classes in `src/transformers/`
3. ✅ **Monitor executions** - View Step Functions console for execution history
4. ✅ **Set up CI/CD** - Automate deployment with GitHub Actions

## Python 3.12 Verification

LocalStack uses Python 3.12 for Lambda runtime. To verify:

```powershell
# Check Lambda runtime
aws lambda get-function --function-name ctd-transformer --endpoint-url http://localhost:4566 | ConvertFrom-Json | Select-Object -ExpandProperty Configuration | Select-Object Runtime
```

Should output: `python3.12`

## File Structure Reference

```
ctd-pa-aws-transformations/
├── docker-compose.yml           # Docker orchestration
├── Dockerfile.local            # Python 3.12 Lambda image
├── requirements-lambda.txt     # Minimal Lambda dependencies
├── lambda_handler.py           # Task-agnostic handler
├── local-orchestrator.ps1      # Step Functions simulator
├── src/
│   ├── storage.py              # S3/Local filesystem abstraction
│   ├── generic_transformer.py  # Transformation orchestrator
│   ├── transformers/           # Transformer plugins
│   │   ├── __init__.py         # TRANSFORMER_REGISTRY
│   │   ├── base.py
│   │   ├── xml_converter.py
│   │   ├── newline_to_p.py
│   │   ├── y_naming.py
│   │   └── replica_metadata.py
│   └── transformers.py         # Existing transformer implementations
├── test-data/
│   └── sample_file.xml         # Test XML file
└── local-s3-data/              # Local S3 simulation (auto-created)
    └── ctd-pa-elt-data-processing-bucket/
        ├── xml_input/
        └── processed/
```

## Questions?

See `LOCAL_TESTING.md` for detailed documentation.
