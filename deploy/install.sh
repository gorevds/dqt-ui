#!/usr/bin/env bash
# Idempotent installer for DQT on Ubuntu 22.04+ / Debian 12+.
# Runs as root. Pulls the repo to /opt/dqt, builds a venv, installs the systemd
# unit, configures nginx for $DOMAIN, and obtains a Let's Encrypt cert.
#
# Usage:
#   DOMAIN=dqt.example.com REPO=https://github.com/USER/DQT-UI.git ./install.sh
#
# Required env: DOMAIN, REPO
# Optional env: EMAIL (for certbot, default admin@$DOMAIN), BRANCH (default main)
set -euo pipefail

DOMAIN="${DOMAIN:?DOMAIN is required}"
REPO="${REPO:?REPO is required}"
BRANCH="${BRANCH:-main}"
EMAIL="${EMAIL:-admin@${DOMAIN}}"
INSTALL_DIR="${INSTALL_DIR:-/opt/dqt}"

echo "==> Installing DQT for $DOMAIN from $REPO ($BRANCH)"

apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git nginx certbot python3-certbot-nginx

if [ ! -d "$INSTALL_DIR/.git" ]; then
    git clone --depth 1 --branch "$BRANCH" "$REPO" "$INSTALL_DIR"
else
    git -C "$INSTALL_DIR" fetch --depth 1 origin "$BRANCH"
    git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
fi

if [ ! -d "$INSTALL_DIR/.venv" ]; then
    python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip wheel
"$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR"

chown -R www-data:www-data "$INSTALL_DIR"

install -m 644 "$INSTALL_DIR/deploy/dqt.service" /etc/systemd/system/dqt.service
systemctl daemon-reload
systemctl enable dqt.service
systemctl restart dqt.service

# nginx vhost — substitute domain
sed "s/dqt.gorev.space/$DOMAIN/g" "$INSTALL_DIR/deploy/nginx.conf" > /etc/nginx/sites-available/dqt
ln -sf /etc/nginx/sites-available/dqt /etc/nginx/sites-enabled/dqt
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# TLS via certbot (idempotent: --keep-until-expiring)
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect --keep-until-expiring

echo "==> DQT is up at https://$DOMAIN"
systemctl --no-pager status dqt.service | head -10
