#!/usr/bin/env bash
# Bash script to deploy Lambda function and layer to AWS
# WARNING: This file contains AWS-specific information and should NOT be committed to Git

set -euo pipefail

FUNCTION_NAME="ctd-pa-etl-data-processing-lambda"
LAYER_NAME="ctd-pa-dependencies"
PROFILE="ctd-pa-discovery"
RUNTIME="python3.12"
HANDLER="run_pipeline.lambda_handler"
ROLE_ARN="arn:aws:iam::361769582662:role/ctd-pa-etl-data-processing-role"

# Check if build artifacts exist
if [ ! -f "../dist/lambda_layer.zip" ]; then
    echo "❌ Error: lambda_layer.zip not found in ../dist/"
    echo "Run build.sh first to create the packages."
    exit 1
fi

if [ ! -f "../dist/lambda_function.zip" ]; then
    echo "❌ Error: lambda_function.zip not found in ../dist/"
    echo "Run build.sh first to create the packages."
    exit 1
fi

echo "=== Deploying Lambda Function and Layer ==="
echo ""

# Step 1: Publish layer version
echo "[1/3] Publishing Lambda layer..."
layer_output=$(aws lambda publish-layer-version \
  --layer-name "$LAYER_NAME" \
  --description "Python dependencies and src code for CTD PA transformations" \
  --zip-file fileb://../dist/lambda_layer.zip \
  --compatible-runtimes "$RUNTIME" \
  --profile "$PROFILE")

layer_arn=$(echo "$layer_output" | grep -o '"LayerVersionArn": "[^"]*' | cut -d'"' -f4)
layer_version=$(echo "$layer_output" | grep -o '"Version": [0-9]*' | grep -o '[0-9]*')

if [ -z "$layer_arn" ]; then
    echo "❌ Failed to publish layer"
    exit 1
fi

echo "✅ Layer published: version $layer_version"
echo "   ARN: $layer_arn"
echo ""

echo "[1.5/3] Putting TRANS_CONFIG into SSM (hard-coded)"
trans_config_value='{"tasks":{"newline_to_p":{"params":{"match":"\n","replace":"<p>"},"target_columns":null},"y_naming":{"target_columns":null}},"record_level_dirs":true,"record_level_mapping":{"1":"01 FONDS","2":"02 SUB-FONDS","3":"03 SUB-SUB-FONDS","4":"04 SUB-SUB-SUB-FONDS","5":"05 SUB-SUB-SUB-SUB-FONDS","6":"06 SERIES","7":"07 SUB-SERIES","8":"08 SUB-SUB-SERIES","9":"09 FILE","10":"10 ITEM"}}'

value=$(printf "%s" "$trans_config_value" | tr -d '\r')
if aws ssm put-parameter --name "/ctd-pa/TRANS_CONFIG" --type String --value "$value" --overwrite --profile "$PROFILE" >/dev/null 2>/tmp/aws_err; then
  echo "✅ TRANS_CONFIG stored in SSM"
else
  echo "⚠️  Failed to store TRANS_CONFIG in SSM: $(cat /tmp/aws_err)"
fi

# Step 2: Check if function exists
echo "[2/3] Checking if function exists..."
if aws lambda get-function --function-name "$FUNCTION_NAME" --profile "$PROFILE" &>/dev/null; then
    function_exists=true
    echo "✅ Function exists, will update"
else
    function_exists=false
    echo "ℹ️  Function does not exist, will create"
fi
echo ""

# Step 3: Create or update function
echo "[3/3] Deploying function code..."

if [ "$function_exists" = true ]; then
    # Update existing function code
    aws lambda update-function-code \
      --function-name "$FUNCTION_NAME" \
      --zip-file fileb://../dist/lambda_function.zip \
      --profile "$PROFILE" > /dev/null
    
    echo "✅ Function code updated"
    
    # Update function configuration (layer + environment variables)
    echo "   Updating configuration..."
    aws lambda update-function-configuration \
      --function-name "$FUNCTION_NAME" \
      --handler "$HANDLER" \
      --layers "$layer_arn" \
      --environment "Variables={RUN_MODE=remote_s3,S3_OUTPUT_DIR=json_outputs,S3_USE_LEVEL_SUBFOLDERS=true,TEST_MODE=false,S3_TEST_FOLDER=testing,CTD_LOG_LEVEL=INFO,MERGE_XML=false,TRANSFER_REGISTER_FILENAME=axiell_transfer_register.json,REPLICA_METADATA_PREFIX=metadata,PROGRESS_VERBOSE=false}" \
      --profile "$PROFILE" > /dev/null
    
    echo "✅ Configuration updated (layer + environment variables)"
else
    # Create new function
    aws lambda create-function \
      --function-name "$FUNCTION_NAME" \
      --runtime "$RUNTIME" \
    wait_for_lambda_ready() {
      local name="$1"
      local profile="$2"
      local timeout=${3:-300}
      local interval=${4:-5}
      local start=$(date +%s)
      while true; do
        status=$(aws lambda get-function-configuration --function-name "$name" --profile "$profile" --query 'LastUpdateStatus' --output text 2>/dev/null || echo "UNKNOWN")
        if [ "$status" != "InProgress" ]; then
          return 0
        fi
        now=$(date +%s)
        if [ $((now - start)) -gt $timeout ]; then
          echo "Timeout waiting for lambda update to finish"
          return 1
        fi
        echo "   Waiting for previous lambda update to complete..."
        sleep $interval
      done
    }
      --role "$ROLE_ARN" \
      --handler "$HANDLER" \
      --zip-file fileb://../dist/lambda_function.zip \
      --handler "$HANDLER" \
      --layers "$layer_arn" \
      --timeout 900 \
      --memory-size 512 \
      --environment "Variables={RUN_MODE=remote_s3,S3_OUTPUT_DIR=json_outputs,S3_USE_LEVEL_SUBFOLDERS=true,TEST_MODE=false,S3_TEST_FOLDER=testing,CTD_LOG_LEVEL=INFO,MERGE_XML=false,TRANSFER_REGISTER_FILENAME=axiell_transfer_register.json,REPLICA_METADATA_PREFIX=metadata,PROGRESS_VERBOSE=false}" \
      --profile "$PROFILE" > /dev/null
    
    echo "✅ Function created successfully"
fi

echo ""
echo "=== Deployment Complete ==="
echo "Function: $FUNCTION_NAME"
echo "Layer: $LAYER_NAME (version $layer_version)"
echo ""
echo "⚠️  Remember: TRANS_CONFIG should be set in SSM Parameter Store at:"
echo "   /ctd-pa/TRANS_CONFIG"
