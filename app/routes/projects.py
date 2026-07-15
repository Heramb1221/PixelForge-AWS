"""
app/routes/projects.py
------------------------
CRUD for Projects and their VariantProfiles, plus the per-project
analytics view.
"""
import logging

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort

from app import models
from app.routes.auth import login_required
from app.services import auth_service
from app.utils.validators import validate_project_name, validate_variant_profile, ValidationError

logger = logging.getLogger(__name__)
projects_bp = Blueprint("projects", __name__, url_prefix="/projects")


def _get_owned_project_or_404(project_id):
    user_id = auth_service.current_user_id()
    project = models.get_project(project_id, user_id)
    if not project:
        abort(404)
    return project


@projects_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_project():
    if request.method == "POST":
        try:
            name = validate_project_name(request.form.get("name", ""))
            description = request.form.get("description", "").strip()[:1000]
            project = models.create_project(auth_service.current_user_id(), name, description)
            logger.info("Created project %s (id=%s)", name, project["id"])
            flash("Project created. Now add at least one variant profile below.", "success")
            return redirect(url_for("projects.detail", project_id=project["id"]))
        except ValidationError as exc:
            flash(str(exc), "error")

    return render_template("new_project.html")


@projects_bp.route("/<project_id>")
@login_required
def detail(project_id):
    project = _get_owned_project_or_404(project_id)
    profiles = models.list_variant_profiles(project_id)
    images = models.list_images(project_id)

    images_with_variants = []
    for image in images:
        variants = models.list_image_variants(image["id"]) if image["status"] == "done" else []
        for v in variants:
            v["download_url"] = current_app.s3_service.generate_presigned_get(
                current_app.config["S3_PROCESSED_BUCKET"], v["processed_key"]
            )
        images_with_variants.append({"image": image, "variants": variants})

    return render_template(
        "project_detail.html",
        project=project,
        profiles=profiles,
        images_with_variants=images_with_variants,
        max_upload_mb=current_app.config["MAX_UPLOAD_SIZE_BYTES"] // (1024 * 1024),
    )


@projects_bp.route("/<project_id>/delete", methods=["POST"])
@login_required
def delete(project_id):
    _get_owned_project_or_404(project_id)
    models.delete_project(project_id, auth_service.current_user_id())
    flash("Project deleted.", "success")
    return redirect(url_for("dashboard.home"))


@projects_bp.route("/<project_id>/profiles", methods=["POST"])
@login_required
def add_profile(project_id):
    _get_owned_project_or_404(project_id)
    try:
        label, width, height, output_format, smart_crop = validate_variant_profile(
            request.form.get("label", ""),
            request.form.get("width", ""),
            request.form.get("height", ""),
            request.form.get("output_format", "webp"),
            request.form.get("smart_crop") == "on",
        )
        models.create_variant_profile(project_id, label, width, height, output_format, smart_crop)
        flash(f"Variant profile '{label}' added.", "success")
    except ValidationError as exc:
        flash(str(exc), "error")
    return redirect(url_for("projects.detail", project_id=project_id))


@projects_bp.route("/<project_id>/profiles/<profile_id>/delete", methods=["POST"])
@login_required
def delete_profile(project_id, profile_id):
    _get_owned_project_or_404(project_id)
    models.delete_variant_profile(profile_id, project_id)
    flash("Variant profile removed.", "success")
    return redirect(url_for("projects.detail", project_id=project_id))


@projects_bp.route("/<project_id>/analytics")
@login_required
def analytics(project_id):
    project = _get_owned_project_or_404(project_id)
    stats = models.get_project_analytics(project_id)
    return render_template("analytics.html", project=project, stats=stats)
