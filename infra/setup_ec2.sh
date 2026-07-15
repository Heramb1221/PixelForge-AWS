#!/usr/bin/env bash
# infra/setup_ec2.sh
# ---------------------
# Launches the t3.micro Ubuntu instance that runs the Flask app.
#
# MANUAL STEPS REQUIRED FIRST:
#   1. Create an EC2 key pair (or use an existing one) and set
#      EC2_KEY_PAIR_NAME in infra/config.sh.
#        aws ec2 create-key-pair --key-name pixelforge-key \
#          --query 'KeyMaterial' --output text > pixelforge-key.pem
#        chmod 400 pixelforge-key.pem
#   2. Set EC2_SSH_CIDR in infra/config.sh to YOUR_IP/32 so SSH isn't
#      open to the entire internet.
#   3. Run infra/setup_iam.sh first (this script attaches that instance
#      profile).

source "$(dirname "$0")/config.sh"

if [[ "$EC2_KEY_PAIR_NAME" == *"CHANGE-ME"* || "$EC2_SSH_CIDR" == *"CHANGE-ME"* ]]; then
    echo "ERROR: Set EC2_KEY_PAIR_NAME and EC2_SSH_CIDR in infra/config.sh first." >&2
    exit 1
fi

echo "==> Looking up default VPC"
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
if [[ "$VPC_ID" == "None" || -z "$VPC_ID" ]]; then
    echo "ERROR: No default VPC found. Create/select a VPC and adapt this script." >&2
    exit 1
fi
echo "    Using VPC: $VPC_ID"

echo "==> Creating security group (if it doesn't already exist)"
SG_ID="$(aws ec2 describe-security-groups \
    --filters Name=group-name,Values="$EC2_SECURITY_GROUP_NAME" Name=vpc-id,Values="$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)"

if [[ -z "$SG_ID" || "$SG_ID" == "None" ]]; then
    SG_ID="$(aws ec2 create-security-group \
        --group-name "$EC2_SECURITY_GROUP_NAME" \
        --description "PixelForge Flask app server" \
        --vpc-id "$VPC_ID" \
        --query 'GroupId' --output text)"
    echo "    Created security group: $SG_ID"

    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
        --protocol tcp --port 22 --cidr "$EC2_SSH_CIDR"
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
        --protocol tcp --port 80 --cidr "0.0.0.0/0"
    echo "    Opened 22 (your IP only) and 80 (public HTTP)"
else
    echo "    Security group already exists: $SG_ID"
fi

echo "==> Finding latest Ubuntu 24.04 LTS AMI (x86_64) in ${AWS_REGION}"
AMI_ID="$(aws ec2 describe-images \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
               "Name=state,Values=available" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
    --output text)"
echo "    Using AMI: $AMI_ID"

USER_DATA_FILE="$(mktemp)"
cat > "$USER_DATA_FILE" <<'CLOUDINIT'
#!/bin/bash
set -e
apt-get update -y
apt-get install -y python3-venv python3-pip nginx git
mkdir -p /opt/pixelforge
chown ubuntu:ubuntu /opt/pixelforge
CLOUDINIT

echo "==> Launching EC2 instance ($EC2_INSTANCE_TYPE, Ubuntu)"
INSTANCE_ID="$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$EC2_INSTANCE_TYPE" \
    --key-name "$EC2_KEY_PAIR_NAME" \
    --security-group-ids "$SG_ID" \
    --iam-instance-profile "Name=${IAM_EC2_INSTANCE_PROFILE}" \
    --user-data "file://${USER_DATA_FILE}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${EC2_INSTANCE_NAME}}]" \
    --query 'Instances[0].InstanceId' --output text)"
rm -f "$USER_DATA_FILE"

echo "    Instance launching: $INSTANCE_ID"
echo "    Waiting for it to reach 'running' state..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

PUBLIC_IP="$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)"

echo "==> EC2 instance is running."
echo "    Instance ID: $INSTANCE_ID"
echo "    Public IP:   $PUBLIC_IP"
echo ""
echo "NEXT STEPS (manual):"
echo "  1. Update INTERNAL_API_BASE_URL in infra/config.sh to: http://${PUBLIC_IP}"
echo "  2. SSH in and deploy the app:"
echo "       scp -i <your-key.pem> -r . ubuntu@${PUBLIC_IP}:/opt/pixelforge"
echo "       ssh -i <your-key.pem> ubuntu@${PUBLIC_IP}"
echo "       cd /opt/pixelforge && sudo bash infra/deploy.sh"
echo "  3. Create your .env file on the server (see .env.example) with"
echo "     your real RDS endpoint, DB password, and INTERNAL_API_KEY"
echo "     BEFORE running deploy.sh, or deploy.sh will fail its config check."
