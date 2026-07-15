"""
run.py
------
Local development entrypoint. Do NOT use this in production - use
wsgi.py behind Gunicorn (see infra/deploy.sh and instructions.md).
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=app.config["DEBUG"])
