# Undeclared

AI-assisted EHR and practice-management platform (modular monolith: FastAPI + PostgreSQL + React).

> **Development build.** All data is synthetic. Undeclared is **not** HIPAA-certified or clinically validated — see [docs/SECURITY_AND_COMPLIANCE.md](docs/SECURITY_AND_COMPLIANCE.md).

## Quick start (Docker)

```bash
docker compose up --build
```

- Web: http://localhost:8080
- API docs: http://localhost:8011/api/docs

The API container runs migrations and loads the synthetic seed on start (`SEED_ON_START=true` in `.env.docker`).

## Quick start (local processes)

Requirements: Python 3.13 + [uv](https://docs.astral.sh/uv/), Node 22+, PostgreSQL 16 (with `btree_gist`, `pg_trgm`), optional Redis.

```bash
# Database (once)
createuser -s undeclared --pwprompt        # password: undeclared
createdb -O undeclared undeclared
createdb -O undeclared undeclared_test

# Backend
cd backend
cp .env.example .env                        # CELERY_EAGER=true → no Redis needed
uv sync
uv run alembic upgrade head
uv run python -m app.seed                   # --reset to wipe and reseed
uv run uvicorn app.main:app --reload --port 8010

# Frontend (new terminal)
cd frontend
npm install
API_PROXY_TARGET=http://localhost:8010 npm run dev   # http://localhost:5173
```

## Development accounts

Password for every account: `Undeclared!2026`

| Email | Roles |
|---|---|
| `admin@undeclared.dev` | Super Admin (platform) |
| `clinicadmin@harborview.dev` | Clinic Admin |
| `dr.chen@harborview.dev` | Doctor |
| `dr.okafor@harborview.dev` | Doctor + Clinic Admin |
| `nurse.rivera@harborview.dev` | Nurse / MA |
| `frontdesk@harborview.dev` | Receptionist |
| `billing@harborview.dev` | Billing Specialist |
| `patient@harborview.dev` | Patient (portal) |
| `dr.lake@lakeside.dev` | Doctor + Admin in a **second organization** (tenant-isolation checks) |

Seed extras: a restricted (VIP) chart "Victor Ashford" for break-the-glass, and "Jonathan Brennan" for duplicate detection.

## Checks

```bash
cd backend && uv run ruff check app tests && uv run pytest -q     # uses the undeclared_test DB
cd frontend && npm run typecheck && npm run build
```

## Common commands

| Task | Command |
|---|---|
| New migration | `cd backend && uv run alembic revision --autogenerate -m "..."` |
| Apply migrations | `uv run alembic upgrade head` |
| Worker (non-eager) | `uv run celery -A app.worker worker -B -l info` |
| Reseed | `uv run python -m app.seed --reset` |

## Docs

[Plan](docs/MASTER_IMPLEMENTATION_PLAN.md) · [Progress](docs/IMPLEMENTATION_PROGRESS.md) · [Architecture](docs/ARCHITECTURE.md) · [Database](docs/DATABASE_DESIGN.md) · [UI/UX](docs/UI_UX_SYSTEM.md) · [Security](docs/SECURITY_AND_COMPLIANCE.md) · [Integrations](docs/INTEGRATIONS.md)
