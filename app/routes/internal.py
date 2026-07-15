"""
app/routes/internal.py
------------------------
Internal-only API used by the process-image Lambda to report results
back into RDS. Not part of the user-facing app: every request must
present the shared secret INTERNAL_API_KEY in the X-Internal-Api-Key
header. This endpoint is reachable over the public internet (the
Lambda has no VPC/private networking to the EC2 instance), so the
API key is the sole gate - keep it secret and rotate it if it ever
leaks into logs.
"""
import logging
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app

from app import models

logger = logging.getLogger(__name__)
internal_bp = Blueprint("internal", __name__, url_prefix="/internal")


def _authorized(req):
    provided = req.headers.get("X-Internal-Api-Key", "")
    expected = current_app.config.get("INTERNAL_API_KEY", "")
    return bool(expected) and provided == expected


@internal_bp.route("/images/<image_id>/result", methods=["POST"])
def report_result(image_id):
    if not _authorized(request):
        logger.warning("Rejected unauthorized internal callback for image_id=%s", image_id)
        return jsonify({"error": "unauthorized"}), 401

    image = models.get_image(image_id)
    if not image:
        return jsonify({"error": "image not found"}), 404

    payload = request.get_json(silent=True) or {}
    outcome = payload.get("status")  # "done" or "failed"

    if outcome == "done":
        variants = payload.get("variants", [])
        total_bytes_saved = 0
        for v in variants:
            models.create_image_variant(
                image_id=image_id,
                variant_profile_id=v["variant_profile_id"],
                processed_key=v["processed_key"],
                width=v["width"],
                height=v["height"],
                size_bytes=v["size_bytes"],
                bytes_saved=v.get("bytes_saved", 0),
            )
            total_bytes_saved += v.get("bytes_saved", 0)

        models.update_image_status(image_id, "done", processed_at=datetime.now(timezone.utc))
        models.record_event(image["project_id"], "upload_completed", bytes_saved=total_bytes_saved)
        logger.info("Image %s processed successfully with %d variants", image_id, len(variants))

    elif outcome == "failed":
        error_message = str(payload.get("error_message", "Unknown processing error"))[:2000]
        models.update_image_status(image_id, "failed", error_message=error_message,
                                    processed_at=datetime.now(timezone.utc))
        models.record_event(image["project_id"], "processing_failed")
        logger.warning("Image %s processing failed: %s", image_id, error_message)

    else:
        return jsonify({"error": "status must be 'done' or 'failed'"}), 400

    return jsonify({"acknowledged": True})


@internal_bp.route("/images/<image_id>/start", methods=["POST"])
def mark_processing(image_id):
    """Lambda calls this as soon as it picks up the S3 event, so the
    dashboard can show 'processing' instead of 'pending' while the
    resize/crop/convert work is in flight."""
    if not _authorized(request):
        return jsonify({"error": "unauthorized"}), 401

    image = models.get_image(image_id)
    if not image:
        return jsonify({"error": "image not found"}), 404

    models.update_image_status(image_id, "processing")
    return jsonify({"acknowledged": True})


@internal_bp.route("/images/<image_id>/profiles", methods=["GET"])

def get_variant_manifest(image_id):
    """
    Lambda calls this immediately after S3 notifies it, to fetch the list
    of variant profiles (target sizes/formats) it needs to produce for
    this image's parent project - avoiding a direct Lambda-to-RDS
    connection and the VPC/connection-pooling complexity that would add.
    """
    if not _authorized(request):
        return jsonify({"error": "unauthorized"}), 401

    image = models.get_image(image_id)
    if not image:
        return jsonify({"error": "image not found"}), 404

    profiles = models.list_variant_profiles(image["project_id"])
    return jsonify({
        "image_id": image_id,
        "original_key": image["original_key"],
        "profiles": [
            {
                "id": p["id"],
                "label": p["label"],
                "target_width": p["width"],
                "target_height": p["height"],
                "output_format": p["output_format"],
                "smart_crop": p["smart_crop"],
            }
            for p in profiles
        ],
    })


@internal_bp.route("/cleanup/stale-images", methods=["GET"])
def stale_images():
    """Used by the cleanup-orphans Lambda to find what it should delete."""
    if not _authorized(request):
        return jsonify({"error": "unauthorized"}), 401

    try:
        max_age_hours = int(request.args.get("max_age_hours", 24))
    except ValueError:
        return jsonify({"error": "max_age_hours must be an integer"}), 400

    images = models.list_stale_images_with_variants(max_age_hours)
    return jsonify({"images": images})


@internal_bp.route("/cleanup/images/<image_id>/purge", methods=["POST"])
def purge_image(image_id):
    """
    Called by the cleanup Lambda AFTER it has already deleted the S3
    objects for this image. Removes the DB row (and its variants, via
    ON DELETE CASCADE).
    """
    if not _authorized(request):
        return jsonify({"error": "unauthorized"}), 401

    image = models.get_image(image_id)
    if not image:
        return jsonify({"error": "image not found"}), 404

    models.delete_image(image_id)
    if image["project_id"]:
        models.record_event(image["project_id"], "cleanup_deleted")

    return jsonify({"purged": True})


@internal_bp.route("/images/lookup", methods=["GET"])
def lookup_image_by_key():
    """Lambda knows the S3 key from the trigger event, not the image_id."""
    if not _authorized(request):
        return jsonify({"error": "unauthorized"}), 401

    key = request.args.get("key")
    if not key:
        return jsonify({"error": "key query parameter is required"}), 400

    image = models.get_image_by_key(key)
    if not image:
        return jsonify({"error": "image not found"}), 404

    return jsonify({"image_id": image["id"], "status": image["status"]})
