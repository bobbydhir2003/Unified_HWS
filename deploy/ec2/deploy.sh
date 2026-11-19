#!/usr/bin/env bash
# Build linux/amd64 images locally, ship them to the EC2 host, and (re)start the stack. Run from the repository root:
#   EC2_HOST=3.19.143.26 EC2_KEY=~/Downloads/Unified_HMS.pem EC2_KNOWN_HOSTS=~/.ssh/known_hosts deploy/ec2/deploy.sh
# The release tag is the current git commit; the working tree must be clean so the deployed code matches a commit.
set -euo pipefail
: "${EC2_HOST:?EC2_HOST is required}"; : "${EC2_KEY:?EC2_KEY (path to the .pem) is required}"
KNOWN="${EC2_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}"
SSH=(ssh -i "$EC2_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" "ubuntu@$EC2_HOST")
SCP=(scp -q -i "$EC2_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN")
APP=/opt/undeclared

[ -z "$(git status --porcelain)" ] || { echo "working tree not clean — commit first" >&2; exit 1; }
RELEASE="$(git rev-parse --short=12 HEAD)"
echo "release $RELEASE"

docker buildx build --platform linux/amd64 -t "undeclared-api:$RELEASE" --load backend
docker buildx build --platform linux/amd64 -t "undeclared-web:$RELEASE" --load frontend

echo "uploading images…"
docker save "undeclared-api:$RELEASE" "undeclared-web:$RELEASE" | gzip -1 | "${SSH[@]}" 'gunzip | sudo docker load'
"${SCP[@]}" deploy/ec2/docker-compose.yml deploy/ec2/Caddyfile deploy/ec2/backup.sh "ubuntu@$EC2_HOST:$APP/"

"${SSH[@]}" bash -s "$RELEASE" <<'REMOTE'
set -euo pipefail
cd /opt/undeclared
PREV="$(grep '^RELEASE=' .env | cut -d= -f2)"
sed -i "s/^RELEASE=.*/RELEASE=$1/" .env
echo "$PREV" > .previous_release
PROFILE=""; grep -q '^ENABLE_HTTPS=true' .env && PROFILE="--profile https"
sudo docker compose $PROFILE up -d --remove-orphans
sudo docker compose ps
# keep the current and previous images only
sudo docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^undeclared-(api|web):' | grep -vE ":($1|$PREV)$" | xargs -r sudo docker rmi >/dev/null || true
REMOTE
echo "deployed $RELEASE (rollback: set RELEASE=<previous> in $APP/.env and run 'sudo docker compose up -d')"
