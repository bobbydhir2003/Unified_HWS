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
| 5 Document AI | ✅ Complete |
| 6 AI scribe | ✅ Complete |
| 7 Clinical orders | ✅ Complete |
| 8 Portal & telehealth | ⏭ Next |
| 9–12 | Not started |

**Milestone reached:** a patient can go from registration → booking → check-in → rooming → encounter → vitals → SOAP note → diagnosis → signed note → completed visit → check-out, all persisted and audited.

## Implemented

- **Foundation:** FastAPI modular monolith, SQLAlchemy 2, Alembic (0001–0002), PostgreSQL, Redis/Celery (+ eager mode), Docker Compose (db, redis, api, worker, web/nginx), health/readiness endpoints, JSON logging, synthetic seed (2 orgs, 9 accounts, 55 patients, ~200 appointments, ~70 signed visits), GitHub Actions CI.
- **Identity:** login, lockout, rotating refresh sessions, logout, session list/revoke, TOTP MFA (+ optional enforcement), forgot/reset password, change password, invitations (create/accept/revoke), multi-role memberships, clinic scoping, org/clinic CRUD, staff management with provider profiles, audit log viewer, outbox, system status.
- **UI shell:** role-filtered collapsible sidebar, org & clinic switcher, breadcrumbs (with dynamic patient labels), ⌘K/`/` patient search, notifications (live polling), user menu, light/dark/system theme, mobile drawer, synthetic-data flag.
- **Patients:** registration with duplicate detection (trigram name + DOB + phone + email), search (name tokens, MRN, DOB, phone), chart with sticky banner and allergies, demographics edit, insurance (add/edit, simulated eligibility), front-desk notes, restricted charts + break-the-glass.
- **Scheduling:** appointment types, provider weekly availability editor, open-slot finder, day/week/month calendar in clinic timezone with availability shading and click-to-book, booking/rescheduling with conflict detection (app + DB exclusion), availability override, status workflow (confirm, check-in, room, check-out, cancel w/ reason, no-show), front-desk board with wait timers, arrival notifications to providers, reminder task.
- **EHR:** encounters (from appointment or unscheduled), vitals (imperial entry, trends chart, abnormal flags), problems/medications/allergies/history with entered-in-error, ICD-10 picker, encounter diagnoses (+ add to problem list), templates, SOAP notes with explicit versioned saves, optimistic concurrency, ⌘S, unsaved-change guard, sign (A/P required, AI attestation), DB-frozen signed notes, addenda, version history, encounter completion rules, patient timeline, "My visits".
- **Document AI (phase 5):** `documents` + `ai_jobs` tables (migration 0003); upload with magic-byte validation, size limit, SHA-256 duplicate detection, object-storage keys free of PHI; Celery pipeline (PDF text layer → AI analysis → rule-based patient matching with confidence + reasons); review queue with status tabs/counts; side-by-side review (preview, AI draft with uncertainties and abnormal flags, editable type/title/date/summary, candidate list, patient search, identity comparison table, mandatory identity attestation); file-to-chart (documents:review only), reject with reason, reprocess; chart Documents tab (uploads from chart still go through review); filed documents on timeline; authenticated inbound fax webhook; synthetic sample/fax generator (exact / ambiguous / unknown identity). AI provider abstraction: `simulated` rule-based default (no network, labeled), `anthropic` provider (Claude Opus 5.5, structured JSON output, server-side refusal fallbacks) hard-blocked for PHI unless `AI_PHI_ALLOWED=true`.
- **AI scribe (phase 6):** `scribe_sessions` (migration 0004) with recorded consent (verbal/written) before any capture; in-browser recording (start/pause/resume/stop, timer, live level, mic-permission errors) → upload (audio magic-byte check) → transcription adapter (none configured → honest failure, never invented text; audio deleted after transcription by default); typed/pasted transcript with speaker labels; synthetic demo conversation (synthetic orgs only, labeled); async drafting via Celery (simulated rule-based or Claude, PHI-gated); transcript editing + redraft; editable draft with uncertainties, allergy-discrepancy alert vs chart, mentioned meds/follow-up; insert into note as an `ai_scribe` version (append/replace, optimistic concurrency, blocked while the editor has unsaved edits) → signing requires AI attestation; every run logged in `ai_jobs`.
- **Clinical orders (phase 7):** `orders` + `lab_results` (migration 0005); catalogs behind a search adapter (medications with drug classes, LOINC-style lab panels with reference ranges, CPT imaging, synthetic specialist directory); per-type validated details; nurses draft, clinicians sign (DB constraint: non-draft orders require a signer); basic safety checks (drug–allergy class cross-reactivity, duplicate drug/class vs active med list) that require an override reason; signing transmits through a labeled simulated channel and adds prescriptions to the med list; simulated lab/imaging results (synthetic orgs) with H/L/critical flags and result notifications; review & release-to-patient (portal sees released results only); referral tracking (sent → scheduled → completed); cancel with reason; Orders worklist (to sign / results to review / awaiting results / referrals), encounter orders card, chart Orders and Results tabs with trends.
- **Portal (minimal):** patient login sees own appointments, allergies, medications, latest vitals.

