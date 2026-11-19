#!/usr/bin/env bash
# Logical backup of the Undeclared database (+ local document storage when used).
# Usage: DATABASE_URL=postgresql://user:pass@host:5432/db ops/backup.sh <output-dir>
# Production: prefer managed snapshots (RDS automated backups + PITR) and S3 versioning; use this for portable copies/drills.
set -euo pipefail
OUT_DIR="${1:?usage: backup.sh <output-dir>}"
URL="${DATABASE_URL:?DATABASE_URL is required}"
URL="${URL/postgresql+psycopg:/postgresql:}"   # accept the SQLAlchemy form
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT_DIR"
DUMP="$OUT_DIR/undeclared-$STAMP.dump"
pg_dump --format=custom --no-owner --no-privileges --file="$DUMP" "$URL"
if [ -n "${STORAGE_LOCAL_PATH:-}" ] && [ -d "$STORAGE_LOCAL_PATH" ]; then
  tar -czf "$OUT_DIR/undeclared-storage-$STAMP.tar.gz" -C "$STORAGE_LOCAL_PATH" .
fi
( cd "$OUT_DIR" && shasum -a 256 undeclared-*"$STAMP"* > "undeclared-$STAMP.sha256" )
echo "backup written: $DUMP"
