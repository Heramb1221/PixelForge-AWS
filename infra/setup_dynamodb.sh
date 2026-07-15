#!/usr/bin/env bash
source "$(dirname "$0")/config.sh"

echo "==> Creating DynamoDB table"
aws dynamodb create-table \
    --table-name PixelForgeProjects \
    --attribute-definitions \
        AttributeName=PK,AttributeType=S \
        AttributeName=SK,AttributeType=S \
        AttributeName=OriginalKey,AttributeType=S \
    --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
    --global-secondary-indexes \
        "[{\"IndexName\": \"SK-index\", \"KeySchema\": [{\"AttributeName\":\"SK\",\"KeyType\":\"HASH\"}, {\"AttributeName\":\"PK\",\"KeyType\":\"RANGE\"}], \"Projection\": {\"ProjectionType\":\"ALL\"}}, {\"IndexName\": \"OriginalKey-index\", \"KeySchema\": [{\"AttributeName\":\"OriginalKey\",\"KeyType\":\"HASH\"}], \"Projection\": {\"ProjectionType\":\"ALL\"}}]" \
    --billing-mode PAY_PER_REQUEST