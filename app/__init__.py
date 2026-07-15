"""
app/__init__.py
----------------
Flask application factory. Wires together config, the DB pool, the S3
service, and blueprints. Keeping this as a factory (rather than a
module-level `app = Flask(__name__)`) makes the app testable and keeps
wsgi.py / run.py thin.
"""
import logging

from flask import Flask
from datetime import timedelta

from app.config import Config
from app.utils.logger import configure_logging

logger = logging.getLogger(__name__)


def create_app(config_object=Config):
    configure_logging(debug=config_object.DEBUG)
    config_object.validate()

    # Imported lazily so that importing submodules of `app` for unit
    # testing (e.g. app.utils.validators) doesn't require psycopg2/boto3
    # testing (e.g. app.utils.validators) doesn't require psycopg2/boto3
    # to be installed or configured.
    from app.services.s3_service import S3Service

    app = Flask(__name__)
    app.config.from_object(config_object)
    app.permanent_session_lifetime = timedelta(days=7)

    # Shared resources, attached to the app object for easy access in routes.
    app.s3_service = S3Service(
        region=config_object.AWS_REGION,
        originals_bucket=config_object.S3_ORIGINALS_BUCKET,
        processed_bucket=config_object.S3_PROCESSED_BUCKET,
        url_expiry_seconds=config_object.PRESIGNED_URL_EXPIRY_SECONDS,
    )

    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.projects import projects_bp
    from app.routes.images import images_bp
    from app.routes.internal import internal_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(images_bp)
    app.register_blueprint(internal_bp)

    @app.errorhandler(404)
    def not_found(_e):
        return {"error": "Not found"}, 404

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("Unhandled server error: %s", e)
        return {"error": "Internal server error"}, 500

    logger.info("PixelForge app created (env=%s, debug=%s)", config_object.ENV, config_object.DEBUG)
    return app
