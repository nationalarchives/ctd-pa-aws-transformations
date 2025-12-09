# Local Testing Guide

This guide explains how to run the transformation pipeline locally using Docker, simulating AWS Step Functions orchestration.

## Prerequisites

- Docker Desktop installed and running
- PowerShell 5.1+ or PowerShell Core 7+
- Python 3.12 (for local development)

## Local S3 Bucket Structure

The local filesystem simulates S3 with this structure:

```
local-s3-data/
└── ctd-pa-elt-data-processing-bucket/
    ├── xml_input/                          # Input XML files
    │   └── sample_file.xml
    └── processed/                          # Transformation outputs
        └── <execution_id>/                 # Each run gets unique ID
            ├── step_1/                     # Step 1: XML → JSON
            │   ├── sample_file.json
            │   └── _SUCCESS
            ├── step_2/                     # Step 2: Newline to <p>
            │   ├── sample_file.json
            │   └── _SUCCESS
            └── step_3/                     # Step 3: Y-naming
                ├── sample_file.json
                └── _SUCCESS
```

## Quick Start

### 1. Build and Start Containers

```powershell
# Build the Lambda Docker image
docker-compose build

# Start LocalStack (S3) and Lambda
docker-compose up -d

# Check containers are running
docker-compose ps
```

### 2. Run the Orchestrator

```powershell
# Run with default test file
.\local-orchestrator.ps1

# Run with custom XML file
.\local-orchestrator.ps1 -TestFile "path\to\your\file.xml"

# Run with custom execution ID
.\local-orchestrator.ps1 -ExecutionId "my-test-001"
```

### 3. Check Results

```powershell
# View output files
Get-ChildItem .\local-s3-data\ctd-pa-elt-data-processing-bucket\processed\ -Recurse

# View specific execution
$execId = "local-exec-20251205-143022"
Get-Content ".\local-s3-data\ctd-pa-elt-data-processing-bucket\processed\$execId\step_3\sample_file.json"
```

## How It Works

### 1. Local Orchestrator (`local-orchestrator.ps1`)

Simulates AWS Step Functions by:
- Creating local S3 bucket structure
- Uploading test XML to `xml_input/`
- Calling Lambda for each transformation step (1, 2, 3)
- Checking status codes (200 = success, 202 = waiting, 500 = error)
- Verifying `_SUCCESS` markers

### 2. Lambda Container

Runs locally using AWS Lambda Runtime Interface Emulator:
- Listens on `http://localhost:9000`
- Receives events via POST requests
- Reads/writes to local filesystem (simulating S3)
- Returns status and output keys

### 3. Transformation Flow

```
XML Input (xml_input/sample_file.xml)
    ↓
[Step 1: Convert XML → JSON]
    → processed/<exec_id>/step_1/sample_file.json
    → processed/<exec_id>/step_1/_SUCCESS
    ↓
[Step 2: Newline to <p>]
    → Reads from step_1/
    → processed/<exec_id>/step_2/sample_file.json
    → processed/<exec_id>/step_2/_SUCCESS
    ↓
[Step 3: Y-naming]
    → Reads from step_2/
    → processed/<exec_id>/step_3/sample_file.json
    → processed/<exec_id>/step_3/_SUCCESS
```

## Testing Individual Steps

You can test each step independently:

```powershell
# Test Step 1 only
$event = @{
    bucket = "ctd-pa-elt-data-processing-bucket"
    key = "xml_input/sample_file.xml"
    transformation_index = 1
    transformation_config = @{
        "1" = @{
            operation = "convert"
            target_fields = @()
            parameters = @{}
        }
    }
    execution_id = "manual-test-001"
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "http://localhost:9000/2015-03-31/functions/function/invocations" `
    -Method Post `
    -ContentType "application/json" `
    -Body $event
```

## Troubleshooting

### Lambda not responding

```powershell
# Check container logs
docker-compose logs lambda

# Restart containers
docker-compose restart
```

### File not found errors

```powershell
# Check local S3 structure
Get-ChildItem .\local-s3-data -Recurse

# Ensure xml_input directory exists
New-Item -ItemType Directory -Path ".\local-s3-data\ctd-pa-elt-data-processing-bucket\xml_input" -Force
```

### Import errors

```powershell
# Rebuild Lambda image
docker-compose build --no-cache lambda
docker-compose up -d
```

## Cleanup

```powershell
# Stop containers
docker-compose down

# Remove local S3 data
Remove-Item -Recurse -Force .\local-s3-data\ctd-pa-elt-data-processing-bucket\processed\*

# Full cleanup (including images)
docker-compose down --rmi all --volumes
```

## Next Steps

Once local testing works:
1. Push Docker image to AWS ECR
2. Create Lambda function from container image
3. Set up Step Functions state machine
4. Connect S3 event notifications to trigger pipeline
