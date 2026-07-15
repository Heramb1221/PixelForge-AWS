#!/usr/bin/env bash
# infra/setup_s3.sh
# -------------------
# Creates the two S3 buckets PixelForge needs and applies CORS so the
# browser can PUT directly to the originals bucket using a presigned URL.
#
# MANUAL STEP REQUIRED FIRST: edit infra/config.sh with your chosen
# (globally unique) bucket names before running this script.

source "$(dirname "$0")/config.sh"

echo "==> Creating S3 buckets in ${AWS_REGION}"

create_bucket() {
    local bucket_name="$1"
    if aws s3api head-bucket --bucket "$bucket_name" --region "$AWS_REGION" 2>/dev/null; then
        echo "    Bucket $bucket_name already exists, skipping creation."
    else
        aws s3api create-bucket \
            --bucket "$bucket_name" \
            --region "$AWS_REGION" \
            --create-bucket-configuration LocationConstraint="$AWS_REGION"
        echo "    Created bucket $bucket_name"
    fi

    aws s3api put-bucket-encryption \
        --bucket "$bucket_name" \
        --server-side-encryption-configuration '{
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        }'

    aws s3api put-public-access-block \
        --bucket "$bucket_name" \
        --public-access-block-configuration \
        BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
}

create_bucket "$S3_ORIGINALS_BUCKET"
create_bucket "$S3_PROCESSED_BUCKET"

echo "==> Applying CORS to $S3_ORIGINALS_BUCKET (browser presigned uploads)"
cat > /tmp/pixelforge-cors.json <<EOF
{
  "CORSRules": [
    {
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["PUT", "GET"],
      "AllowedOrigins": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
}
EOF
# NOTE: this uses the AWS CLI's `s3api put-bucket-cors` command, which is
# the CLI equivalent of the boto3 client method `put_bucket_cors` used in
# app/services/s3_service.py. Do not confuse this with the nonexistent
# boto3 method `put_bucket_cors_configuration`.
aws s3api put-bucket-cors --bucket "$S3_ORIGINALS_BUCKET" --cors-configuration file:///tmp/pixelforge-cors.json
rm -f /tmp/pixelforge-cors.json

echo "==> Enabling lifecycle rule on $S3_ORIGINALS_BUCKET to abort incomplete multipart uploads after 1 day"
cat > /tmp/pixelforge-lifecycle.json <<EOF
{
  "Rules": [
    {
      "ID": "abort-incomplete-multipart-uploads",
      "Status": "Enabled",
      "Filter": {},
      "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1}
    }
  ]
}
EOF
aws s3api put-bucket-lifecycle-configuration \
    --bucket "$S3_ORIGINALS_BUCKET" \
    --lifecycle-configuration file:///tmp/pixelforge-lifecycle.json
rm -f /tmp/pixelforge-lifecycle.json

echo "==> S3 setup complete."
echo "    Originals bucket: $S3_ORIGINALS_BUCKET"
echo "    Processed bucket: $S3_PROCESSED_BUCKET"
echo ""
echo "NOTE: The S3 -> Lambda event notification is configured later, in"
echo "      infra/setup_lambda.sh, once the Lambda function exists (S3"
echo "      cannot subscribe a notification to a function that isn't"
echo "      created yet)."
