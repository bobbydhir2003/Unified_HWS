# Implementation progress

_Last updated: 2026-11-19_

## Status

| Phase | Status |
|---|---|
| 0 Foundation | ✅ Complete |
| 1 Identity, security, orgs | ✅ Complete |
| 2 UI shell | ✅ Complete |
| 3 Patients & scheduling | ✅ Complete |
| 4 Core EHR | ✅ Complete |
| 5 Document AI | ⏭ Next |
| 6–12 | Not started |

**Milestone reached:** a patient can go from registration → booking → check-in → rooming → encounter → vitals → SOAP note → diagnosis → signed note → completed visit → check-out, all persisted and audited.

## Implemented

- **Foundation:** FastAPI modular monolith, SQLAlchemy 2, Alembic (0001–0002), PostgreSQL, Redis/Celery (+ eager mode), Docker Compose (db, redis, api, worker, web/nginx), health/readiness endpoints, JSON logging, synthetic seed (2 orgs, 9 accounts, 55 patients, ~200 appointments, ~70 signed visits), GitHub Actions CI.
- **Identity:** login, lockout, rotating refresh sessions, logout, session list/revoke, TOTP MFA (+ optional enforcement), forgot/reset password, change password, invitations (create/accept/revoke), multi-role memberships, clinic scoping, org/clinic CRUD, staff management with provider profiles, audit log viewer, outbox, system status.
- **UI shell:** role-filtered collapsible sidebar, org & clinic switcher, breadcrumbs (with dynamic patient labels), ⌘K/`/` patient search, notifications (live polling), user menu, light/dark/system theme, mobile drawer, synthetic-data flag.
- **Patients:** registration with duplicate detection (trigram name + DOB + phone + email), search (name tokens, MRN, DOB, phone), chart with sticky banner and allergies, demographics edit, insurance (add/edit, simulated eligibility), front-desk notes, restricted charts + break-the-glass.
- **Scheduling:** appointment types, provider weekly availability editor, open-slot finder, day/week/month calendar in clinic timezone with availability shading and click-to-book, booking/rescheduling with conflict detection (app + DB exclusion), availability override, status workflow (confirm, check-in, room, check-out, cancel w/ reason, no-show), front-desk board with wait timers, arrival notifications to providers, reminder task.
- **EHR:** encounters (from appointment or unscheduled), vitals (imperial entry, trends chart, abnormal flags), problems/medications/allergies/history with entered-in-error, ICD-10 picker, encounter diagnoses (+ add to problem list), templates, SOAP notes with explicit versioned saves, optimistic concurrency, ⌘S, unsaved-change guard, sign (A/P required, AI attestation), DB-frozen signed notes, addenda, version history, encounter completion rules, patient timeline, "My visits".
- **Portal (minimal):** patient login sees own appointments, allergies, medications, latest vitals.

## Test results (2026-11-19)

| Check | Result |
|---|---|
| `ruff check app tests` | ✅ pass |
| Backend import/startup | ✅ |
| Migrations up → down → up, `alembic check` | ✅ no drift |
| `pytest` (20 tests: auth, MFA, lockout, sessions, authz, tenant isolation, restricted charts, portal scoping, audit immutability, duplicates, appointment conflicts, full visit + note integrity) | ✅ 20 passed |
| Frontend `tsc --noEmit` (TS 7) | ✅ 0 errors |
| Frontend `vite build` | ✅ (bundle 1.37 MB / 405 kB gz — warning) |
| API smoke across all screens × 7 roles | ✅ 0 server errors (found & fixed INET serialization bug) |
| Browser E2E (headless Chrome via Playwright): register → … → check-out | ✅ no page errors (found & fixed override-button and UTC-message bugs) |
| `docker compose up --build` | ✅ all services healthy; Celery task round-trip verified |

Browser E2E and API smoke scripts live in `e2e/` (manual; not yet in CI).

## Known issues / limitations

- Frontend bundle not code-split yet (single ~405 kB gz chunk).
- ICD-10 search covers a ~120-code common subset.
- Reminder delivery and eligibility are simulated.
- No RLS yet; isolation relies on application layer + tests.
- Portal is read-only and minimal until phase 8.
- Port 8000 is used by another local service on the dev machine; docs use 8010.

## Next steps

1. Phase 5 — Document AI: `documents` + `ai_jobs` tables, secure upload/download, OCR/extraction pipeline behind `app/ai` provider abstraction (simulated by default), classification, patient-match suggestions with confidence, review queue, file-to-chart.
2. Phase 6 — AI scribe on top of the same provider abstraction and the existing note-versioning (`source='ai_scribe'`).
3. Route-level code splitting; run `e2e/` in CI.
