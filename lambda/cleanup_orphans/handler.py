"""
lambda/cleanup_orphans/handler.py
------------------------------------
Scheduled (EventBridge, e.g. once every 24h) housekeeping job that keeps
storage costs and clutter down - a small but genuine "production-like"
concern for a project that is otherwise "just" a resizer.

It removes:
  1. Objects in the "originals" bucket that have no matching `images` row
     in "done" or "processing" state after ORPHAN_MAX_AGE_HOURS - i.e.
     uploads that never got picked up, or whose Lambda processing failed
     and were never retried.
  2. S3 objects for images whose Flask-side record has status='failed'
     and is older than the same threshold (they've already been reported
     as errors to the user; no need to keep the broken upload around).

Talks to Flask's internal API rather than RDS directly, for the same
reason as the process-image Lambda (no VPC networking / connection
pooling for a function that runs once a day).
"""
import json
import logging
import os
import urllib.request
import urllib.error

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

ORIGINALS_BUCKET = os.environ["S3_ORIGINALS_BUCKET"]
PROCESSED_BUCKET = os.environ["S3_PROCESSED_BUCKET"]
INTERNAL_API_BASE_URL = os.environ["INTERNAL_API_BASE_URL"].rstrip("/")
INTERNAL_API_KEY = os.environ["INTERNAL_API_KEY"]
ORPHAN_MAX_AGE_HOURS = int(os.environ.get("ORPHAN_MAX_AGE_HOURS", "24"))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "10"))


def _internal_request(method, path, payload=None):
    url = f"{INTERNAL_API_BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Internal-Api-Key", INTERNAL_API_KEY)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def _fetch_stale_images():
    """
    GET /internal/cleanup/stale-images returns pending/failed images
    older than ORPHAN_MAX_AGE_HOURS, along with their S3 keys and any
    variant keys already written, so this Lambda can delete every
    associated object before telling Flask to drop the DB rows.
    """
    return _internal_request(
        "GET",
        f"/internal/cleanup/stale-images?max_age_hours={ORPHAN_MAX_AGE_HOURS}",
    )


def _delete_if_exists(bucket, key):
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except s3.exceptions.ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise
    s3.delete_object(Bucket=bucket, Key=key)
    return True


def handler(event, context):
    logger.info("Starting orphan cleanup (threshold=%sh)", ORPHAN_MAX_AGE_HOURS)

    try:
        stale = _fetch_stale_images()
    except urllib.error.URLError as exc:
        logger.error("Could not reach Flask internal API: %s", exc)
        return {"deleted_images": 0, "deleted_objects": 0, "errors": 1}

    deleted_images = 0
    deleted_objects = 0
    errors = 0

    for item in stale.get("images", []):
        image_id = item["id"]
        try:
            if _delete_if_exists(ORIGINALS_BUCKET, item["original_key"]):
                deleted_objects += 1
            for variant_key in item.get("variant_keys", []):
                if _delete_if_exists(PROCESSED_BUCKET, variant_key):
                    deleted_objects += 1

            _internal_request("POST", f"/internal/cleanup/images/{image_id}/purge")
            deleted_images += 1
            logger.info("Purged orphaned image_id=%s (key=%s)", image_id, item["original_key"])
        except Exception as exc:
            logger.exception("Failed to purge image_id=%s: %s", image_id, exc)
            errors += 1

    result = {"deleted_images": deleted_images, "deleted_objects": deleted_objects, "errors": errors}
    logger.info("Cleanup complete: %s", result)
    return result
