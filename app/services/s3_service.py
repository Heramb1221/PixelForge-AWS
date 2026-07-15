"""
app/services/s3_service.py
---------------------------
All direct interaction with S3 lives here so route handlers never touch
boto3 directly. Uses presigned URLs so the browser uploads straight to
S3 (Flask never proxies the binary), which keeps the EC2 instance's
bandwidth and memory footprint minimal.
"""
import logging
import uuid
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3Service:
    def __init__(self, region, originals_bucket, processed_bucket, url_expiry_seconds):
        from botocore.config import Config
        self.client = boto3.client(
            "s3", 
            region_name=region, 
            endpoint_url=f"https://s3.{region}.amazonaws.com",
            config=Config(s3={'addressing_style': 'virtual'}, signature_version='s3v4')
        )
        self.originals_bucket = originals_bucket
        self.processed_bucket = processed_bucket
        self.url_expiry_seconds = url_expiry_seconds

    @staticmethod
    def build_original_key(project_id, filename):
        """project_id/yyyy/mm/uuid_filename -> keeps buckets browsable and unique."""
        safe_filename = filename.replace(" ", "_")
        now = datetime.utcnow()
        unique = uuid.uuid4().hex[:12]
        return f"{project_id}/{now.year:04d}/{now.month:02d}/{unique}_{safe_filename}"

    def generate_presigned_put(self, key, content_type):
        try:
            url = self.client.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": self.originals_bucket,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=self.url_expiry_seconds,
            )
            return url
        except ClientError as exc:
            logger.error("Failed to generate presigned PUT URL for key %s: %s", key, exc)
            raise

    def generate_presigned_get(self, bucket, key):
        try:
            return self.client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=self.url_expiry_seconds,
            )
        except ClientError as exc:
            logger.error("Failed to generate presigned GET URL for key %s: %s", key, exc)
            raise

    def object_exists(self, bucket, key):
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            logger.error("head_object failed for %s/%s: %s", bucket, key, exc)
            raise

    def delete_object(self, bucket, key):
        try:
            self.client.delete_object(Bucket=bucket, Key=key)
            logger.info("Deleted s3://%s/%s", bucket, key)
        except ClientError as exc:
            logger.error("Failed to delete s3://%s/%s: %s", bucket, key, exc)
            raise

    def apply_cors(self, bucket, allowed_origins):
        """
        Configure CORS on a bucket so the browser can PUT directly to it.

        NOTE: the correct boto3 S3 client method for this is
        `put_bucket_cors` (NOT `put_bucket_cors_configuration`, which does
        not exist on the boto3 S3 client).
        """
        cors_configuration = {
            "CORSRules": [
                {
                    "AllowedHeaders": ["*"],
                    "AllowedMethods": ["PUT", "GET"],
                    "AllowedOrigins": allowed_origins,
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 3000,
                }
            ]
        }
        self.client.put_bucket_cors(Bucket=bucket, CORSConfiguration=cors_configuration)
        logger.info("Applied CORS configuration to bucket %s", bucket)
