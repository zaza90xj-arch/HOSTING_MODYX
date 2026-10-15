#!/usr/bin/env bash
# MODYX VPS HOSTING installer for Ubuntu 22.04/24.04 (x86_64 or arm64). Run on the server as root:
#   sudo bash deploy/install.sh https://panel.example.com
# NOTE: written for a real Ubuntu server and NOT yet tested on one. Read it before running it.
set -euo pipefail

BASE_URL="${1:-}"
[ -n "$BASE_URL" ] || { echo "Usage: sudo bash deploy/install.sh <BASE_URL, e.g. https://panel.example.com or http://SERVER_IP>"; exit 1; }
[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }

APP_DIR=/opt/modyx-vps
DATA_DIR=/var/lib/modyx
ENV_FILE=/etc/modyx/env

apt-get update
apt-get install -y python3 python3-venv python3-pip git nginx

id modyx >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin modyx
mkdir -p "$APP_DIR" "$DATA_DIR/instance" "$DATA_DIR/storage" /etc/modyx
cp -r . "$APP_DIR"/
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f "$ENV_FILE" ]; then
  COOKIE=true; case "$BASE_URL" in http://*) COOKIE=false ;; esac
  cat > "$ENV_FILE" <<ENVEOF
MODYX_ENV=production
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
BASE_URL=$BASE_URL
COOKIE_SECURE=$COOKIE
DATABASE_PATH=$DATA_DIR/instance/modyx.db
STORAGE_ROOT=$DATA_DIR/storage
ALLOW_REGISTRATION=false
ENVEOF
fi
chown -R modyx:modyx "$DATA_DIR" "$APP_DIR"
chown root:modyx "$ENV_FILE"; chmod 640 "$ENV_FILE"

cp "$APP_DIR/deploy/modyx.service" /etc/systemd/system/modyx.service
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/modyx
ln -sf /etc/nginx/sites-available/modyx /etc/nginx/sites-enabled/modyx
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl daemon-reload
systemctl enable --now modyx
systemctl reload nginx

echo
echo "Panel is running behind nginx. Open: $BASE_URL"
echo "The FIRST account you register becomes the owner; registration then closes."
echo "Firewall: this script did not change it. Allow only 22, 80 and 443 (e.g. ufw allow OpenSSH; ufw allow 'Nginx Full'; ufw enable)."
echo "HTTPS: point a domain at this server, then: apt install certbot python3-certbot-nginx && certbot --nginx -d YOUR_DOMAIN"
echo "On Oracle Cloud also open ports 80/443 in the VCN security list (provider firewall)."
