#!/usr/bin/env bash
# infra/deploy_all.sh
# ----------------------
# Convenience wrapper that runs the AWS-side setup scripts in the
# correct order. You still need to complete the manual steps each
# script prints out (SSH deployment, .env creation, etc.) - this just
# saves you from getting the AWS resource ordering wrong.
#
# Read instructions.md before running this for the first time.

set -euo pipefail
cd "$(dirname "$0")"

echo "############################################################"
echo "# PixelForge - full AWS provisioning"
echo "############################################################"

echo ""
echo ">>> Step 1/6: S3 buckets"
bash setup_s3.sh

echo ""
echo ">>> Step 2/6: IAM roles"
bash setup_iam.sh

echo ""
echo ">>> Step 3/6: EC2 instance"
bash setup_ec2.sh

echo ""
echo "############################################################"
echo "MANUAL STEP: SSH into the EC2 instance printed above, copy the"
echo "project there, create .env from .env.example, and run:"
echo "    sudo bash infra/deploy.sh"
echo "Then update INTERNAL_API_BASE_URL in infra/config.sh to the"
echo "instance's public IP and re-run this script, OR continue with"
echo "the remaining steps manually:"
echo "    bash infra/setup_rds.sh"
echo "    bash infra/package_lambda.sh"
echo "    bash infra/setup_lambda.sh"
echo "    bash infra/setup_eventbridge.sh"
echo "############################################################"
