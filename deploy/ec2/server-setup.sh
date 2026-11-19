#!/usr/bin/env bash
# One-time (idempotent) preparation of the EC2 host. Run on the server as the ubuntu user:  bash server-setup.sh
# Installs Docker from Ubuntu's archive, adds a 1 GB swap file, enables a host firewall (SSH/HTTP/HTTPS only), creates
# /opt/undeclared and generates /opt/undeclared/.env with fresh secrets if it does not exist yet. Never overwrites .env.
set -euo pipefail
APP=/opt/undeclared

sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io docker-compose-v2 openssl ufw >/dev/null
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

# Swap: protects the 2 GB host from OOM during migrations/backups.
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/90-undeclared.conf >/dev/null && sudo sysctl -q -p /etc/sysctl.d/90-undeclared.conf
fi

# Host firewall (defence in depth; the AWS security group is the primary control). SSH is allowed before enabling.
sudo ufw allow OpenSSH >/dev/null
sudo ufw allow 80/tcp >/dev/null
sudo ufw allow 443/tcp >/dev/null
sudo ufw --force enable >/dev/null

# Docker log rotation defaults.
if [ ! -f /etc/docker/daemon.json ]; then
  echo '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}' | sudo tee /etc/docker/daemon.json >/dev/null
  sudo systemctl restart docker
fi

sudo mkdir -p "$APP/backups" && sudo chown -R "$USER":"$USER" "$APP" && chmod 750 "$APP" "$APP/backups"

if [ ! -f "$APP/.env" ]; then
  umask 077
  rnd() { openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-"$1"; }
  PG="$(rnd 32)"
  cat > "$APP/.env" <<EOF
# Generated $(date -u +%FT%TZ) by server-setup.sh. Secrets live only here (mode 600). Back this file up securely:
# losing CREDENTIALS_ENCRYPTION_KEY makes stored AI provider keys unreadable.
RELEASE=unset
ENVIRONMENT=staging
POSTGRES_PASSWORD=$PG
DATABASE_URL=postgresql+psycopg://undeclared:$PG@db:5432/undeclared
REDIS_URL=redis://redis:6379/0
CELERY_EAGER=false
ENGINE_INPROCESS_SCHEDULER=false
SECRET_KEY=$(rnd 64)
CREDENTIALS_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')
COOKIE_SECURE=true
CORS_ORIGINS=["http://localhost:8080"]
FRONTEND_URL=http://localhost:8080
STORAGE_BACKEND=local
STORAGE_LOCAL_PATH=/app/var/storage
AI_PROVIDER=simulated
AI_PHI_ALLOWED=false
RATE_LIMIT_ENABLED=true
SEED_ON_START=false
SEED_DEMO_PASSWORD=$(rnd 20)
SITE_ADDRESS=localhost
EOF
  chmod 600 "$APP/.env"
  echo "created $APP/.env with new secrets"
else
  echo "$APP/.env already exists — left unchanged"
fi
echo "server ready: $(docker --version 2>/dev/null || sudo docker --version)"
