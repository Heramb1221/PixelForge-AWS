#!/usr/bin/env bash
# infra/deploy.sh
# ------------------
# Runs ON the EC2 instance (after code has been copied to /opt/pixelforge)
# to set up the Python environment, systemd service, and nginx reverse
# proxy. Re-run any time you deploy a new version of the code.
#
# Usage:  cd /opt/pixelforge && sudo bash infra/deploy.sh
#
# MANUAL STEP REQUIRED FIRST: create /opt/pixelforge/.env from
# .env.example with real values (RDS endpoint/password, secret keys).
# This script refuses to continue without it.

set -euo pipefail

APP_DIR="/opt/pixelforge"
VENV_DIR="${APP_DIR}/venv"
SERVICE_NAME="pixelforge"
APP_USER="ubuntu"

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: run this script with sudo." >&2
    exit 1
fi

if [ ! -f "${APP_DIR}/.env" ]; then
    echo "ERROR: ${APP_DIR}/.env not found. Copy .env.example to .env and fill in real values first." >&2
    exit 1
fi

echo "==> Installing system packages"
apt-get update -y
apt-get install -y python3-venv python3-pip nginx

echo "==> Creating virtual environment"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "==> Initializing database schema"
set -a
source "${APP_DIR}/.env"
set +a
"${VENV_DIR}/bin/python" "${APP_DIR}/db/init_db.py"

echo "==> Writing systemd service"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=PixelForge Flask app (Gunicorn)
After=network.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${VENV_DIR}/bin/gunicorn --workers 3 --bind 127.0.0.1:8000 --access-logfile - --error-logfile - wsgi:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "==> Writing nginx reverse proxy config"
cat > "/etc/nginx/sites-available/${SERVICE_NAME}" <<'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
ln -sf "/etc/nginx/sites-available/${SERVICE_NAME}" "/etc/nginx/sites-enabled/${SERVICE_NAME}"
rm -f /etc/nginx/sites-enabled/default

chown -R "${APP_USER}:${APP_USER}" "$APP_DIR"

echo "==> Starting services"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
systemctl restart nginx

echo "==> Deployment complete."
echo "    Check app status:   systemctl status ${SERVICE_NAME}"
echo "    Tail app logs:      journalctl -u ${SERVICE_NAME} -f"
echo "    App should now be reachable at http://<ec2-public-ip>/"
