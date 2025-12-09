#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Initialize LocalStack with Lambda function and Step Functions state machine

.DESCRIPTION
    This script:
    1. Waits for LocalStack to be ready
    2. Creates S3 bucket
    3. Creates Lambda function from local code
    4. Creates IAM role for Lambda
    5. Creates Step Functions state machine
    6. Uploads test XML file
#>

param(
    [string]$LocalStackEndpoint = "http://localhost:4566",
    [string]$Region = "eu-west-2",
    [string]$BucketName = "ctd-pa-elt-data-processing-bucket",
    [string]$FunctionName = "ctd-transformer",
    [string]$StateMachineName = "ctd-transformation-pipeline"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "LocalStack Initialization" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Set AWS CLI to use LocalStack
$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION = $Region

$awsArgs = @(
    "--endpoint-url", $LocalStackEndpoint,
    "--region", $Region
)

# Wait for LocalStack to be ready
Write-Host "[1/7] Waiting for LocalStack..." -ForegroundColor Yellow
$maxRetries = 30
$retryCount = 0
$ready = $false

while (-not $ready -and $retryCount -lt $maxRetries) {
    try {
        $health = Invoke-RestMethod -Uri "$LocalStackEndpoint/_localstack/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($health.services.s3 -eq "available") {
            $ready = $true
            Write-Host "  ✓ LocalStack is ready" -ForegroundColor Green
        }
    }
    catch {
        $retryCount++
        Write-Host "  Waiting... (attempt $retryCount/$maxRetries)" -ForegroundColor Gray
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    Write-Host "  ✗ LocalStack failed to start" -ForegroundColor Red
    Write-Host "  Try: docker-compose up -d" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Create S3 bucket
Write-Host "[2/7] Creating S3 bucket..." -ForegroundColor Yellow
try {
    aws s3 mb "s3://$BucketName" @awsArgs 2>$null
    Write-Host "  ✓ Created bucket: $BucketName" -ForegroundColor Green
}
catch {
    Write-Host "  Bucket already exists" -ForegroundColor Gray
}

# Create folders in S3
aws s3api put-object --bucket $BucketName --key "xml_input/" --body "" @awsArgs | Out-Null
aws s3api put-object --bucket $BucketName --key "processed/" --body "" @awsArgs | Out-Null
Write-Host ""

# Create IAM role for Lambda
Write-Host "[3/7] Creating IAM role..." -ForegroundColor Yellow
$trustPolicy = @{
    Version = "2012-10-17"
    Statement = @(
        @{
            Effect = "Allow"
            Principal = @{
                Service = "lambda.amazonaws.com"
            }
            Action = "sts:AssumeRole"
        }
    )
} | ConvertTo-Json -Depth 10

$trustPolicyFile = New-TemporaryFile
$trustPolicy | Out-File -FilePath $trustPolicyFile -Encoding utf8

try {
    $roleArn = (aws iam create-role `
        --role-name lambda-execution-role `
        --assume-role-policy-document "file://$trustPolicyFile" `
        @awsArgs | ConvertFrom-Json).Role.Arn
    Write-Host "  ✓ Created role: lambda-execution-role" -ForegroundColor Green
}
catch {
    $roleArn = "arn:aws:iam::000000000000:role/lambda-execution-role"
    Write-Host "  Role already exists" -ForegroundColor Gray
}

Remove-Item $trustPolicyFile
Write-Host ""

# Package Lambda function (ZIP)
Write-Host "[4/7] Packaging Lambda function..." -ForegroundColor Yellow
$tempDir = New-TemporaryFile | ForEach-Object { Remove-Item $_; New-Item -ItemType Directory -Path $_ }
$zipFile = Join-Path $tempDir "function.zip"

# Copy Lambda handler and src folder
Copy-Item "lambda_handler.py" $tempDir
Copy-Item "src" $tempDir -Recurse

# Install dependencies to temp dir (minimal)
Write-Host "  Installing dependencies..." -ForegroundColor Gray
pip install -q -t $tempDir python-dotenv pyyaml 2>$null

# Create ZIP
Push-Location $tempDir
Compress-Archive -Path * -DestinationPath $zipFile -Force
Pop-Location

Write-Host "  ✓ Created function package" -ForegroundColor Green
Write-Host ""

# Create Lambda function
Write-Host "[5/7] Creating Lambda function..." -ForegroundColor Yellow
try {
    aws lambda create-function `
        --function-name $FunctionName `
        --runtime python3.12 `
        --role $roleArn `
        --handler lambda_handler.lambda_handler `
        --zip-file "fileb://$zipFile" `
        --timeout 300 `
        --memory-size 512 `
        --environment "Variables={CTD_LOG_LEVEL=INFO}" `
        @awsArgs | Out-Null
    Write-Host "  ✓ Created Lambda function: $FunctionName" -ForegroundColor Green
}
catch {
    Write-Host "  Updating existing function..." -ForegroundColor Gray
    aws lambda update-function-code `
        --function-name $FunctionName `
        --zip-file "fileb://$zipFile" `
        @awsArgs | Out-Null
    Write-Host "  ✓ Updated Lambda function: $FunctionName" -ForegroundColor Green
}

# Cleanup temp files
Remove-Item -Recurse -Force $tempDir
Write-Host ""

# Create Step Functions state machine
Write-Host "[6/7] Creating Step Functions state machine..." -ForegroundColor Yellow

$stateMachineDefinition = @"
{
  "Comment": "CTD Transformation Pipeline",
  "StartAt": "Transform_Step_1",
  "States": {
    "Transform_Step_1": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "$FunctionName",
        "Payload": {
          "bucket.$": "`$.bucket",
          "key.$": "`$.key",
          "transformation_index": 1,
          "transformation_config.$": "`$.transformation_config",
          "execution_id.$": "`$`$.Execution.Name"
        }
      },
      "ResultPath": "`$.step1_result",
      "ResultSelector": {
        "statusCode.$": "`$.Payload.statusCode",
        "output_key.$": "`$.Payload.output_key"
      },
      "Next": "Check_Step_1"
    },
    "Check_Step_1": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "`$.step1_result.statusCode",
          "NumericEquals": 200,
          "Next": "Transform_Step_2"
        }
      ],
      "Default": "Pipeline_Failed"
    },
    "Transform_Step_2": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "$FunctionName",
        "Payload": {
          "bucket.$": "`$.bucket",
          "key.$": "`$.key",
          "transformation_index": 2,
          "transformation_config.$": "`$.transformation_config",
          "execution_id.$": "`$`$.Execution.Name"
        }
      },
      "ResultPath": "`$.step2_result",
      "ResultSelector": {
        "statusCode.$": "`$.Payload.statusCode",
        "output_key.$": "`$.Payload.output_key"
      },
      "Next": "Check_Step_2"
    },
    "Check_Step_2": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "`$.step2_result.statusCode",
          "NumericEquals": 200,
          "Next": "Transform_Step_3"
        }
      ],
      "Default": "Pipeline_Failed"
    },
    "Transform_Step_3": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "$FunctionName",
        "Payload": {
          "bucket.$": "`$.bucket",
          "key.$": "`$.key",
          "transformation_index": 3,
          "transformation_config.$": "`$.transformation_config",
          "execution_id.$": "`$`$.Execution.Name"
        }
      },
      "ResultPath": "`$.step3_result",
      "ResultSelector": {
        "statusCode.$": "`$.Payload.statusCode",
        "output_key.$": "`$.Payload.output_key"
      },
      "Next": "Check_Step_3"
    },
    "Check_Step_3": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "`$.step3_result.statusCode",
          "NumericEquals": 200,
          "Next": "Pipeline_Success"
        }
      ],
      "Default": "Pipeline_Failed"
    },
    "Pipeline_Success": {
      "Type": "Succeed"
    },
    "Pipeline_Failed": {
      "Type": "Fail",
      "Error": "TransformationError",
      "Cause": "One or more transformation steps failed"
    }
  }
}
"@