## Test results (2026-11-19)

| Check | Result |
|---|---|
| `ruff check app tests` | ✅ pass |
| Backend import/startup | ✅ |
| Migrations up → down → up, `alembic check` | ✅ no drift |
| `pytest` (35 tests, incl. order role separation, allergy override, simulated transmission, med list update, result review/release & portal visibility, isolation; incl. scribe consent/role gates, honest STT failure, demo→draft→apply provenance, version/sign protection; incl. document upload validation, never-auto-file, matching, review permission, identity attestation, isolation, PHI gate, fax webhook auth; earlier: auth, MFA, lockout, sessions, authz, tenant isolation, restricted charts, portal scoping, audit immutability, duplicates, appointment conflicts, full visit + note integrity) | ✅ 35 passed |
| Frontend `tsc --noEmit` (TS 7) | ✅ 0 errors |
| Frontend `vite build` | ✅ (bundle 1.37 MB / 405 kB gz — warning) |
| API smoke across all screens × 7 roles | ✅ 0 server errors (found & fixed INET serialization bug) |
| Browser E2E (headless Chrome via Playwright): register → … → check-out | ✅ no page errors (found & fixed override-button and UTC-message bugs) |
| Browser E2E: simulated fax → review → identity attestation → file → chart; unknown patient blocked | ✅ no page errors (found & fixed: Compose API port collided with local dev API) |
| Browser E2E (fake mic device): scribe record → honest STT failure → demo → draft → allergy discrepancy → insert → attested sign → complete | ✅ (found & fixed: missing allergy-discrepancy warning, overflowing follow-up badge) |
| Browser E2E orders: Rx with allergy warning → override sign → med list; lab → simulated result → review & release → Results tab | ✅ (found & fixed: toasts covering drawer actions) |
| `docker compose up --build` | ✅ all services healthy; Celery task round-trip verified |

Browser E2E and API smoke scripts live in `e2e/` (manual; not yet in CI).

## Known issues / limitations

- Frontend bundle not code-split yet (single ~405 kB gz chunk).
- Order catalogs are small built-in subsets; safety checks are basic (allergy class, duplicates) — no drug–drug interaction database.
- ICD-10 search covers a ~120-code common subset.
- Reminder delivery and eligibility are simulated.
- No RLS yet; isolation relies on application layer + tests.
- Portal is read-only and minimal until phase 8.
- Port 8000 is used by another local service on the dev machine; local API uses 8010, Docker API 8011.
- Scanned images have no OCR with the simulated provider (no tesseract installed); they're flagged unreadable with low confidence. The Anthropic provider reads images/PDFs directly but is PHI-gated.
- No speech-to-text vendor is integrated; recorded audio can't be transcribed until one is configured (typed transcripts and the synthetic demo work).
- The Anthropic provider path is unit-tested only for the PHI gate; it has not been exercised against the live API (no key configured, and it must not receive PHI without a BAA).

## Next steps

1. Phase 8 — Patient portal (appointments, booking requests, intake, secure messages, released results, visit summaries, documents) and telehealth visit room.
2. Route-level code splitting; run `e2e/` in CI.
