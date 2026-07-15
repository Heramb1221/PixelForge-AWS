#!/usr/bin/env bash
# infra/config.sh
# -----------------
# Shared configuration sourced by every script in infra/.
# Fill in the placeholders below before running anything else.
# This file intentionally contains NO real AWS account IDs, ARNs, or
# credentials - only names/values you choose yourself.

set -euo pipefail

# --- Required: edit these ---
export AWS_REGION="ap-south-1"
export PROJECT_PREFIX="pixelforge"                     # used to name all resources
export S3_ORIGINALS_BUCKET="${PROJECT_PREFIX}-originals-985214763"   # must be globally unique
export S3_PROCESSED_BUCKET="${PROJECT_PREFIX}-processed-985214763"   # must be globally unique
export EC2_KEY_PAIR_NAME="pixelforge-key"   # create in EC2 console first, or via CLI
export EC2_SSH_CIDR="36.255.185.142/32"                      # your IP in CIDR form, e.g. 203.0.113.4/32
export INTERNAL_API_BASE_URL="http://CHANGE-ME-ec2-public-ip"        # nginx proxies :80 -> gunicorn :8000; set after EC2 is running

export INTERNAL_API_KEY="CHANGE-ME-generate-a-long-random-string"

# --- Derived names (usually no need to edit) ---
export IAM_LAMBDA_ROLE_NAME="${PROJECT_PREFIX}-lambda-process-role"
export IAM_CLEANUP_ROLE_NAME="${PROJECT_PREFIX}-lambda-cleanup-role"
export IAM_EC2_ROLE_NAME="${PROJECT_PREFIX}-ec2-role"
export IAM_EC2_INSTANCE_PROFILE="${PROJECT_PREFIX}-ec2-instance-profile"
export LAMBDA_PROCESS_FUNCTION_NAME="${PROJECT_PREFIX}-process-image"
export LAMBDA_CLEANUP_FUNCTION_NAME="${PROJECT_PREFIX}-cleanup-orphans"
export EVENTBRIDGE_RULE_NAME="${PROJECT_PREFIX}-cleanup-schedule"
export EC2_INSTANCE_NAME="${PROJECT_PREFIX}-app-server"
export EC2_SECURITY_GROUP_NAME="${PROJECT_PREFIX}-app-sg"
export EC2_INSTANCE_TYPE="t3.micro"

# Resolved lazily by scripts that need it (avoids a hard dependency on
# `aws sts` succeeding just to source this file).
get_account_id() {
    aws sts get-caller-identity --query Account --output text
}
