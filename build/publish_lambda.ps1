$ErrorActionPreference = "Stop"

$FUNCTION_NAME = "ctd-pa-etl-data-processing-lambda"
$LAYER_NAME = "ctd-pa-dependencies"
$PROFILE = "ctd-pa-discovery"
$RUNTIME = "python3.12"
$HANDLER = "run_pipeline.lambda_handler"
$ROLE_ARN = "arn:aws:iam::361769582662:role/ctd-pa-etl-data-processing-role"

# Check if build artifacts exist
if (-Not (Test-Path "..\dist\lambda_layer.zip")) {
    Write-Host "❌ Error: lambda_layer.zip not found in ../dist/" -ForegroundColor Red
    Write-Host "Run build.ps1 first to create the packages." -ForegroundColor Yellow
    exit 1
}

if (-Not (Test-Path "..\dist\lambda_function.zip")) {
    Write-Host "❌ Error: lambda_function.zip not found in ../dist/" -ForegroundColor Red
    Write-Host "Run build.ps1 first to create the packages." -ForegroundColor Yellow
    exit 1
}

Write-Host "=== Deploying Lambda Function and Layer ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Publish layer version
Write-Host "[1/3] Publishing Lambda layer..." -ForegroundColor Cyan
$layerOutput = aws lambda publish-layer-version `
  --layer-name $LAYER_NAME `
  --description "Python dependencies and src code for CTD PA transformations" `
  --zip-file fileb://../dist/lambda_layer.zip `
  --compatible-runtimes $RUNTIME `
  --profile $PROFILE | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to publish layer" -ForegroundColor Red
    exit 1
}

$layerArn = $layerOutput.LayerVersionArn
$layerVersion = $layerOutput.Version
Write-Host "✅ Layer published: version $layerVersion" -ForegroundColor Green
Write-Host "   ARN: $layerArn" -ForegroundColor Gray
Write-Host ""

# Step 1.5: Put hard-coded TRANS_CONFIG into SSM Parameter Store
Write-Host "[1.5/3] Putting TRANS_CONFIG into SSM (hard-coded)" -ForegroundColor Cyan
$transConfigValue = '{"tasks":{"newline_to_p":{"params":{"match":"\n","replace":"<p>"},"target_columns":null},"y_naming":{"target_columns":null}},"record_level_dirs":true,"record_level_mapping":{"1":"01 FONDS","2":"02 SUB-FONDS","3":"03 SUB-SUB-FONDS","4":"04 SUB-SUB-SUB-FONDS","5":"05 SUB-SUB-SUB-SUB-FONDS","6":"06 SERIES","7":"07 SUB-SERIES","8":"08 SUB-SUB-SERIES","9":"09 FILE","10":"10 ITEM"}}'

$oldEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    aws ssm put-parameter --name "/ctd-pa/TRANS_CONFIG" --type String --value $transConfigValue --overwrite --profile $PROFILE | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ TRANS_CONFIG stored in SSM" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Failed to store TRANS_CONFIG in SSM (exit $LASTEXITCODE)" -ForegroundColor Yellow
    }
} finally {
    $ErrorActionPreference = $oldEap
}

# Step 2: Check if function exists
Write-Host "[2/3] Checking if function exists..." -ForegroundColor Cyan
$functionExists = $false
try {
    aws lambda get-function --function-name $FUNCTION_NAME --profile $PROFILE 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $functionExists = $true
        Write-Host "✅ Function exists, will update" -ForegroundColor Green
    }
} catch {
    $functionExists = $false
}

if (-not $functionExists) {
    Write-Host "INFO:  Function does not exist, will create" -ForegroundColor Yellow
}
Write-Host ""

# Step 3: Create or update function
Write-Host "[3/3] Deploying function code..." -ForegroundColor Cyan

# Helper: wait for any in-progress Lambda update to finish
function Wait-Lambda-UpdateComplete {
    param(
        [string]$Name,
        [string]$Profile,
        [int]$TimeoutSec = 300,
        [int]$Interval = 5
    )
    $end = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $end) {
        $status = aws lambda get-function-configuration --function-name $Name --profile $Profile --query "LastUpdateStatus" --output text 2>$null
        if ($LASTEXITCODE -ne 0) { Start-Sleep -Seconds $Interval; continue }
        if ($status -ne "InProgress") { return $status }
        Write-Host "   Waiting for previous lambda update to complete..." -ForegroundColor Yellow
        Start-Sleep -Seconds $Interval
    }
    throw "Timeout waiting for Lambda update to complete"
}

# Use single-quoted here-string to avoid any parsing issues with braces/commas/quotes
$envVars = @'
Variables={RUN_MODE=remote_s3,S3_OUTPUT_DIR=json_outputs,S3_USE_LEVEL_SUBFOLDERS=true,TEST_MODE=false,S3_TEST_FOLDER=testing,CTD_LOG_LEVEL=INFO,MERGE_XML=false,TRANSFER_REGISTER_FILENAME=axiell_transfer_register.json,REPLICA_METADATA_PREFIX=metadata,PROGRESS_VERBOSE=false}
'@

if ($functionExists) {
    # Update existing function code
    aws lambda update-function-code `
      --function-name $FUNCTION_NAME `
      --zip-file fileb://../dist/lambda_function.zip `
      --profile $PROFILE | Out-Null
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to update function code" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Function code updated" -ForegroundColor Green
    
    # Update function configuration (layer + environment variables)
    Write-Host "   Updating configuration..." -ForegroundColor Gray

    $attempts = 0
    $maxAttempts = 3
    do {
        $attempts++
        $oldEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $result = & aws lambda update-function-configuration `
                --function-name $FUNCTION_NAME `
                --handler $HANDLER `
                --layers $layerArn `
                --environment $envVars `
                --profile $PROFILE 2>&1
        } finally {
            $ErrorActionPreference = $oldEap
        }
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Configuration updated (layer + environment variables)" -ForegroundColor Green
            break
        }

        if ($result -match "ResourceConflictException" -or $result -match "ResourceInUseException" -or $result -match "Conflict") {
            Write-Host "⚠️  Update conflict detected (attempt $attempts). Waiting and retrying..." -ForegroundColor Yellow
            Wait-Lambda-UpdateComplete -Name $FUNCTION_NAME -Profile $PROFILE -TimeoutSec 300 -Interval 5
            continue
        } else {
            Write-Host "❌ Failed to update configuration: $result" -ForegroundColor Red
            exit 1
        }
    } while ($attempts -lt $maxAttempts)
} else {
    # Create new function
    aws lambda create-function `
      --function-name $FUNCTION_NAME `
      --runtime $RUNTIME `
      --role $ROLE_ARN `
      --handler $HANDLER `
      --zip-file fileb://../dist/lambda_function.zip `
      --layers $layerArn `
      --timeout 900 `
      --memory-size 512 `
      --environment $envVars `
      --profile $PROFILE | Out-Null
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to create function" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Function created successfully" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Deployment Complete ===" -ForegroundColor Green
Write-Host "Function: $FUNCTION_NAME" -ForegroundColor White
Write-Host "Layer: $LAYER_NAME (version $layerVersion)" -ForegroundColor White
Write-Host ""
Write-Host '⚠️  Remember: TRANS_CONFIG should be set in SSM Parameter Store at:' -ForegroundColor Yellow
Write-Host '   /ctd-pa/TRANS_CONFIG' -ForegroundColor Gray