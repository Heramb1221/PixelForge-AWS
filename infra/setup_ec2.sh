#!/usr/bin/env bash
source "$(dirname "$0")/config.sh"

echo "==> Launching EC2 instance"
INSTANCE_ID="$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$EC2_INSTANCE_TYPE" \
    --key-name "$EC2_KEY_PAIR_NAME" \
    --security-group-ids "$SG_ID" \
    --iam-instance-profile "Name=${IAM_EC2_INSTANCE_PROFILE}" \
    --user-data file://user_data.txt \
    --query 'Instances[0].InstanceId' --output text)"

echo "    Instance ID: $INSTANCE_ID"