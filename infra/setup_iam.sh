#!/usr/bin/env bash
# infra/setup_iam.sh
# ---------------------
# Creates three least-privilege IAM roles:
#   1. Lambda execution role for process-image  (S3 read/write, scoped to
#      the two PixelForge buckets only; CloudWatch Logs)
#   2. Lambda execution role for cleanup-orphans (S3 read/delete, same
#      buckets only; CloudWatch Logs)
#   3. EC2 instance role for the Flask app       (S3 put/get, scoped to
#      the two PixelForge buckets, so it can generate valid presigned
#      URLs; CloudWatch Logs)
#
# Run this AFTER infra/setup_s3.sh (bucket ARNs are referenced by name).

source "$(dirname "$0")/config.sh"

ACCOUNT_ID="$(get_account_id)"
echo "==> Using AWS account: $ACCOUNT_ID"

LAMBDA_TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}'

EC2_TRUST_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ec2.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}'

create_role_if_missing() {
    local role_name="$1"
    local trust_policy="$2"
    if aws iam get-role --role-name "$role_name" >/dev/null 2>&1; then
        echo "    Role $role_name already exists, skipping creation."
    else
        aws iam create-role \
            --role-name "$role_name" \
            --assume-role-policy-document "$trust_policy" \
            --description "PixelForge role: $role_name"
        echo "    Created role $role_name"
    fi
}

echo "==> Creating IAM roles"
create_role_if_missing "$IAM_LAMBDA_ROLE_NAME" "$LAMBDA_TRUST_POLICY"
create_role_if_missing "$IAM_CLEANUP_ROLE_NAME" "$LAMBDA_TRUST_POLICY"
create_role_if_missing "$IAM_EC2_ROLE_NAME" "$EC2_TRUST_POLICY"

echo "==> Attaching CloudWatch Logs basic execution policy to Lambda roles"
aws iam attach-role-policy --role-name "$IAM_LAMBDA_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
aws iam attach-role-policy --role-name "$IAM_CLEANUP_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

echo "==> Attaching scoped S3 policy to process-image Lambda role"
cat > /tmp/pixelforge-lambda-process-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::${S3_ORIGINALS_BUCKET}/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::${S3_PROCESSED_BUCKET}/*"
    }
  ]
}
EOF
aws iam put-role-policy --role-name "$IAM_LAMBDA_ROLE_NAME" \
    --policy-name "${PROJECT_PREFIX}-process-s3-access" \
    --policy-document file:///tmp/pixelforge-lambda-process-policy.json

echo "==> Attaching scoped S3 policy to cleanup-orphans Lambda role"
cat > /tmp/pixelforge-lambda-cleanup-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:DeleteObject"],
      "Resource": [
        "arn:aws:s3:::${S3_ORIGINALS_BUCKET}/*",
        "arn:aws:s3:::${S3_PROCESSED_BUCKET}/*"
      ]
    }
  ]
}
EOF
aws iam put-role-policy --role-name "$IAM_CLEANUP_ROLE_NAME" \
    --policy-name "${PROJECT_PREFIX}-cleanup-s3-access" \
    --policy-document file:///tmp/pixelforge-lambda-cleanup-policy.json

echo "==> Attaching scoped S3 + CloudWatch Logs policy to EC2 role"
cat > /tmp/pixelforge-ec2-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::${S3_ORIGINALS_BUCKET}/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::${S3_PROCESSED_BUCKET}/*"
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:${AWS_REGION}:${ACCOUNT_ID}:log-group:/pixelforge/*"
    }
  ]
}
EOF
aws iam put-role-policy --role-name "$IAM_EC2_ROLE_NAME" \
    --policy-name "${PROJECT_PREFIX}-ec2-access" \
    --policy-document file:///tmp/pixelforge-ec2-policy.json

echo "==> Creating EC2 instance profile"
if aws iam get-instance-profile --instance-profile-name "$IAM_EC2_INSTANCE_PROFILE" >/dev/null 2>&1; then
    echo "    Instance profile already exists, skipping creation."
else
    aws iam create-instance-profile --instance-profile-name "$IAM_EC2_INSTANCE_PROFILE"
    aws iam add-role-to-instance-profile \
        --instance-profile-name "$IAM_EC2_INSTANCE_PROFILE" \
        --role-name "$IAM_EC2_ROLE_NAME"
    echo "    Waiting 10s for instance profile propagation..."
    sleep 10
fi

rm -f /tmp/pixelforge-*.json

echo "==> IAM setup complete."
echo "    Lambda process role:  $IAM_LAMBDA_ROLE_NAME"
echo "    Lambda cleanup role:  $IAM_CLEANUP_ROLE_NAME"
echo "    EC2 role/profile:     $IAM_EC2_ROLE_NAME / $IAM_EC2_INSTANCE_PROFILE"
