"""
app/services/auth_service.py
------------------------------
Password hashing (Werkzeug's PBKDF2-based helpers, already a Flask
dependency, so this adds zero new packages) and simple session helpers
for the single-user deployment model.
"""
import logging

from werkzeug.security import generate_password_hash, check_password_hash
from flask import session

from app import models

logger = logging.getLogger(__name__)

SESSION_USER_KEY = "user_id"


def hash_password(plain_password):
    return generate_password_hash(plain_password, method="pbkdf2:sha256", salt_length=16)


def verify_password(plain_password, password_hash):
    return check_password_hash(password_hash, plain_password)


def register_first_user(email, plain_password):
    """
    Single-user guard: registration is only permitted if no user exists yet.
    Subsequent visitors only see the login page.
    """
    if models.any_user_exists():
        raise PermissionError("Registration is closed: an account already exists.")
    if models.get_user_by_email(email):
        raise ValueError("A user with this email already exists.")
    password_hash = hash_password(plain_password)
    return models.create_user(email, password_hash)


def authenticate(email, plain_password):
    user = models.get_user_by_email(email)
    if not user or not verify_password(plain_password, user["password_hash"]):
        return None
    return user


def login_user(user):
    session.clear()
    session[SESSION_USER_KEY] = user["id"]
    session.permanent = True


def logout_user():
    session.clear()


def current_user_id():
    return session.get(SESSION_USER_KEY)


def is_authenticated():
    return SESSION_USER_KEY in session
