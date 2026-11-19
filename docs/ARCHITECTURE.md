# Architecture

## Shape

```
frontend/ (React SPA, Vite)  ──/api──▶  backend/ (FastAPI modular monolith)  ──▶ PostgreSQL 16
        nginx in prod                         │        └─ Celery worker + beat ──▶ Redis
                                              └─ object storage (local dir / S3)
```

One deployable API plus one worker image (same code). No microservices; modules are folders.

## Backend layout (`backend/app`)

| Path | Responsibility |
|---|---|
| `core/config.py` | All settings (env vars, pydantic-settings) |
| `core/security.py` | Argon2 hashing, JWT, opaque tokens |
| `core/permissions.py` | Role → permission map (single source of truth) |
| `api/deps.py` | `get_auth_user`, `TenantContext` (`get_ctx`), `require(perm)` |
| `api/routers/*` | HTTP layer per domain: `auth`, `admin`, `patients`, `scheduling`, `clinical`, `workspace`, `health` |
| `services/*` | Business rules that span requests: `patients` (access, MRN, duplicates), `notes` (versioning/sign), `audit`, `identity`, `notify`, `storage` |
| `models/*` | SQLAlchemy 2 models by domain |
| `schemas/*` | Pydantic v2 request/response contracts |
| `tasks.py`, `worker.py` | Celery tasks + beat schedule |
| `seed.py` | Deterministic synthetic dataset |

### Request flow

1. `get_auth_user` validates the bearer JWT **and** that its session row is not revoked.
2. `get_ctx` resolves the organization from `X-Organization-Id` (or the only membership), loads roles → permissions and the clinic scope, and enforces MFA enrollment when configured.
3. Endpoints call `ctx.require(...)` / `require(...)` and load tenant rows via helpers (`get_patient`, `_owned`) that return **404** for cross-tenant ids.
4. Writes add an `audit_events` row in the same transaction.

### Tenancy

Every tenant table carries `organization_id` (`OrgScoped` mixin). Isolation is enforced server-side in `TenantContext` and covered by tests in `tests/test_security.py`. PostgreSQL row-level security is a planned hardening step (see Security doc).

### Auth

- Access token: JWT (HS256), 15 min, held in memory by the SPA.
- Refresh token: opaque, rotated on every use, stored hashed in `user_sessions`, sent as `httpOnly; SameSite=Strict` cookie scoped to `/api/auth`.
- MFA: TOTP (pyotp). Login returns `mfa_required` + short-lived MFA token when enabled.
- Lockout after 5 failures for 15 minutes.

## Frontend layout (`frontend/src`)

| Path | Responsibility |
|---|---|
| `lib/api.ts` | fetch wrapper, token + org headers, single-flight refresh on 401 |
| `lib/auth.tsx` | session state, membership/clinic selection, `can()` |
| `lib/tz.ts` | clinic-timezone math for the calendar |
| `components/ui/*` | design-system primitives (shadcn-style, Radix) |
| `components/common/*` | app patterns: page header, empty/error/loading, confirm, unsaved-changes guard, form dialog, ICD-10 picker |
| `components/layout/*` | app shell, nav, ⌘K search |
| `features/<domain>/*` | screens |

Server state lives in TanStack Query; there is no global client store.

## Background work

Celery with Redis. `CELERY_EAGER=true` runs tasks inline for local dev/tests. Beat currently schedules appointment reminders (delivery simulated to the outbox).

## AI

`app/ai/provider.py` defines the provider interface. `get_provider()` returns:

- `SimulatedProvider` (default): deterministic, local, rule-based. Labeled "Rule-based simulation" in the UI.
- `AnthropicProvider`: Claude (`claude-opus-5-5` by default) via the official SDK, structured JSON output validated by Pydantic, server-side refusal fallbacks, typed error handling. Raises `AIPolicyError` for PHI unless `AI_PHI_ALLOWED=true`.

Every call is recorded in `ai_jobs` (provider, model, whether PHI left the system, tokens, latency, errors). AI output is always a draft: documents land in `needs_review`; patient matching is rule-based and transparent (score + reasons) and only *suggests* when the top candidate is strong and clearly ahead.

### Document pipeline

`POST /documents` → magic-byte validation → object storage (`{org}/documents/{id}/{sha256}`) → `documents` row + `ai_jobs` row → Celery `process_document` → text extraction (pypdf) → provider analysis → `match_patients` → `needs_review`. Filing (`POST /documents/{id}/file`) requires `documents:review` and an explicit identity attestation.
