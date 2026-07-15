"""
wsgi.py
-------
Production entrypoint. Run with Gunicorn on EC2:

    gunicorn --workers 3 --bind 0.0.0.0:8000 wsgi:app

See infra/deploy.sh for the systemd unit that wraps this command.
"""
from app import create_app

app = create_app()
