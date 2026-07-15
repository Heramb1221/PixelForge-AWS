#!/usr/bin/env bash
source "$(dirname "$0")/config.sh"

echo "==> Creating IAM roles"
# (Use your existing create_role_if_missing function here)

echo "==> Attaching policies"
# Ensure these JSON files exist in your infra/ folder
aws iam put-role-policy --role-name "$IAM_LAMBDA_ROLE_NAME" --policy-name "${PROJECT_PREFIX}-process-s3-access" --policy-document file://pixelforge-lambda-process-policy.json
aws iam put-role-policy --role-name "$IAM_CLEANUP_ROLE_NAME" --policy-name "${PROJECT_PREFIX}-cleanup-s3-access" --policy-document file://pixelforge-lambda-cleanup-policy.json
aws iam put-role-policy --role-name "$IAM_EC2_ROLE_NAME" --policy-name "${PROJECT_PREFIX}-ec2-access" --policy-document file://pixelforge-ec2-policy.json

echo "==> Creating EC2 instance profile"
aws iam create-instance-profile --instance-profile-name "$IAM_EC2_INSTANCE_PROFILE" || true
aws iam add-role-to-instance-profile --instance-profile-name "$IAM_EC2_INSTANCE_PROFILE" --role-name "$IAM_EC2_ROLE_NAME" || true
aws iam put-role-policy --role-name "$IAM_LAMBDA_ROLE_NAME" --policy-name "DynamoDBAccess" --policy-document file://pixelforge-dynamodb-policy.json
aws iam put-role-policy --role-name "$IAM_EC2_ROLE_NAME" --policy-name "DynamoDBAccess" --policy-document file://pixelforge-dynamodb-policy.json