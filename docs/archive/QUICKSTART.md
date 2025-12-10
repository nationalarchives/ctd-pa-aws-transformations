# Quick Reference - Lambda Setup

## Quick Start Commands

### Build and Deploy
```powershell
# One-command deployment (automated)
.\deploy-lambda.ps1 -Region us-east-1 -Environment dev

# Or step-by-step with SAM
sam build
sam deploy --guided
```

### Test Lambda
```powershell
# Test with sample event
aws lambda invoke `
    --function-name ctd-pa-transformation-dev `
    --payload (Get-Content test-event.json -Raw) `
    --cli-binary-format raw-in-base64-out `
    response.json
```

### View Logs
```powershell
# Real-time logs
aws logs tail /aws/lambda/ctd-pa-transformation-dev --follow
```

## File Quick Reference

| File | Purpose |
|------|---------|
| `template.yaml` | SAM infrastructure template |
| `lambda_handler.py` | Lambda entry point for Step Functions |
| `Dockerfile` | Docker build configuration |
| `deploy-lambda.ps1` | Automated deployment script |
| `samconfig.toml` | SAM CLI configuration |
| `test-event.json` | Sample test event |
| `DEPLOYMENT.md` | Full deployment guide |
| `LAMBDA_SETUP.md` | Architecture documentation |

## Lambda Event Format

```json
{
  "bucket": "bucket-name",
  "key": "path/to/file.xml",
  "transformation_index": 1,
  "transformation_config": {
    "1": {"name": "convert_xml_to_json", "enabled": true},
    "2": {"name": "replace_newline_with_p", "enabled": true},
    "3": {"name": "add_y_to_department_codes", "enabled": true}
  },
  "execution_id": "exec-id"
}
```

## Transformation Index

| Index | Transformation | Description |
|-------|---------------|-------------|
| 1 | convert_xml_to_json | XML → JSON conversion |
| 2 | replace_newline_with_p | Newline → `<p>` tags |
| 3 | add_y_to_department_codes | Add 'Y' prefix to dept codes |

## Environment Variables in Lambda

| Variable | Default | Set In |
|----------|---------|--------|
| RUN_MODE | remote_s3 | template.yaml |
| CTD_LOG_LEVEL | INFO | template.yaml (parameter) |
| INGEST_BUCKET | - | template.yaml (parameter) |
| PROCESSING_BUCKET | - | template.yaml (parameter) |
| S3_OUTPUT_DIR | json_outputs | template.yaml |
| TRANSFER_REGISTER_FILENAME | uploaded_records... | template.yaml (parameter) |

## Common Tasks

### Update Lambda Code
```powershell
# After code changes
docker build -t ctd-pa-transformations .
.\deploy-lambda.ps1
```

### Change Environment Variables
Edit `template.yaml` → `sam deploy`

### View All Lambda Functions
```powershell
aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `ctd-pa`)]'
```

### Delete Stack
```powershell
sam delete --stack-name ctd-pa-transformations-dev
```

## Troubleshooting Quick Fixes

| Issue | Fix |
|-------|-----|
| Docker not running | Start Docker Desktop |
| ECR auth failed | Re-run: `aws ecr get-login-password ...` |
| Lambda timeout | Increase timeout in template.yaml |
| Permission denied | Check IAM policies in template.yaml |
| File not found in S3 | Verify bucket name and key |

## What's Next?

1. Test Lambda with real XML file
2. Create Step Functions state machine
3. Configure S3 event trigger
4. Implement full workflow

See `LAMBDA_SETUP.md` for complete architecture details.
