# Undeclared — Master Implementation Plan

Undeclared is an AI-assisted EHR and practice-management platform. It is an independent product; eClinicalWorks V12 is only a functional reference for scope.

## Guiding decisions

| Decision | Choice | Why |
|---|---|---|
| Shape | Modular monolith (`backend/app/*`) + SPA (`frontend/`) | Fastest path that's still maintainable; services can be extracted later |
| DB access | SQLAlchemy 2 (sync) + psycopg3 | Simpler than async, FastAPI runs sync handlers in a threadpool |
| Tenancy | `organization_id` on every tenant row, enforced in a single dependency (`TenantContext`) + regression tests | Isolation is enforced server-side, never trusted from the UI |
| Auth | Short JWT access token (memory) + rotating opaque refresh token (httpOnly cookie, hashed in `user_sessions`) | Revocable sessions, session management UI |
| Integrity | DB triggers make `audit_events` and `clinical_note_versions` append-only; exclusion constraint blocks double-booking | Safety guarantees hold even if app code has a bug |
| AI | `app/ai/provider.py` abstraction; default `simulated` provider (deterministic, no network); `anthropic` provider opt-in | No PHI leaves the system unless explicitly configured with a BAA |
| UI | Tailwind v4 + shadcn-style components owned in-repo (Radix primitives) | One design system, no duplicate component variants |

## Phases, dependencies and acceptance criteria

| # | Phase | Depends on | Acceptance criteria |
|---|---|---|---|
| 0 | Foundation | — | `docker compose up` brings up db/redis/api/worker/web; `/api/health` green; migrations run; seed loads; CI workflow present |
| 1 | Identity & orgs | 0 | Login per role, MFA (TOTP), password reset, invitations, sessions list/revoke, org/clinic CRUD, audit of auth events, cross-tenant access returns 404 (tested) |
| 2 | UI shell | 1 | Sidebar (role-aware), top bar, ⌘K search, notifications, clinic switcher, breadcrumbs, light/dark, responsive |
| 3 | Patients & scheduling | 1,2 | Register (duplicate detection), search, chart shell, calendar day/week/month, conflict-safe booking, check-in → waiting room → check-out |
| 4 | Core EHR | 3 | Encounter from appointment, vitals, problems/diagnoses, allergies, meds, history, SOAP draft → sign (immutable) → addenda, timeline |
| 5 | Document AI | 4 | Upload → OCR/extract → classify → patient-match suggestion → review queue → file to chart (never auto-file uncertain matches) |
| 6 | AI scribe | 4 | Consent → record → transcribe → draft SOAP (AI-labelled) → clinician edit → sign |
| 7 | Orders | 4 | Rx drafts, labs, imaging, referrals, results; clinician approval; simulated transmission clearly labelled |
| 8 | Portal & telehealth | 3,4,7 | Patient login, appointments, intake, messages, released results, video visit room |
| 9 | Billing/RCM | 4 | Charges from encounters, claims (idempotent), mock clearinghouse, denials/appeals, invoices, payments |
| 10 | Advanced AI | 5,6 | Chart assistant with citations, automation studio w/ approvals, AI receptionist sandbox |
| 11 | Analytics | 3–9 | Dashboards from live SQL, care gaps, quality measures, CSV export |
| 12 | Integrations & deploy | all | FHIR R4 read endpoints, adapter interfaces, AWS reference architecture, backup/restore runbook, readiness checklist |

## Working rules

- One vertical slice at a time (DB → API → UI → test), app runnable after every phase.
- Every visible action works, is disabled with a reason, or says "not yet available".
- Simulated integrations are labelled `SIMULATED` in UI and API payloads.
- Progress is tracked in `IMPLEMENTATION_PROGRESS.md`.
