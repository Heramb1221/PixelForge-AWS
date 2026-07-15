"""
app/routes/auth.py
-------------------
Single-user auth flow: the first visitor registers the one account this
deployment will ever have; every subsequent visitor only sees /login.
"""
import logging
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, flash

from app import models
from app.services import auth_service
from app.utils.validators import validate_email, validate_password, ValidationError

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not auth_service.is_authenticated():
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)
    return wrapped


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if models.any_user_exists():
        flash("An account already exists for this deployment. Please log in.", "info")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        try:
            email = validate_email(request.form.get("email", ""))
            password = validate_password(request.form.get("password", ""))
            user = auth_service.register_first_user(email, password)
            auth_service.login_user(user)
            logger.info("Registered first user: %s", email)
            return redirect(url_for("dashboard.home"))
        except (ValidationError, ValueError, PermissionError) as exc:
            flash(str(exc), "error")

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = auth_service.authenticate(email, password)
        if user:
            auth_service.login_user(user)
            logger.info("User %s logged in", email)
            return redirect(url_for("dashboard.home"))
        flash("Invalid email or password.", "error")

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    auth_service.logout_user()
    return redirect(url_for("auth.login"))
