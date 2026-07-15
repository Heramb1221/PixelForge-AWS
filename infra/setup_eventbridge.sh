#!/usr/bin/env bash
# infra/setup_eventbridge.sh
# -----------------------------
# Creates a daily EventBridge schedule that invokes the cleanup-orphans
# Lambda. Run this AFTER infra/setup_lambda.sh (the function must exist).

source "$(dirname "$0")/config.sh"

ACCOUNT_ID="$(get_account_id)"
CLEANUP_LAMBDA_ARN="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:${LAMBDA_CLEANUP_FUNCTION_NAME}"

echo "==> Creating EventBridge rule: $EVENTBRIDGE_RULE_NAME (runs daily at 03:00 UTC)"
aws events put-rule \
    --name "$EVENTBRIDGE_RULE_NAME" \
    --schedule-expression "cron(0 3 * * ? *)" \
    --state ENABLED \
    --description "Daily PixelForge orphaned-upload cleanup"

echo "==> Granting EventBridge permission to invoke the cleanup Lambda"
aws lambda add-permission \
    --function-name "$LAMBDA_CLEANUP_FUNCTION_NAME" \
    --statement-id "AllowEventBridgeInvoke" \
    --action "lambda:InvokeFunction" \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${AWS_REGION}:${ACCOUNT_ID}:rule/${EVENTBRIDGE_RULE_NAME}" \
    2>/dev/null || echo "    Permission already exists, skipping."

echo "==> Attaching Lambda as the rule's target"
aws events put-targets \
    --rule "$EVENTBRIDGE_RULE_NAME" \
    --targets "Id"="1","Arn"="${CLEANUP_LAMBDA_ARN}"

echo "==> EventBridge setup complete. Cleanup will run daily at 03:00 UTC."
echo "    To trigger it manually for testing:"
echo "    aws lambda invoke --function-name ${LAMBDA_CLEANUP_FUNCTION_NAME} /tmp/cleanup-result.json && cat /tmp/cleanup-result.json"
