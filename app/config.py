"""
app/config.py
-------------
Central configuration object. Every value is read from environment
variables so no secret ever lives in source control. See .env.example
for the full list of variables the app expects.
"""
import os


class Config:
    # --- Flask core ---
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
    ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = ENV == "development"

    # --- AWS ---
    AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
    S3_ORIGINALS_BUCKET = os.environ.get("S3_ORIGINALS_BUCKET")
    S3_PROCESSED_BUCKET = os.environ.get("S3_PROCESSED_BUCKET")
    PRESIGNED_URL_EXPIRY_SECONDS = int(os.environ.get("PRESIGNED_URL_EXPIRY_SECONDS", "300"))

    # --- Database (Amazon DynamoDB) ---
    DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "PixelForgeProjects")

    # --- Internal API (used by the Lambda callback) ---
    # Shared secret the process-image Lambda must present when it calls back
    # into the Flask app to report processing results. Never checked into git.
    INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY")

    # --- Upload constraints ---
    MAX_UPLOAD_SIZE_BYTES = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(15 * 1024 * 1024)))  # 15 MB
    ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

    # --- Cleanup job thresholds (also referenced by the cleanup Lambda docs) ---
    ORPHAN_MAX_AGE_HOURS = int(os.environ.get("ORPHAN_MAX_AGE_HOURS", "24"))

    @classmethod
    def validate(cls):
        """Fail fast and loudly if required configuration is missing."""
        required = [
            "SECRET_KEY", "S3_ORIGINALS_BUCKET", "S3_PROCESSED_BUCKET",
            "DYNAMODB_TABLE_NAME", "INTERNAL_API_KEY",
        ]
        missing = [name for name in required if not getattr(cls, name)]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Copy .env.example to .env and fill in real values."
            )
