"""
tests/test_validators.py
---------------------------
Unit tests for app/utils/validators.py. Run with:
    pytest tests/
No AWS or database access required - these are pure functions.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app.utils.validators import (
    validate_email,
    validate_password,
    validate_project_name,
    validate_variant_profile,
    validate_upload_request,
    ValidationError,
)


def test_validate_email_accepts_valid():
    assert validate_email("Person@Example.com") == "person@example.com"


@pytest.mark.parametrize("bad_email", ["", "not-an-email", "missing@domain", "@nouser.com"])
def test_validate_email_rejects_invalid(bad_email):
    with pytest.raises(ValidationError):
        validate_email(bad_email)


def test_validate_password_minimum_length():
    with pytest.raises(ValidationError):
        validate_password("short")
    assert validate_password("longenough1") == "longenough1"


def test_validate_project_name_strips_and_accepts():
    assert validate_project_name("  Blog Hero Images  ") == "Blog Hero Images"


def test_validate_project_name_rejects_special_chars():
    with pytest.raises(ValidationError):
        validate_project_name("Invalid/Name!")


def test_validate_variant_profile_happy_path():
    label, width, height, fmt, smart_crop = validate_variant_profile(
        "thumbnail", "150", "150", "webp", True
    )
    assert label == "thumbnail"
    assert width == 150
    assert height == 150
    assert fmt == "webp"
    assert smart_crop is True


def test_validate_variant_profile_rejects_out_of_range_dimensions():
    with pytest.raises(ValidationError):
        validate_variant_profile("huge", "9999", "9999", "webp", True)


def test_validate_variant_profile_rejects_bad_format():
    with pytest.raises(ValidationError):
        validate_variant_profile("thumb", "150", "150", "bmp", True)


def test_validate_upload_request_happy_path():
    filename, content_type, size = validate_upload_request(
        "photo.jpg", "image/jpeg", 1024 * 1024,
        allowed_content_types={"image/jpeg", "image/png"},
        max_size_bytes=15 * 1024 * 1024,
    )
    assert filename == "photo.jpg"
    assert content_type == "image/jpeg"
    assert size == 1024 * 1024


def test_validate_upload_request_rejects_oversized_file():
    with pytest.raises(ValidationError):
        validate_upload_request(
            "photo.jpg", "image/jpeg", 999 * 1024 * 1024,
            allowed_content_types={"image/jpeg"},
            max_size_bytes=15 * 1024 * 1024,
        )


def test_validate_upload_request_rejects_bad_content_type():
    with pytest.raises(ValidationError):
        validate_upload_request(
            "malware.exe", "application/octet-stream", 1024,
            allowed_content_types={"image/jpeg", "image/png"},
            max_size_bytes=15 * 1024 * 1024,
        )