$defFile = New-TemporaryFile
$stateMachineDefinition | Out-File -FilePath $defFile -Encoding utf8

try {
    $stateMachineArn = (aws stepfunctions create-state-machine `
        --name $StateMachineName `
        --definition "file://$defFile" `
        --role-arn $roleArn `
        @awsArgs | ConvertFrom-Json).stateMachineArn
    Write-Host "  ✓ Created state machine: $StateMachineName" -ForegroundColor Green
}
catch {
    Write-Host "  State machine already exists" -ForegroundColor Gray
    $stateMachineArn = "arn:aws:states:$Region:000000000000:stateMachine:$StateMachineName"
}

Remove-Item $defFile
Write-Host ""

# Upload test XML file
Write-Host "[7/7] Uploading test XML file..." -ForegroundColor Yellow
if (Test-Path "test-data\sample_file.xml") {
    aws s3 cp "test-data\sample_file.xml" "s3://$BucketName/xml_input/" @awsArgs | Out-Null
    Write-Host "  ✓ Uploaded: test-data\sample_file.xml" -ForegroundColor Green
} else {
    Write-Host "  ⚠ Test file not found: test-data\sample_file.xml" -ForegroundColor Yellow
}
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Resources created:" -ForegroundColor Cyan
Write-Host "  S3 Bucket:      $BucketName" -ForegroundColor White
Write-Host "  Lambda:         $FunctionName" -ForegroundColor White
Write-Host "  State Machine:  $StateMachineName" -ForegroundColor White
Write-Host ""
Write-Host "Next step:" -ForegroundColor Cyan
Write-Host "  Run pipeline:   .\run-local-pipeline.ps1" -ForegroundColor White
Write-Host ""
