#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run transformation pipeline using LocalStack Step Functions

.DESCRIPTION
    Triggers the Step Functions state machine to process an XML file through all transformation steps

.PARAMETER InputFile
    XML file to process (relative to xml_input/ in S3)

.PARAMETER ExecutionName
    Name for this execution (default: timestamp-based)

.EXAMPLE
    .\run-local-pipeline.ps1 -InputFile "sample_file.xml"
#>

param(
    [string]$InputFile = "sample_file.xml",
    [string]$ExecutionName = "exec-$(Get-Date -Format 'yyyyMMdd-HHmmss')",
    [string]$LocalStackEndpoint = "http://localhost:4566",
    [string]$Region = "us-east-1",
    [string]$BucketName = "ctd-pa-elt-data-processing-bucket",
    [string]$StateMachineName = "ctd-transformation-pipeline"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Step Functions Pipeline Execution" -ForegroundColor Cyan
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

# Check LocalStack is running
Write-Host "Checking LocalStack..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "$LocalStackEndpoint/_localstack/health" -TimeoutSec 5
    if ($health.services.stepfunctions -ne "available") {
        Write-Host "  ✗ Step Functions not available" -ForegroundColor Red
        Write-Host "  Run: .\init-localstack.ps1" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  ✓ LocalStack is ready" -ForegroundColor Green
}
catch {
    Write-Host "  ✗ LocalStack is not running" -ForegroundColor Red
    Write-Host "  Run: docker-compose up -d" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Check if input file exists in S3
Write-Host "Checking input file..." -ForegroundColor Yellow
$s3Key = "xml_input/$InputFile"
try {
    aws s3 ls "s3://$BucketName/$s3Key" @awsArgs | Out-Null
    Write-Host "  ✓ Found: s3://$BucketName/$s3Key" -ForegroundColor Green
}
catch {
    Write-Host "  ✗ File not found: s3://$BucketName/$s3Key" -ForegroundColor Red
    Write-Host "  Upload with: aws s3 cp test-data\$InputFile s3://$BucketName/xml_input/ --endpoint-url $LocalStackEndpoint" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Prepare execution input
$executionInput = @{
    bucket = $BucketName
    key = $s3Key
    transformation_config = @{
        "1" = @{
            operation = "convert"
            target_fields = @()
            parameters = @{}
            description = "Convert XML to JSON format"
        }
        "2" = @{
            operation = "newline_to_p"
            target_fields = @("scopecontent.p")
            parameters = @{}
            description = "Replace newline characters with <p> tags"
        }
        "3" = @{
            operation = "y_naming"
            target_fields = @("department")
            parameters = @{}
            description = "Add 'Y' prefix to department codes"
        }
    }
} | ConvertTo-Json -Depth 10 -Compress

# Get state machine ARN
$stateMachineArn = "arn:aws:states:${Region}:000000000000:stateMachine:$StateMachineName"

# Start execution
Write-Host "Starting Step Functions execution..." -ForegroundColor Yellow
Write-Host "  Execution Name: $ExecutionName" -ForegroundColor Gray
Write-Host "  Input File: $s3Key" -ForegroundColor Gray
Write-Host ""

try {
    $execution = aws stepfunctions start-execution `
        --state-machine-arn $stateMachineArn `
        --name $ExecutionName `
        --input $executionInput `
        @awsArgs | ConvertFrom-Json

    $executionArn = $execution.executionArn
    Write-Host "  ✓ Started execution" -ForegroundColor Green
    Write-Host "  Execution ARN: $executionArn" -ForegroundColor Gray
}
catch {
    Write-Host "  ✗ Failed to start execution" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
Write-Host ""

# Poll execution status
Write-Host "Monitoring execution..." -ForegroundColor Yellow
Write-Host ""

$maxWaitTime = 300  # 5 minutes
$startTime = Get-Date
$status = "RUNNING"

while ($status -eq "RUNNING" -and ((Get-Date) - $startTime).TotalSeconds -lt $maxWaitTime) {
    Start-Sleep -Seconds 2
    
    try {
        $execDetails = aws stepfunctions describe-execution `
            --execution-arn $executionArn `
            @awsArgs | ConvertFrom-Json
        
        $status = $execDetails.status
        
        Write-Host "`r  Status: $status" -NoNewline -ForegroundColor $(
            if ($status -eq "RUNNING") { "Yellow" }
            elseif ($status -eq "SUCCEEDED") { "Green" }
            else { "Red" }
        )
    }
    catch {
        Write-Host "`r  Error checking status" -ForegroundColor Red
        break
    }
}

Write-Host ""
Write-Host ""

# Show final results
if ($status -eq "SUCCEEDED") {
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Pipeline Completed Successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    
    # List outputs
    Write-Host "Outputs:" -ForegroundColor Cyan
    $outputPrefix = "processed/$ExecutionName/"
    
    $outputs = aws s3 ls "s3://$BucketName/$outputPrefix" --recursive @awsArgs
    if ($outputs) {
        $outputs | ForEach-Object {
            if ($_ -match '\s+(\S+)$') {
                $key = $matches[1]
                Write-Host "  s3://$BucketName/$key" -ForegroundColor White
            }
        }
    }
    
    Write-Host ""
    Write-Host "View final output:" -ForegroundColor Cyan
    Write-Host "  aws s3 cp s3://$BucketName/${outputPrefix}step_3/$(Split-Path $InputFile -LeafBase).json - --endpoint-url $LocalStackEndpoint" -ForegroundColor Gray
    
} elseif ($status -eq "FAILED" -or $status -eq "TIMED_OUT" -or $status -eq "ABORTED") {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Pipeline Failed!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Status: $status" -ForegroundColor Red
    
    if ($execDetails.error) {
        Write-Host "Error: $($execDetails.error)" -ForegroundColor Red
    }
    if ($execDetails.cause) {
        Write-Host "Cause: $($execDetails.cause)" -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "View execution history:" -ForegroundColor Yellow
    Write-Host "  aws stepfunctions get-execution-history --execution-arn $executionArn --endpoint-url $LocalStackEndpoint" -ForegroundColor Gray
    
} else {
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host "Execution Timeout" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Execution is still running after $maxWaitTime seconds" -ForegroundColor Yellow
    Write-Host "Check status with:" -ForegroundColor Yellow
    Write-Host "  aws stepfunctions describe-execution --execution-arn $executionArn --endpoint-url $LocalStackEndpoint" -ForegroundColor Gray
}

Write-Host ""
