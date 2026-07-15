#!/usr/bin/env bash
source "$(dirname "$0")/config.sh"

echo "==> Creating S3 buckets"
create_bucket() {
    local bucket_name="$1"
    if aws s3api head-bucket --bucket "$bucket_name" --region "$AWS_REGION" 2>/dev/null; then
        echo "    Bucket $bucket_name already exists, skipping."
    else
        aws s3api create-bucket --bucket "$bucket_name" --region "$AWS_REGION" --create-bucket-configuration LocationConstraint="$AWS_REGION"
    fi
}
create_bucket "$S3_ORIGINALS_BUCKET"
create_bucket "$S3_PROCESSED_BUCKET"

echo "==> Applying CORS"
aws s3api put-bucket-cors --bucket "$S3_ORIGINALS_BUCKET" --cors-configuration file://pixelforge-cors.json

echo "==> Applying Lifecycle rule"
aws s3api put-bucket-lifecycle-configuration --bucket "$S3_ORIGINALS_BUCKET" --lifecycle-configuration file://pixelforge-lifecycle.json