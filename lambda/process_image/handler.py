"""
lambda/process_image/handler.py
---------------------------------
Triggered by S3 ObjectCreated events on the "originals" bucket.

For each uploaded image:
  1. Look up the PixelForge image_id for this S3 key (Flask internal API).
  2. Mark the image "processing".
  3. Fetch the variant profiles configured for the parent project.
  4. For each profile: smart-crop (or center-crop) + resize + convert
     format, upload the result to the "processed" bucket.
  5. Report success (with per-variant metadata) or failure back to Flask.

Deliberately talks to RDS only through the Flask internal API rather
than opening a direct database connection - this avoids putting the
Lambda inside the RDS VPC and dealing with connection pooling/cold-start
overhead for a function that already has a natural HTTP-reachable
control plane (the Flask app) sitting in front of the database.
"""
import io
import json
import logging
import os
import urllib.parse
import urllib.request
import urllib.error

import boto3
from PIL import Image, ImageOps

from saliency import find_focal_point, compute_smart_crop_box

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

PROCESSED_BUCKET = os.environ["S3_PROCESSED_BUCKET"]
INTERNAL_API_BASE_URL = os.environ["INTERNAL_API_BASE_URL"].rstrip("/")
INTERNAL_API_KEY = os.environ["INTERNAL_API_KEY"]
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "10"))

PILLOW_FORMAT_MAP = {"webp": "WEBP", "jpeg": "JPEG", "png": "PNG"}
CONTENT_TYPE_MAP = {"webp": "image/webp", "jpeg": "image/jpeg", "png": "image/png"}


def _internal_request(method, path, payload=None):
    url = f"{INTERNAL_API_BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Internal-Api-Key", INTERNAL_API_KEY)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Internal API HTTP error %s for %s %s: %s", exc.code, method, path, error_body)
        raise
    except urllib.error.URLError as exc:
        logger.error("Internal API request failed for %s %s: %s", method, path, exc)
        raise


def _lookup_image_id(key):
    encoded_key = urllib.parse.quote(key, safe="")
    result = _internal_request("GET", f"/internal/images/lookup?key={encoded_key}")
    return result["image_id"]


def _fetch_manifest(image_id):
    return _internal_request("GET", f"/internal/images/{image_id}/profiles")


def _mark_processing(image_id):
    _internal_request("POST", f"/internal/images/{image_id}/start")


def _report_success(image_id, variants):
    _internal_request("POST", f"/internal/images/{image_id}/result", {
        "status": "done",
        "variants": variants,
    })


def _report_failure(image_id, error_message):
    try:
        _internal_request("POST", f"/internal/images/{image_id}/result", {
            "status": "failed",
            "error_message": error_message,
        })
    except Exception:
        logger.exception("Failed to report failure back to Flask for image_id=%s", image_id)


def _naive_reencode_size(image: Image.Image, size, output_format) -> int:
    """
    Baseline used to compute 'bytes saved': a same-dimension re-encode in
    the ORIGINAL format (no WebP conversion, no smart crop optimization),
    which approximates what a naive manual export would produce.
    """
    baseline = image.copy()
    baseline.thumbnail(size, Image.LANCZOS)
    buf = io.BytesIO()
    fmt = "JPEG" if output_format != "PNG" else "PNG"
    save_kwargs = {"quality": 90} if fmt == "JPEG" else {}
    baseline.convert("RGB" if fmt == "JPEG" else baseline.mode).save(buf, format=fmt, **save_kwargs)
    return buf.tell()


def _render_variant(source_image: Image.Image, profile, focal_point):
    target_w, target_h = int(profile["target_width"]), int(profile["target_height"])
    target_aspect = target_w / target_h

    if profile["smart_crop"]:
        box = compute_smart_crop_box(source_image.size, target_aspect, focal_point)
        cropped = source_image.crop(box)
    else:
        cropped = ImageOps.fit(source_image, (target_w, target_h), Image.LANCZOS)
        box = None

    if box is not None:
        resized = cropped.resize((target_w, target_h), Image.LANCZOS)
    else:
        resized = cropped

    output_format = profile["output_format"]
    pillow_format = PILLOW_FORMAT_MAP[output_format]

    buf = io.BytesIO()
    save_kwargs = {}
    if pillow_format == "WEBP":
        save_kwargs = {"quality": 82, "method": 6}
    elif pillow_format == "JPEG":
        save_kwargs = {"quality": 85, "optimize": True}
    elif pillow_format == "PNG":
        save_kwargs = {"optimize": True}

    to_save = resized.convert("RGB") if pillow_format == "JPEG" else resized
    to_save.save(buf, format=pillow_format, **save_kwargs)
    variant_bytes = buf.getvalue()

    naive_size = _naive_reencode_size(source_image, (target_w, target_h), pillow_format)
    bytes_saved = max(0, naive_size - len(variant_bytes))

    return variant_bytes, resized.size, bytes_saved


def _process_one_record(bucket, key, image_id):
    logger.info("Processing image_id=%s key=%s", image_id, key)
    _mark_processing(image_id)

    manifest = _fetch_manifest(image_id)
    profiles = manifest["profiles"]
    if not profiles:
        raise RuntimeError("No variant profiles configured for this project.")

    obj = s3.get_object(Bucket=bucket, Key=key)
    source_bytes = obj["Body"].read()
    source_image = Image.open(io.BytesIO(source_bytes))
    source_image = ImageOps.exif_transpose(source_image)  # respect camera orientation
    if source_image.mode not in ("RGB", "RGBA", "L"):
        source_image = source_image.convert("RGBA")

    focal_point = find_focal_point(source_image)
    logger.info("Focal point for %s: %s", key, focal_point)

    variants_metadata = []
    for profile in profiles:
        variant_bytes, (w, h), bytes_saved = _render_variant(source_image, profile, focal_point)

        base, _ = os.path.splitext(key)
        processed_key = f"{base}/{profile['label']}.{profile['output_format']}"

        s3.put_object(
            Bucket=PROCESSED_BUCKET,
            Key=processed_key,
            Body=variant_bytes,
            ContentType=CONTENT_TYPE_MAP[profile["output_format"]],
        )

        variants_metadata.append({
            "variant_profile_id": profile["id"],
            "processed_key": processed_key,
            "width": w,
            "height": h,
            "size_bytes": len(variant_bytes),
            "bytes_saved": bytes_saved,
        })
        logger.info("Wrote variant '%s' for image_id=%s -> s3://%s/%s (%d bytes)",
                    profile["label"], image_id, PROCESSED_BUCKET, processed_key, len(variant_bytes))

    _report_success(image_id, variants_metadata)
    logger.info("Completed image_id=%s with %d variants", image_id, len(variants_metadata))


def handler(event, context):
    results = {"processed": 0, "failed": 0}

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        image_id = None
        try:
            image_id = _lookup_image_id(key)
        except Exception as exc:
            # If we can't even resolve the image_id, there's nothing to
            # report back to - log and move to the next record.
            logger.exception("Could not resolve image_id for key=%s: %s", key, exc)
            results["failed"] += 1
            continue

        try:
            _process_one_record(bucket, key, image_id)
            results["processed"] += 1
        except Exception as exc:
            logger.exception("Failed to process key=%s (image_id=%s): %s", key, image_id, exc)
            _report_failure(image_id, str(exc))
            results["failed"] += 1

    return results
