#!/usr/bin/env bash
# infra/setup_lambda.sh
# ------------------------
# Creates both Lambda functions from the zips built by package_lambda.sh,
# and wires the S3 -> process-image trigger.
#
# MANUAL STEP REQUIRED FIRST: set INTERNAL_API_BASE_URL and
# INTERNAL_API_KEY in infra/config.sh. INTERNAL_API_BASE_URL should point
# at your running EC2 instance (see infra/setup_ec2.sh), e.g.
# http://<ec2-public-ip>  (nginx on port 80 proxies to gunicorn on 8000)


source "$(dirname "$0")/config.sh"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd -W 2>/dev/null || pwd)"
ACCOUNT_ID="$(get_account_id)"

LAMBDA_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${IAM_LAMBDA_ROLE_NAME}"
CLEANUP_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${IAM_CLEANUP_ROLE_NAME}"

if [[ "$INTERNAL_API_BASE_URL" == *"CHANGE-ME"* || "$INTERNAL_API_KEY" == *"CHANGE-ME"* ]]; then
    echo "ERROR: Set INTERNAL_API_BASE_URL and INTERNAL_API_KEY in infra/config.sh first." >&2
    exit 1
fi

create_or_update_function() {
    local function_name="$1"
    local role_arn="$2"
    local zip_path="$3"
    local handler="$4"
    local timeout="$5"
    local memory="$6"
    local env_vars="$7"

    if aws lambda get-function --function-name "$function_name" >/dev/null 2>&1; then
        echo "    Function $function_name exists, updating code + config."
        aws lambda update-function-code \
            --function-name "$function_name" \
            --zip-file "fileb://${zip_path}" >/dev/null
        aws lambda update-function-configuration \
            --function-name "$function_name" \
            --timeout "$timeout" \
            --memory-size "$memory" \
            --environment "$env_vars" >/dev/null
    else
        echo "    Creating function $function_name."
        aws lambda create-function \
            --function-name "$function_name" \
            --runtime python3.12 \
            --role "$role_arn" \
            --handler "$handler" \
            --zip-file "fileb://${zip_path}" \
            --timeout "$timeout" \
            --memory-size "$memory" \
            --environment "$env_vars" >/dev/null
    fi
}

echo "==> Deploying process-image Lambda"
PROCESS_ENV="Variables={S3_PROCESSED_BUCKET=${S3_PROCESSED_BUCKET},INTERNAL_API_BASE_URL=${INTERNAL_API_BASE_URL},INTERNAL_API_KEY=${INTERNAL_API_KEY}}"
create_or_update_function \
    "$LAMBDA_PROCESS_FUNCTION_NAME" \
    "$LAMBDA_ROLE_ARN" \
    "F:/Symbiosis AWS Notes/AWS programs/CAPSTONE PROJECTS/pixelforge/lambda/process_image/package.zip" \
    "handler.handler" \
    60 \
    768 \
    "$PROCESS_ENV"

echo "==> Deploying cleanup-orphans Lambda"
CLEANUP_ENV="Variables={S3_ORIGINALS_BUCKET=${S3_ORIGINALS_BUCKET},S3_PROCESSED_BUCKET=${S3_PROCESSED_BUCKET},INTERNAL_API_BASE_URL=${INTERNAL_API_BASE_URL},INTERNAL_API_KEY=${INTERNAL_API_KEY},ORPHAN_MAX_AGE_HOURS=24}"
create_or_update_function \
    "$LAMBDA_CLEANUP_FUNCTION_NAME" \
    "$CLEANUP_ROLE_ARN" \
    "F:/Symbiosis AWS Notes/AWS programs/CAPSTONE PROJECTS/pixelforge/lambda/cleanup_orphans/package.zip" \
    "handler.handler" \
    120 \
    256 \
    "$CLEANUP_ENV"

echo "==> Granting S3 permission to invoke process-image Lambda"
aws lambda add-permission \
    --function-name "$LAMBDA_PROCESS_FUNCTION_NAME" \
    --statement-id "AllowS3Invoke" \
    --action "lambda:InvokeFunction" \
    --principal s3.amazonaws.com \
    --source-arn "arn:aws:s3:::${S3_ORIGINALS_BUCKET}" \
    2>/dev/null || echo "    Permission already exists, skipping."

echo "==> Wiring S3 ObjectCreated notification -> process-image Lambda"
PROCESS_LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:${LAMBDA_PROCESS_FUNCTION_NAME}"
cat > /tmp/pixelforge-notification.json <<EOF
{
  "LambdaFunctionConfigurations": [
    {
      "Id": "pixelforge-process-on-upload",
      "LambdaFunctionArn": "${PROCESS_LAMBDA_ARN}",
      "Events": ["s3:ObjectCreated:*"]
    }
  ]
}
EOF
aws s3api put-bucket-notification-configuration \
    --bucket "$S3_ORIGINALS_BUCKET" \
    --notification-configuration file:///tmp/pixelforge-notification.json
rm -f /tmp/pixelforge-notification.json

echo "==> Lambda setup complete."
echo "    ${LAMBDA_PROCESS_FUNCTION_NAME} triggers on uploads to ${S3_ORIGINALS_BUCKET}"
echo "    ${LAMBDA_CLEANUP_FUNCTION_NAME} is ready for EventBridge scheduling (see setup_eventbridge.sh)"
