#!/bin/sh
# Installs/updates the notifier on Debian. Run as root from /opt/f1-discord-notifier.
set -eu

APP_DIR=/opt/f1-discord-notifier
cd "$(dirname "$0")"
if [ "$(pwd)" != "$APP_DIR" ]; then
    echo "Please clone the repo to $APP_DIR (currently in $(pwd))" >&2
    exit 1
fi

apt-get update
apt-get install -y python3 python3-venv tzdata ca-certificates sudo

id f1notify >/dev/null 2>&1 || useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin f1notify

[ -d venv ] || python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

mkdir -p data
chown -R f1notify:f1notify data
if [ ! -f .env ]; then
    cp .env.example .env
    echo ">>> Created $APP_DIR/.env - edit it before starting the service!"
fi
chown root:f1notify .env
chmod 640 .env

# `f1notify test`, `f1notify upcoming`, ... from anywhere
cat > /usr/local/bin/f1notify <<EOF
#!/bin/sh
cd $APP_DIR && exec sudo -u f1notify $APP_DIR/venv/bin/python -m f1notify "\$@"
EOF
chmod 755 /usr/local/bin/f1notify

cp f1notify.service /etc/systemd/system/f1notify.service
systemctl daemon-reload
systemctl enable f1notify.service
systemctl restart f1notify.service || true
echo ">>> Done. Check status with: systemctl status f1notify   logs: journalctl -u f1notify -f"
