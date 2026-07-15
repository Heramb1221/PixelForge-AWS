#!/usr/bin/env bash
source "$(dirname "$0")/config.sh"

echo "==> Creating DynamoDB table"
aws dynamodb create-table \
    --table-name PixelForgeProjects \
    --attribute-definitions AttributeName=ProjectId,AttributeType=S \
    --key-schema AttributeName=ProjectId,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST