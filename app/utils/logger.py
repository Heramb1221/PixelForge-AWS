"""
app/utils/logger.py
--------------------
Configures application-wide logging. Writes structured, timestamped
log lines to stdout so they are picked up by whatever process manager
(systemd/journalctl) runs the app on EC2, and can optionally be shipped
to CloudWatch Logs via the CloudWatch agent.
"""
import logging
import sys


def configure_logging(debug=False):
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers if configure_logging is called more than once
    # (e.g. once by the app factory, once by the WSGI entrypoint).
    root.handlers = [handler]

    # Quiet down noisy third-party loggers unless we're in debug mode.
    if not debug:
        logging.getLogger("botocore").setLevel(logging.WARNING)
        logging.getLogger("boto3").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
