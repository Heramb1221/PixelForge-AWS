"""
app/models.py
-------------
Data access functions. Each function opens a short-lived cursor from the
shared pool, runs a single parameterized statement, and returns plain
dicts (via RealDictCursor) so callers never touch psycopg2 objects
directly.
"""
import logging

from app.db import get_cursor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- users ---
def create_user(email, password_hash):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id, email, created_at",
            (email, password_hash),
        )
        return cur.fetchone()


def get_user_by_email(email):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()


def get_user_by_id(user_id):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()


def any_user_exists():
    """Single-user deployment guard: registration is only allowed once."""
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS count FROM users")
        return cur.fetchone()["count"] > 0


# ------------------------------------------------------------- projects ---
def create_project(user_id, name, description):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO projects (user_id, name, description)
               VALUES (%s, %s, %s) RETURNING *""",
            (user_id, name, description),
        )
        return cur.fetchone()


def list_projects(user_id):
    with get_cursor() as cur:
        cur.execute(
            """SELECT p.*,
                      COUNT(DISTINCT i.id) AS image_count
               FROM projects p
               LEFT JOIN images i ON i.project_id = p.id
               WHERE p.user_id = %s
               GROUP BY p.id
               ORDER BY p.created_at DESC""",
            (user_id,),
        )
        return cur.fetchall()


def get_project(project_id, user_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM projects WHERE id = %s AND user_id = %s",
            (project_id, user_id),
        )
        return cur.fetchone()


def delete_project(project_id, user_id):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM projects WHERE id = %s AND user_id = %s RETURNING id",
            (project_id, user_id),
        )
        return cur.fetchone()


# ------------------------------------------------------- variant profiles -
def create_variant_profile(project_id, label, width, height, output_format, smart_crop):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO variant_profiles
                   (project_id, label, target_width, target_height, output_format, smart_crop)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
            (project_id, label, width, height, output_format, smart_crop),
        )
        return cur.fetchone()


def list_variant_profiles(project_id):
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM variant_profiles WHERE project_id = %s ORDER BY created_at",
            (project_id,),
        )
        return cur.fetchall()


def delete_variant_profile(profile_id, project_id):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM variant_profiles WHERE id = %s AND project_id = %s RETURNING id",
            (profile_id, project_id),
        )
        return cur.fetchone()


# ------------------------------------------------------------------ images
def create_image(project_id, original_key, original_filename, content_type, size_bytes):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO images
                   (project_id, original_key, original_filename, content_type,
                    original_size_bytes, status)
               VALUES (%s, %s, %s, %s, %s, 'pending') RETURNING *""",
            (project_id, original_key, original_filename, content_type, size_bytes),
        )
        return cur.fetchone()


def get_image(image_id):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM images WHERE id = %s", (image_id,))
        return cur.fetchone()


def get_image_by_key(original_key):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM images WHERE original_key = %s", (original_key,))
        return cur.fetchone()


def list_images(project_id, limit=100):
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM images WHERE project_id = %s ORDER BY created_at DESC LIMIT %s",
            (project_id, limit),
        )
        return cur.fetchall()


def update_image_status(image_id, status, error_message=None, processed_at=None):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE images
               SET status = %s, error_message = %s,
                   processed_at = COALESCE(%s, processed_at)
               WHERE id = %s RETURNING *""",
            (status, error_message, processed_at, image_id),
        )
        return cur.fetchone()


def list_stale_pending_images(max_age_hours):
    """Used by the cleanup Lambda's HTTP fallback / admin tooling reference."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT * FROM images
               WHERE status IN ('pending', 'failed')
                 AND created_at < NOW() - (%s || ' hours')::interval""",
            (max_age_hours,),
        )
        return cur.fetchall()


def list_stale_images_with_variants(max_age_hours):
    """
    Used by the cleanup Lambda: every pending/processing/failed image
    older than the threshold, together with any variant keys already
    written for it (covers the edge case where processing failed
    partway through, after some variants were already uploaded to S3).
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, original_key, status, created_at
               FROM images
               WHERE status IN ('pending', 'processing', 'failed')
                 AND created_at < NOW() - (%s || ' hours')::interval""",
            (max_age_hours,),
        )
        images = cur.fetchall()

        results = []
        for image in images:
            cur.execute(
                "SELECT processed_key FROM image_variants WHERE image_id = %s",
                (image["id"],),
            )
            variant_keys = [row["processed_key"] for row in cur.fetchall()]
            results.append({
                "id": image["id"],
                "original_key": image["original_key"],
                "status": image["status"],
                "variant_keys": variant_keys,
            })
        return results


def delete_image(image_id):

    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM images WHERE id = %s RETURNING id", (image_id,))
        return cur.fetchone()


# ---------------------------------------------------------- image variants
def create_image_variant(image_id, variant_profile_id, processed_key, width, height,
                          size_bytes, bytes_saved):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO image_variants
                   (image_id, variant_profile_id, processed_key, width, height,
                    size_bytes, bytes_saved)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (image_id, variant_profile_id, processed_key, width, height, size_bytes, bytes_saved),
        )
        return cur.fetchone()


def list_image_variants(image_id):
    with get_cursor() as cur:
        cur.execute(
            """SELECT iv.*, vp.label, vp.output_format
               FROM image_variants iv
               JOIN variant_profiles vp ON vp.id = iv.variant_profile_id
               WHERE iv.image_id = %s
               ORDER BY vp.label""",
            (image_id,),
        )
        return cur.fetchall()


# -------------------------------------------------------------- analytics
def record_event(project_id, event_type, bytes_saved=0):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO analytics_events (project_id, event_type, bytes_saved)
               VALUES (%s, %s, %s)""",
            (project_id, event_type, bytes_saved),
        )


def get_project_analytics(project_id):
    with get_cursor() as cur:
        cur.execute(
            """SELECT
                   COUNT(DISTINCT i.id) AS total_images,
                   COUNT(DISTINCT i.id) FILTER (WHERE i.status = 'done') AS completed_images,
                   COUNT(DISTINCT i.id) FILTER (WHERE i.status = 'failed') AS failed_images,
                   COALESCE(SUM(i.original_size_bytes), 0) AS total_original_bytes,
                   COALESCE(SUM(iv.size_bytes), 0) AS total_variant_bytes,
                   COALESCE(SUM(iv.bytes_saved), 0) AS total_bytes_saved,
                   COUNT(iv.id) AS total_variants_generated
               FROM images i
               LEFT JOIN image_variants iv ON iv.image_id = i.id
               WHERE i.project_id = %s""",
            (project_id,),
        )
        return cur.fetchone()
