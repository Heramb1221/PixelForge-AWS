"""
app/utils/validators.py
------------------------
Small, dependency-free input validation helpers. Every route handler that
accepts user input should route it through one of these before touching
the database or S3.
"""
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9 _\-]{2,150}$")

ALLOWED_OUTPUT_FORMATS = {"webp", "jpeg", "png"}


class ValidationError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def validate_email(email):
    if not email or not EMAIL_RE.match(email.strip()):
        raise ValidationError("Please enter a valid email address.")
    return email.strip().lower()


def validate_password(password):
    if not password or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")
    return password


def validate_project_name(name):
    if not name or not SAFE_NAME_RE.match(name.strip()):
        raise ValidationError(
            "Project name must be 2-150 characters and contain only letters, "
            "numbers, spaces, hyphens, or underscores."
        )
    return name.strip()


def validate_variant_profile(label, width, height, output_format, smart_crop):
    if not label or not SAFE_NAME_RE.match(label.strip()):
        raise ValidationError("Variant label must be 2-150 characters (letters/numbers/spaces/-/_).")

    try:
        width = int(width)
        height = int(height)
    except (TypeError, ValueError):
        raise ValidationError("Width and height must be whole numbers.")

    if not (16 <= width <= 4000) or not (16 <= height <= 4000):
        raise ValidationError("Width and height must be between 16 and 4000 pixels.")

    output_format = (output_format or "webp").lower()
    if output_format not in ALLOWED_OUTPUT_FORMATS:
        raise ValidationError(f"Output format must be one of: {', '.join(sorted(ALLOWED_OUTPUT_FORMATS))}.")

    return label.strip(), width, height, output_format, bool(smart_crop)


def validate_upload_request(filename, content_type, size_bytes, allowed_content_types, max_size_bytes):
    if not filename or "/" in filename or "\\" in filename:
        raise ValidationError("Invalid filename.")

    if content_type not in allowed_content_types:
        raise ValidationError(
            f"Unsupported file type '{content_type}'. Allowed: {', '.join(sorted(allowed_content_types))}."
        )

    try:
        size_bytes = int(size_bytes)
    except (TypeError, ValueError):
        raise ValidationError("File size is required and must be numeric.")

    if size_bytes <= 0 or size_bytes > max_size_bytes:
        raise ValidationError(
            f"File size must be between 1 byte and {max_size_bytes // (1024 * 1024)} MB."
        )

    return filename, content_type, size_bytes
