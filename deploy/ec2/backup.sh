#!/usr/bin/env bash
# Nightly backup on the EC2 host (installed in cron by the deployment): database dump + document storage, kept 7 days.
#   /opt/undeclared/backup.sh            → /opt/undeclared/backups/undeclared-<UTC>.dump (+ -storage.tar.gz, .sha256)
# Restore (into an EMPTY database; see docs/AWS_DEPLOYMENT.md):
#   sudo docker compose exec -T db pg_restore -U undeclared -d undeclared --no-owner < backups/undeclared-<stamp>.dump
# Copy backups off the instance regularly (a single disk is not a backup); the .env file must be backed up separately.
set -euo pipefail
cd /opt/undeclared
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT=backups
umask 077
sudo docker compose exec -T db pg_dump -U undeclared --format=custom --no-owner --no-privileges undeclared > "$OUT/undeclared-$STAMP.dump"
sudo docker compose run --rm --no-deps -T --entrypoint sh -u 0 -v "$PWD/$OUT:/out" api -c "tar -czf /out/undeclared-$STAMP-storage.tar.gz -C /app/var/storage ." 2>/dev/null || true
( cd "$OUT" && sha256sum undeclared-"$STAMP"* > "undeclared-$STAMP.sha256" )
find "$OUT" -name 'undeclared-*' -mtime +7 -delete
echo "backup written: $OUT/undeclared-$STAMP.dump ($(du -h "$OUT/undeclared-$STAMP.dump" | cut -f1))"
