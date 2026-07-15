"""
app/routes/images.py
----------------------
Handles the "browser uploads directly to S3" flow:

  1. POST /projects/<id>/images/presign  -> returns a presigned PUT URL
     and creates an `images` row with status='pending'.
  2. Browser PUTs the file bytes straight to S3 using that URL.
  3. S3 ObjectCreated event fires the process-image Lambda, which
     eventually calls back into /internal/... (see internal.py).
  4. GET /projects/<id>/images/<image_id>/status is polled by the
     frontend to know when processing finished.
"""
import logging

from flask import Blueprint, request, jsonify, current_app, abort

from app import models
from app.routes.auth import login_required
from app.services import auth_service
from app.utils.validators import validate_upload_request, ValidationError

logger = logging.getLogger(__name__)
images_bp = Blueprint("images", __name__, url_prefix="/projects/<project_id>/images")


def _get_owned_project_or_404(project_id):
    user_id = auth_service.current_user_id()
    project = models.get_project(project_id, user_id)
    if not project:
        abort(404)
    return project


@images_bp.route("/presign", methods=["POST"])
@login_required
def presign(project_id):
    _get_owned_project_or_404(project_id)
    payload = request.get_json(silent=True) or {}

    try:
        filename, content_type, size_bytes = validate_upload_request(
            payload.get("filename"),
            payload.get("content_type"),
            payload.get("size_bytes"),
            current_app.config["ALLOWED_CONTENT_TYPES"],
            current_app.config["MAX_UPLOAD_SIZE_BYTES"],
        )
    except ValidationError as exc:
        return jsonify({"error": exc.message}), 400

    profiles = models.list_variant_profiles(project_id)
    if not profiles:
        return jsonify({"error": "Add at least one variant profile before uploading images."}), 400

    s3 = current_app.s3_service
    key = s3.build_original_key(project_id, filename)

    image = models.create_image(project_id, key, filename, content_type, size_bytes)
    upload_url = s3.generate_presigned_put(key, content_type)

    logger.info("Issued presigned upload for project=%s image_id=%s key=%s",
                project_id, image["id"], key)

    return jsonify({
        "image_id": image["id"],
        "upload_url": upload_url,
        "s3_key": key,
    })


@images_bp.route("/<image_id>/status")
@login_required
def status(project_id, image_id):
    _get_owned_project_or_404(project_id)
    image = models.get_image(image_id)
    if not image or image["project_id"] != project_id:
        abort(404)

    variants = []
    if image["status"] == "done":
        s3 = current_app.s3_service
        for v in models.list_image_variants(image_id):
            variants.append({
                "label": v["label"],
                "format": v["output_format"],
                "width": v["width"],
                "height": v["height"],
                "size_bytes": v["size_bytes"],
                "download_url": s3.generate_presigned_get(
                    current_app.config["S3_PROCESSED_BUCKET"], v["processed_key"]
                ),
            })

    return jsonify({
        "image_id": image["id"],
        "status": image["status"],
        "error_message": image.get("error_message"),
        "variants": variants,
    })


@images_bp.route("/<image_id>/delete", methods=["POST"])
@login_required
def delete(project_id, image_id):
    _get_owned_project_or_404(project_id)
    image = models.get_image(image_id)
    if not image or image["project_id"] != project_id:
        abort(404)

    s3 = current_app.s3_service
    try:
        if s3.object_exists(current_app.config["S3_ORIGINALS_BUCKET"], image["original_key"]):
            s3.delete_object(current_app.config["S3_ORIGINALS_BUCKET"], image["original_key"])
        for v in models.list_image_variants(image_id):
            if s3.object_exists(current_app.config["S3_PROCESSED_BUCKET"], v["processed_key"]):
                s3.delete_object(current_app.config["S3_PROCESSED_BUCKET"], v["processed_key"])
    except Exception as exc:
        logger.error("S3 cleanup failed while deleting image %s: %s", image_id, exc)

    models.delete_image(image_id)
    return jsonify({"deleted": True})
