#!/usr/bin/env bash
# infra/setup_rds.sh
# ---------------------
# Creates a single db.t3.micro PostgreSQL RDS instance (Free Tier
# eligible) reachable only from the PixelForge EC2 security group.
#
# MANUAL STEP REQUIRED: this script will prompt you to type a master
# password interactively - it is never written to disk or logged.
# Run infra/setup_ec2.sh BEFORE this script, since it needs the EC2
# security group ID to lock down RDS access.

source "$(dirname "$0")/config.sh"

DB_INSTANCE_ID="${PROJECT_PREFIX}-db"
DB_NAME="pixelforge"
DB_MASTER_USER="pixelforge_app"

echo "==> Looking up default VPC and EC2 security group"
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)"
EC2_SG_ID="$(aws ec2 describe-security-groups \
    --filters Name=group-name,Values="$EC2_SECURITY_GROUP_NAME" Name=vpc-id,Values="$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' --output text)"

if [[ -z "$EC2_SG_ID" || "$EC2_SG_ID" == "None" ]]; then
    echo "ERROR: EC2 security group not found. Run infra/setup_ec2.sh first." >&2
    exit 1
fi

echo "==> Creating RDS security group (if it doesn't already exist)"
RDS_SG_NAME="${PROJECT_PREFIX}-rds-sg"
RDS_SG_ID="$(aws ec2 describe-security-groups \
    --filters Name=group-name,Values="$RDS_SG_NAME" Name=vpc-id,Values="$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)"

if [[ -z "$RDS_SG_ID" || "$RDS_SG_ID" == "None" ]]; then
    RDS_SG_ID="$(aws ec2 create-security-group \
        --group-name "$RDS_SG_NAME" \
        --description "PixelForge RDS - only reachable from the app server" \
        --vpc-id "$VPC_ID" \
        --query 'GroupId' --output text)"
    aws ec2 authorize-security-group-ingress --group-id "$RDS_SG_ID" \
        --protocol tcp --port 5432 --source-group "$EC2_SG_ID"
    echo "    Created RDS security group: $RDS_SG_ID (port 5432 from EC2 SG only)"
else
    echo "    RDS security group already exists: $RDS_SG_ID"
fi

echo ""
echo "You will now be prompted for a master database password."
echo "Requirements: 8-128 characters, at least one letter and one number."
read -s -p "Enter RDS master password: " DB_PASSWORD
echo ""
read -s -p "Confirm RDS master password: " DB_PASSWORD_CONFIRM
echo ""

if [[ "$DB_PASSWORD" != "$DB_PASSWORD_CONFIRM" ]]; then
    echo "ERROR: Passwords did not match. Aborting." >&2
    exit 1
fi

echo "==> Creating RDS instance (db.t3.micro, PostgreSQL, Free Tier eligible)"
echo "    This takes several minutes."
aws rds create-db-instance \
    --db-instance-identifier "$DB_INSTANCE_ID" \
    --db-instance-class db.t3.micro \
    --engine postgres \
    --engine-version 16.3 \
    --master-username "$DB_MASTER_USER" \
    --master-user-password "$DB_PASSWORD" \
    --allocated-storage 20 \
    --storage-type gp2 \
    --db-name "$DB_NAME" \
    --vpc-security-group-ids "$RDS_SG_ID" \
    --no-publicly-accessible \
    --backup-retention-period 1 \
    --no-multi-az \
    --tags "Key=Name,Value=${DB_INSTANCE_ID}"

unset DB_PASSWORD DB_PASSWORD_CONFIRM

echo "==> Waiting for the instance to become available (this can take 5-10 minutes)..."
aws rds wait db-instance-available --db-instance-identifier "$DB_INSTANCE_ID"

DB_ENDPOINT="$(aws rds describe-db-instances \
    --db-instance-identifier "$DB_INSTANCE_ID" \
    --query 'DBInstances[0].Endpoint.Address' --output text)"

echo "==> RDS instance is available."
echo "    Endpoint: $DB_ENDPOINT"
echo ""
echo "NEXT STEP (manual): set these values in your EC2 instance's .env file:"
echo "    DB_HOST=${DB_ENDPOINT}"
echo "    DB_PORT=5432"
echo "    DB_NAME=${DB_NAME}"
echo "    DB_USER=${DB_MASTER_USER}"
echo "    DB_PASSWORD=<the password you just entered>"
echo ""
echo "Note: DB_HOST above is only reachable from inside the VPC (the EC2"
echo "instance) since the instance was created with --no-publicly-accessible."
