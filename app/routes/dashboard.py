"""
app/routes/dashboard.py
------------------------
Landing page after login: lists projects and an at-a-glance summary.
Per-project analytics live under /projects/<id>/analytics (projects.py).
"""
import logging

from flask import Blueprint, render_template, redirect, url_for

from app import models
from app.routes.auth import login_required
from app.services import auth_service

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    if auth_service.is_authenticated():
        return redirect(url_for("dashboard.home"))
    if models.any_user_exists():
        return redirect(url_for("auth.login"))
    return redirect(url_for("auth.register"))


@dashboard_bp.route("/home")
@login_required
def home():
    user_id = auth_service.current_user_id()
    projects = models.list_projects(user_id)
    return render_template("dashboard.html", projects=projects)
