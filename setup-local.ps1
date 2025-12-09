#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Setup script for local Docker testing environment

.DESCRIPTION
    Creates necessary directories and verifies setup for local Lambda testing
#>

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Local Development Environment Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Docker is running
Write-Host "[1/5] Checking Docker..." -ForegroundColor Yellow
try {
    $null = docker ps 2>&1
    Write-Host "  ✓ Docker is running" -ForegroundColor Green
}
catch {
    Write-Host "  ✗ Docker is not running" -ForegroundColor Red
    Write-Host "  Please start Docker Desktop and try again" -ForegroundColor Yellow
    exit 1
}
Write-Host ""

# Create local S3 structure
Write-Host "[2/5] Creating local S3 bucket structure..." -ForegroundColor Yellow
$bucketRoot = ".\local-s3-data\ctd-pa-elt-data-processing-bucket"
$xmlInput = Join-Path $bucketRoot "xml_input"
$processed = Join-Path $bucketRoot "processed"

foreach ($dir in @($xmlInput, $processed)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  Created: $dir" -ForegroundColor Green
    } else {
        Write-Host "  Exists: $dir" -ForegroundColor Gray
    }
}
Write-Host ""

# Check test data exists
Write-Host "[3/5] Checking test data..." -ForegroundColor Yellow
if (-not (Test-Path "test-data\sample_file.xml")) {
    Write-Host "  Test file already exists: test-data\sample_file.xml" -ForegroundColor Gray
} else {
    Write-Host "  ✓ Test file exists: test-data\sample_file.xml" -ForegroundColor Green
}
Write-Host ""

# Check Docker Compose file
Write-Host "[4/5] Verifying Docker Compose configuration..." -ForegroundColor Yellow
if (Test-Path "docker-compose.yml") {
    Write-Host "  ✓ docker-compose.yml found" -ForegroundColor Green
} else {
    Write-Host "  ✗ docker-compose.yml not found" -ForegroundColor Red
    exit 1
}

if (Test-Path "Dockerfile.local") {
    Write-Host "  ✓ Dockerfile.local found" -ForegroundColor Green
} else {
    Write-Host "  ✗ Dockerfile.local not found" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Verify Python files
Write-Host "[5/5] Verifying source files..." -ForegroundColor Yellow
$requiredFiles = @(
    "lambda_handler.py",
    "src\storage.py",
    "src\generic_transformer.py",
    "src\transformers\__init__.py",
    "src\transformers\base.py",
    "src\transformers\xml_converter.py",
    "requirements-lambda.txt"
)

$allFilesExist = $true
foreach ($file in $requiredFiles) {
    if (Test-Path $file) {
        Write-Host "  ✓ $file" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $file" -ForegroundColor Red
        $allFilesExist = $false
    }
}

if (-not $allFilesExist) {
    Write-Host ""
    Write-Host "Some required files are missing!" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Build Docker image:    docker-compose build" -ForegroundColor White
Write-Host "  2. Start containers:      docker-compose up -d" -ForegroundColor White
Write-Host "  3. Run test pipeline:     .\local-orchestrator.ps1" -ForegroundColor White
Write-Host ""
Write-Host "See QUICKSTART_LOCAL.md for detailed instructions" -ForegroundColor Gray
Write-Host ""
