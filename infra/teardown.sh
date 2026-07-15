#!/usr/bin/env bash
# infra/teardown.sh
# --------------------
# Removes every AWS resource created by the infra/ scripts, so the
# project doesn't keep costing money after you're done demoing it.
# Safe to re-run; each step tolerates "already gone" errors.
#
# WARNING: this deletes your S3 buckets (including their contents), your
# RDS instance (including all data - no final snapshot is taken), and
# your EC2 instance. Make sure you actually want to tear everything down
# before running this.

source "$(dirname "$0")/config.sh"

ACCOUNT_ID="$(get_account_id)"
echo "==> Tearing down PixelForge AWS resources in ${AWS_REGION}"

echo "==> Removing EventBridge rule"
aws events remove-targets --rule "$EVENTBRIDGE_RULE_NAME" --ids "1" 2>/dev/null || true
aws events delete-rule --name "$EVENTBRIDGE_RULE_NAME" 2>/dev/null || true

echo "==> Removing S3 bucket notification (process-image trigger)"
aws s3api put-bucket-notification-configuration \
    --bucket "$S3_ORIGINALS_BUCKET" \
    --notification-configuration '{}' 2>/dev/null || true

echo "==> Deleting Lambda functions"
aws lambda delete-function --function-name "$LAMBDA_PROCESS_FUNCTION_NAME" 2>/dev/null || true
aws lambda delete-function --function-name "$LAMBDA_CLEANUP_FUNCTION_NAME" 2>/dev/null || true

echo "==> Emptying and deleting S3 buckets"
aws s3 rm "s3://${S3_ORIGINALS_BUCKET}" --recursive 2>/dev/null || true
aws s3 rm "s3://${S3_PROCESSED_BUCKET}" --recursive 2>/dev/null || true
aws s3api delete-bucket --bucket "$S3_ORIGINALS_BUCKET" --region "$AWS_REGION" 2>/dev/null || true
aws s3api delete-bucket --bucket "$S3_PROCESSED_BUCKET" --region "$AWS_REGION" 2>/dev/null || true

echo "==> Deleting RDS instance (if one was created by setup_rds.sh)"
DB_INSTANCE_ID="${PROJECT_PREFIX}-db"
if aws rds describe-db-instances --db-instance-identifier "$DB_INSTANCE_ID" >/dev/null 2>&1; then
    aws rds delete-db-instance --db-instance-identifier "$DB_INSTANCE_ID" --skip-final-snapshot >/dev/null
    echo "    Deleting $DB_INSTANCE_ID (this happens in the background, takes several minutes)"
else
    echo "    No RDS instance named $DB_INSTANCE_ID found, skipping."
fi

echo "==> Terminating EC2 instance"

INSTANCE_ID="$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=${EC2_INSTANCE_NAME}" "Name=instance-state-name,Values=running,stopped,pending" \
    --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null || true)"
if [[ -n "$INSTANCE_ID" && "$INSTANCE_ID" != "None" ]]; then
    aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" >/dev/null
    echo "    Terminating instance $INSTANCE_ID"
fi

echo "==> Removing security group (after instance termination completes; may need a retry)"
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
SG_ID="$(aws ec2 describe-security-groups \
    --filters Name=group-name,Values="$EC2_SECURITY_GROUP_NAME" Name=vpc-id,Values="$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)"
if [[ -n "$SG_ID" && "$SG_ID" != "None" ]]; then
    aws ec2 delete-security-group --group-id "$SG_ID" 2>/dev/null || \
        echo "    Could not delete security group yet (instance may still be terminating). Re-run this script in a minute."
fi

echo "==> Removing IAM role policies, roles, and instance profile"
aws iam remove-role-from-instance-profile \
    --instance-profile-name "$IAM_EC2_INSTANCE_PROFILE" --role-name "$IAM_EC2_ROLE_NAME" 2>/dev/null || true
aws iam delete-instance-profile --instance-profile-name "$IAM_EC2_INSTANCE_PROFILE" 2>/dev/null || true

for role in "$IAM_LAMBDA_ROLE_NAME" "$IAM_CLEANUP_ROLE_NAME" "$IAM_EC2_ROLE_NAME"; do
    for policy in $(aws iam list-role-policies --role-name "$role" --query 'PolicyNames[]' --output text 2>/dev/null || true); do
        aws iam delete-role-policy --role-name "$role" --policy-name "$policy" 2>/dev/null || true
    done
    for arn in $(aws iam list-attached-role-policies --role-name "$role" --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null || true); do
        aws iam detach-role-policy --role-name "$role" --policy-arn "$arn" 2>/dev/null || true
    done
    aws iam delete-role --role-name "$role" 2>/dev/null || true
done

echo "==> Teardown complete."
echo "    RDS deletion runs in the background - check status with:"
echo "      aws rds describe-db-instances --db-instance-identifier ${DB_INSTANCE_ID}"
