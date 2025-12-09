#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Local Step Functions orchestrator - simulates Step Functions calling Lambda for each transformation step

.DESCRIPTION
    This script mimics AWS Step Functions behavior by:
    1. Setting up local S3 bucket structure
    2. Uploading test XML file
    3. Calling Lambda for each transformation step
    4. Checking for _SUCCESS markers
    5. Verifying outputs

.PARAMETER TestFile
    Path to the test XML file to process

.PARAMETER ExecutionId
    Unique execution ID for this run (default: timestamp-based)

.EXAMPLE
    .\local-orchestrator.ps1 -TestFile "test-data/sample.xml"
#>

param(
    [string]$TestFile = "test-data/sample_file.xml",
    [string]$ExecutionId = "local-exec-$(Get-Date -Format 'yyyyMMdd-HHmmss')",
    [string]$LambdaUrl = "http://localhost:9000/2015-03-31/functions/function/invocations",
    [string]$LocalS3Root = "./local-s3-data"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Local Step Functions Orchestrator" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$bucket = "ctd-pa-elt-data-processing-bucket"
$transformationConfig = @{
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

# Step 0: Setup local S3 structure
Write-Host "[Step 0] Setting up local S3 bucket structure..." -ForegroundColor Yellow

$bucketPath = Join-Path $LocalS3Root $bucket
$xmlInputPath = Join-Path $bucketPath "xml_input"
$processedPath = Join-Path $bucketPath "processed"

# Create directory structure
@($xmlInputPath, $processedPath) | ForEach-Object {
    if (-not (Test-Path $_)) {
        New-Item -ItemType Directory -Path $_ -Force | Out-Null
        Write-Host "  Created: $_" -ForegroundColor Green
    }
}

# Copy test XML file to xml_input
if (-not (Test-Path $TestFile)) {
    Write-Host "ERROR: Test file not found: $TestFile" -ForegroundColor Red
    Write-Host "Please create a test XML file or specify a valid path" -ForegroundColor Red
    exit 1
}

$xmlFileName = Split-Path $TestFile -Leaf
$destinationXml = Join-Path $xmlInputPath $xmlFileName
Copy-Item $TestFile $destinationXml -Force
Write-Host "  Uploaded: $TestFile -> xml_input/$xmlFileName" -ForegroundColor Green
Write-Host ""

# Lambda invocation function
function Invoke-LocalLambda {
    param(
        [int]$TransformationIndex,
        [string]$InputKey,
        [hashtable]$Config,
        [string]$ExecId
    )

    $event = @{
        bucket = $bucket
        key = $InputKey
        transformation_index = $TransformationIndex
        transformation_config = $Config
        execution_id = $ExecId
    }

    $eventJson = $event | ConvertTo-Json -Depth 10
    
    Write-Host "[Step $TransformationIndex] Invoking Lambda..." -ForegroundColor Yellow
    Write-Host "  Operation: $($Config[$TransformationIndex.ToString()].operation)" -ForegroundColor Gray
    
    try {
        $response = Invoke-RestMethod -Uri $LambdaUrl `
            -Method Post `
            -ContentType "application/json" `
            -Body $eventJson `
            -TimeoutSec 300

        Write-Host "  Status: $($response.statusCode)" -ForegroundColor $(if ($response.statusCode -eq 200) { "Green" } else { "Red" })
        
        if ($response.statusCode -eq 200) {
            Write-Host "  Output: $($response.output_key)" -ForegroundColor Green
            Write-Host "  Success Marker: $($response.success_marker)" -ForegroundColor Green
        } elseif ($response.statusCode -eq 202) {
            Write-Host "  Message: $($response.message)" -ForegroundColor Yellow
        } else {
            Write-Host "  Error: $($response.error)" -ForegroundColor Red
        }

        Write-Host ""
        return $response
    }
    catch {
        Write-Host "  ERROR: Failed to invoke Lambda" -ForegroundColor Red
        Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
        Write-Host ""
        return $null
    }
}

# Wait for Lambda to be ready
Write-Host "Checking if Lambda is ready..." -ForegroundColor Yellow
$maxRetries = 10
$retryCount = 0
$lambdaReady = $false

while (-not $lambdaReady -and $retryCount -lt $maxRetries) {
    try {
        $testEvent = @{ test = "ping" } | ConvertTo-Json
        $null = Invoke-RestMethod -Uri $LambdaUrl -Method Post -Body $testEvent -TimeoutSec 5 -ErrorAction SilentlyContinue
        $lambdaReady = $true
        Write-Host "  Lambda is ready!" -ForegroundColor Green
    }
    catch {
        $retryCount++
        Write-Host "  Waiting for Lambda... (attempt $retryCount/$maxRetries)" -ForegroundColor Gray
        Start-Sleep -Seconds 2
    }
}

if (-not $lambdaReady) {
    Write-Host "ERROR: Lambda is not responding. Make sure Docker containers are running:" -ForegroundColor Red
    Write-Host "  docker-compose up -d" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Execute transformation pipeline
$initialKey = "xml_input/$xmlFileName"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Transformation Pipeline" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Execution ID: $ExecutionId" -ForegroundColor Cyan
Write-Host "Input File: $initialKey" -ForegroundColor Cyan
Write-Host ""

# Step 1: Convert XML to JSON
$step1Result = Invoke-LocalLambda -TransformationIndex 1 -InputKey $initialKey -Config $transformationConfig -ExecId $ExecutionId

if (-not $step1Result -or $step1Result.statusCode -ne 200) {
    Write-Host "Pipeline FAILED at Step 1" -ForegroundColor Red
    exit 1
}

# Step 2: Newline to <p>
$step2Result = Invoke-LocalLambda -TransformationIndex 2 -InputKey $initialKey -Config $transformationConfig -ExecId $ExecutionId

if (-not $step2Result -or $step2Result.statusCode -ne 200) {
    Write-Host "Pipeline FAILED at Step 2" -ForegroundColor Red
    exit 1
}

# Step 3: Y naming
$step3Result = Invoke-LocalLambda -TransformationIndex 3 -InputKey $initialKey -Config $transformationConfig -ExecId $ExecutionId

if (-not $step3Result -or $step3Result.statusCode -ne 200) {
    Write-Host "Pipeline FAILED at Step 3" -ForegroundColor Red
    exit 1
}

# Summary
Write-Host "========================================" -ForegroundColor Green
Write-Host "Pipeline Completed Successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Results:" -ForegroundColor Cyan
Write-Host "  Execution ID: $ExecutionId" -ForegroundColor White
Write-Host "  Step 1 Output: $($step1Result.output_key)" -ForegroundColor White
Write-Host "  Step 2 Output: $($step2Result.output_key)" -ForegroundColor White
Write-Host "  Step 3 Output: $($step3Result.output_key)" -ForegroundColor White
Write-Host ""
Write-Host "Check outputs in: $processedPath/$ExecutionId/" -ForegroundColor Cyan
Write-Host ""
