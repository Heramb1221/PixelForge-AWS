#!/usr/bin/env bash
# infra/setup_ec2.sh
# ---------------------
# Launches the EC2 instance with proper error handling and variable initialization.

source "$(dirname "$0")/config.sh"

# 1. Validate environment
if [[ "$EC2_KEY_PAIR_NAME" == *"CHANGE-ME"* || "$EC2_SSH_CIDR" == *"CHANGE-ME"* ]]; then
    echo "ERROR: Set EC2_KEY_PAIR_NAME and EC2_SSH_CIDR in infra/config.sh first." >&2
    exit 1
fi

# 2. Lookup VPC
echo "==> Looking up default VPC"
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
if [[ -z "$VPC_ID" || "$VPC_ID" == "None" ]]; then
    echo "ERROR: No default VPC found." >&2
    exit 1
fi

# 3. Setup Security Group
echo "==> Configuring security group"
SG_ID="$(aws ec2 describe-security-groups \
    --filters Name=group-name,Values="$EC2_SECURITY_GROUP_NAME" Name=vpc-id,Values="$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)"

if [[ -z "$SG_ID" || "$SG_ID" == "None" ]]; then
    SG_ID="$(aws ec2 create-security-group \
        --group-name "$EC2_SECURITY_GROUP_NAME" \
        --description "PixelForge Flask app server" \
        --vpc-id "$VPC_ID" \
        --query 'GroupId' --output text)"
    
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr "$EC2_SSH_CIDR"
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 80 --cidr "0.0.0.0/0"
    echo "    Created security group: $SG_ID"
fi

# 4. Lookup AMI
echo "==> Finding latest Ubuntu 24.04 LTS AMI"
AMI_ID="$(aws ec2 describe-images \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" "Name=state,Values=available" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text)"

if [[ -z "$AMI_ID" ]]; then
    echo "ERROR: Could not find AMI." >&2
    exit 1
fi

# 5. Launch Instance
echo "==> Launching EC2 instance ($EC2_INSTANCE_TYPE)"
INSTANCE_ID="$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$EC2_INSTANCE_TYPE" \
    --key-name "$EC2_KEY_PAIR_NAME" \
    --security-group-ids "$SG_ID" \
    --iam-instance-profile "Name=${IAM_EC2_INSTANCE_PROFILE}" \
    --user-data file://user_data.txt \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${EC2_INSTANCE_NAME}}]" \
    --query 'Instances[0].InstanceId' --output text)"

echo "==> Instance launching: $INSTANCE_ID"
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

PUBLIC_IP="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"
echo "==> EC2 is running. Public IP: $PUBLIC_IP"