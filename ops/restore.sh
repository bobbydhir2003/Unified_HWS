#!/usr/bin/env bash
# Restore a backup produced by backup.sh into a TARGET database.
# Usage: TARGET_DATABASE_URL=postgresql://user:pass@host:5432/newdb ops/restore.sh <dump-file> [--force]
# Refuses to restore into a database that already has tables unless --force is given.
set -euo pipefail
DUMP="${1:?usage: restore.sh <dump-file> [--force]}"
FORCE="${2:-}"
URL="${TARGET_DATABASE_URL:?TARGET_DATABASE_URL is required}"
URL="${URL/postgresql+psycopg:/postgresql:}"
SUMS="${DUMP%.dump}.sha256"
if [ -f "$SUMS" ]; then ( cd "$(dirname "$DUMP")" && shasum -a 256 -c "$(basename "$SUMS")" --ignore-missing ); fi
TABLES="$(psql "$URL" -Atc "select count(*) from information_schema.tables where table_schema='public'")"
if [ "$TABLES" != "0" ] && [ "$FORCE" != "--force" ]; then
  echo "target database already has $TABLES tables; refusing (pass --force to restore over it)" >&2
  exit 1
fi
psql "$URL" -qc "create extension if not exists btree_gist; create extension if not exists pg_trgm;"
pg_restore --no-owner --no-privileges --exit-on-error ${FORCE:+--clean --if-exists} --dbname="$URL" "$DUMP"
echo "restored $DUMP"
psql "$URL" -Atc "select 'alembic_version=' || version_num from alembic_version"
