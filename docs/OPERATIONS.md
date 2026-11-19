# Operations runbook

## Health & monitoring

| Signal | Where |
|---|---|
| Liveness | `GET /api/health` |
| Readiness (DB, Redis, storage) | `GET /api/health/ready` → 503 when degraded |
| Metrics (Prometheus text) | `GET /api/metrics` — request counts by method/route-template/status class and latency histograms. Route templates only (no ids, no PHI). Expose internally only. |
| Logs | JSON on stdout: request id, method, path (no query string), status, latency. Never bodies or PHI. |
| Audit | Admin › Audit log (append-only table) |
| AI | Admin › AI monitoring (`ai_jobs`: provider, model, latency, failures, PHI-external flag) |
| App status | Admin › System status (dependencies, schema version, adapters, AI policy) |

Suggested alerts: readiness failing > 2 min; 5xx rate > 1 % for 5 min; p95 latency > 2 s; Celery worker healthcheck failing; `ai_jobs` failures spike; any `phi_sent_externally=true` when policy says blocked; login 429s spike (credential stuffing).

## Backups

| Layer | Mechanism | Retention / RPO |
|---|---|---|
| PostgreSQL | RDS automated backups with point-in-time recovery | 14 days, RPO ≈ 5 min |
| PostgreSQL + S3 | AWS Backup daily plan | 35 days |
| Documents | S3 versioning (+ AWS Backup) | object versions retained |
| Portable copy / drills | `ops/backup.sh` (pg_dump custom format + local storage tarball + SHA-256 manifest) | per run |

Target RTO: 1 hour for a database restore to a new instance.

## Restore procedure

1. Create an **empty** target database (new RDS instance from PITR/snapshot in production, or `createdb` for a drill).
2. `TARGET_DATABASE_URL=postgresql://… ops/restore.sh backups/undeclared-<stamp>.dump` — verifies the checksum, refuses non-empty targets (unless `--force`), installs required extensions, restores, prints the schema version.
3. Restore documents (S3 version restore, or untar the storage archive into `STORAGE_LOCAL_PATH`).
4. Point the API at the restored database; run `alembic upgrade head` if restoring an older schema.
5. Smoke test: readiness endpoint, sign in, open a chart, open a document, check the audit log continues.

### Last drill — 2026-11-19 (local)

Backup of the development database → restore into a fresh database `undeclared_restore_drill`:
schema `0008`; row counts identical for patients (58), appointments (211), encounters (72), clinical_notes (71),
audit_events (129), claims (57), payments (68), documents (2); the append-only audit trigger blocked an UPDATE on the
restored copy; a second restore without `--force` was refused. The drill database was dropped afterwards.

## Common tasks

| Task | Command |
|---|---|
| Apply migrations | `uv run alembic upgrade head` |
| Roll back one migration | `uv run alembic downgrade -1` (test on a copy first) |
| Re-run a failed document | Documents › open › Reprocess |
| Re-run a failed automation | Automation studio › Activity › Retry |
| Revoke a user's sessions | Staff › deactivate user (sessions are rejected on next request) |
| Rotate `SECRET_KEY` | update the secret, redeploy — all sessions must sign in again |

## Incident response (outline)

1. Contain (revoke sessions/keys, disable affected integration adapter or workflow).
2. Preserve evidence (audit log is append-only; export it).
3. Assess PHI exposure using `audit_events` (who accessed which `patient_id`) and `ai_jobs.phi_sent_externally`.
4. Notify per HIPAA Breach Notification Rule timelines and BAAs.
5. Post-incident review and regression test.
