# Implementation progress

_Last updated: 2026-11-19 (handoff checkpoint)_

# Undeclared HMS expansion — Milestones A, B, C

All work is local on branch `dev` (never pushed). Synthetic data only. Not HIPAA-certified or clinically validated.

## Milestone A — Intelligent EHR ✅ complete (2026-11-19)

| Package | Status | Commit |
|---|---|---|
| A1.1 `/api/v1` (legacy `/api` alias), OpenAPI → TS types (`npm run gen:api`), CI drift check | ✅ | dd4d193 |
| A1.2–A1.5 Facility → department → unit/room/bed hierarchy, 7 new roles + department scope, PostgreSQL RLS (`undeclared_app` role), SSE live updates over LISTEN/NOTIFY | ✅ | a13e86c |
| A2 Durable automation engine: outbox + idempotent dispatcher, cases (dedupe, SLA, escalation, snooze w/ reason), monitors (auto-verify/close), notification deliveries (dedupe, caps, prefs), approval gate, operations API, Celery queues/beat, in-process dev scheduler | ✅ | 8366e46 |
| A3 Insurance Guardian backend: eligibility history (simulated 270/271), coverage state per date of service, visit-readiness + renewal monitors, portal card upload → AI draft → staff confirm → re-verify, visit overrides, dashboard | ✅ | b657cd4 |
| A3 UI: My work, case drawer, Monitors & rules, Insurance Guardian (dashboard, cases, card review, patient lookup), portal Insurance page, chart coverage panel, Facilities admin, nav restructure; E2E `e2e/insurance_guardian_flow.py` | ✅ | (this commit) |
| A4 OpenAI provider: Responses API, strict structured outputs, bounded server-side tool loop, transcription, retries/timeouts, cost (`AI_PRICES`), PHI gate + synthetic-org policy, labeled fallback, status/health (no secrets). **Live validation pending (no key)**; contract tests with fake client | ✅ | e50f1fd |
| A5 Document AI vision / scribe transcription + drafting / chart assistant routed through OpenAI when configured; AI workspace page; AI activity with cost | ✅ | (milestone commit) |
| A6 Early Command Center: 8 DB-derived tiles with sources, problem queue (search/severity/department/SLA filters), category×severity matrix, department worklists, automation health, live (SSE) + wall display | ✅ | (milestone commit) |
| A4b AI Settings (Super Admin): write-only OpenAI key (Fernet-encrypted at rest, masked hint only, never logged/returned), provider switch, text/vision/transcription/realtime models, per-agent models, Test connection (authenticates + checks every configured model id via `models.list()`), remove key; UI settings override env. Suggested ids (gpt-4.1-mini, gpt-4o-mini-transcribe, gpt-4o-mini-realtime-preview) are **unverified suggestions** until tested with a real key | ✅ | (A4b commit) |
| A-demo: `tests/test_milestone_a_journey.py` (registration → inactive coverage detected → fixed → payer re-verified → case auto-closed → check-in → AI scribe → attested sign → completion → follow-up task → claim) + Insurance Guardian & Command Center browser flows | ✅ | (milestone commit) |

## Milestone B — Unified Hospital ✅ complete (2026-11-19)

| Package | Status | Commit |
|---|---|---|
| B1/B2 Inpatient stays + ADT (admit/transfer/discharge order/discharge/cancel), DB exclusion constraint against double bed occupancy, one active stay per patient, bed state machine + history, housekeeping tasks, bed board (live), census, bed-flow monitors (turnover delay, admission waiting, discharge not departed) | ✅ | 0fd926c, 71786f8 |
| B4 Nursing: inpatient encounter per stay (notes reuse: progress/nursing/discharge_summary), vitals, SBAR handoffs (append-only after acknowledgment), care team, nursing workspace | ✅ | 9c61195, 71786f8 |
| B5 Discharge coordination: checklist w/ owner task fan-out on discharge order, data-verified items (signed summary, booked follow-up, approved instructions), attested manual items, instructions draft → clinician approval (approval gate), readiness gate (physician-only audited override) | ✅ | 9c61195, 71786f8 |
| B3 Emergency department — **backend complete & tested; UI pending**: quick registration incl. temporary identities, nurse/physician-recorded ESI triage (no AI triage), bay rooming (DB-unique bay + one active visit per patient), provider assignment + ED encounter, physician-only dispositions, admit → boarding → auto-release on inpatient placement, identity reconciliation (merge moves records; append-only tables/signed notes accept *only* a patient_id change under `app.patient_merge`; audit log never rewritten), ED boarding + door-to-provider monitors, ED seed census; bed board shows ED occupants; **ED tracking board UI** (arrival incl. unidentified, triage, room, assign, disposition, identify/merge) + `e2e/ed_flow.py` | ✅ | 6679c53, 3501149, (B3 UI commit) |
| B6 Pharmacy & inventory + Pharmacy Watchdog: items/lots/locations, append-only ledger (DB: no negative stock), receive/transfer/dispense (expired lots blocked; pharmacist-only meds), two-person approval for waste/negative adjustments, suppliers, purchase requests (approver ≠ requester; simulated supplier PO; receive closes request), pharmacist verification queue for inpatient medication orders, reports; Watchdog monitors (expiring/expired, low stock + deterministic reorder recommendation + auto purchase request, unusual consumption); UI (inventory, item drawer w/ ledger, Watchdog, purchasing, verification); `e2e/pharmacy_flow.py` | ✅ | 4711cb0 + (B6 UI commit) |
| B9 Procurement & equipment: suppliers, purchase requests (approval ≠ requester, simulated PO, receiving) from B6; **department stock allocation** via location par levels + below-par monitor (restock by transfer); **equipment registry** with append-only maintenance log, failed service → out of service, maintenance due/overdue monitor; Equipment UI. Multi-line POs deferred (single-item requests cover the demo) | ✅ | (B9 commit) |
| B7 Laboratory: collection list (patient location), accession numbers, receive/reject (auto recollect task), results entry prefilled from the test catalog (preliminary), **independent verification** (verifier ≠ enterer), corrections keep superseded history + force clinician re-review, critical-result call-back (case assigned to ordering clinician, read-back acknowledgment, SLA escalation), turnaround monitors; patients see only verified results and release is blocked while any result is preliminary; UI + `e2e/lab_flow.py`. Analyzer interfaces not connected (manual entry, labeled) | ✅ | 3d12977 + (B7 UI commit) |
| B8 Radiology: worklist from signed imaging orders, accession + modality, technologist status sequence, radiologist-only report draft/sign, **DB-frozen signed reports** + addenda, critical-finding acknowledgment (case to ordering clinician), unread-study monitor, PACS/DICOMweb adapter interface (simulated: synthetic Study UID, no viewer/pixels); UI + `e2e/radiology_flow.py` | ✅ | 76ef6b2 + (B8 UI commit) |
| B10 Revenue & insurance expansion: prior authorizations (required-service rules per org, auto-drafted from signed orders with a document checklist, simulated payer decision, validity window), PA-needed/PA-expiring/claims-on-hold monitors, claim review findings (rules + optional AI consistency check; **advisory only**; blockers gate submission until a person resolves them), scrubber now uses payer-verified eligibility (not stored end dates) and checks PA, facility room & board charges at discharge, coding worklist, denial analytics; Revenue integrity UI | ✅ | c6cffc7 + (B10 UI commit) |
| B11 OR + rostering — backend + UI (`/or` timeline board in facility timezone incl. turnover, schedule dialog, status; `/roster` 3-day view, coverage gaps → explained candidates → assign, swap offer/accept/approve): OR schedule with DB-enforced room (incl. turnover) and surgeon conflict prevention, case status, utilization; shifts (DB: no overlaps), rest/weekly-hours/time-off/credential rules with audited override, explainable fill suggestions, swaps (request → accept → manager approval), staffing coverage-gap monitor | ✅ | 239ef4d + (B11 UI commit) |
| B12 Patient portal expansion: “Before your visit” readiness (payer-verified insurance, questionnaire, device check), hospital stays with **clinician-approved** discharge instructions + follow-up only, outside-records upload → nurse review task (never auto-filed), notification preferences per topic/channel enforced by the delivery service | ✅ | (B12 commit) |
B1 inpatient/ADT → B2 bed board → B3 ED → B4 nursing → B5 discharge agent → B6 pharmacy + Watchdog → B7 lab → B8 radiology → B9 procurement → B10 prior auth/claims → B11 OR + rostering → B12 portal.
Foundations already in place: locations with `bed_status`, hospital seed (Harborview General: ED 12 bays, 4B/4C/ICU beds, 4 ORs, pharmacy storage), department-scoped staff, engine + monitors.

## Milestone C — Intelligent Operations (core packages C1–C8 + 13-step demo complete; open items listed below)

| Package | Status | Commit |
|---|---|---|
| C1 Complete Command Center: hospital tiles (inpatients, available beds/occupancy, ED waiting/boarding, awaiting bed, discharges ordered, pharmacy/supply, lab/imaging, staffing gaps, OR today, claims held/blockers/prior auths, equipment, AI activity) each with source + drill-down; occupancy by department; department + facility + severity filters; shift handoff (deterministic, every line cites a case; optional AI narrative keeps only cited sentences); live + wall display | ✅ | (C1 commit) |
| C2 Agent Studio: 10 agents (Insurance Guardian, Doctor Assistant*, Medical Scribe*, Document Intelligence*, Pharmacy Watchdog, Discharge Coordination, Hospital Operations, Claims Review, Patient Communication, Staff Scheduling; *run inside their feature screens) with purpose, instructions, allowed tools, model, tool/time/cost limits, per-facility enable, versioned config; backend tool registry (allow-list + invoking user's permission + Pydantic args per call); propose_* tools → approval requests only; run log (tools, tokens, cost, status); rule-based labeled fallback; UI with run dialog, tool trace, feedback | ✅ | 8305013 + (C2 UI commit) |
| C7 AI governance (part): usage/cost/latency by feature and agent, failed/limited runs with retry, feedback, PHI-sent counter, provider/model settings (A4b) | ✅ | same |
| C3 cross-department automations: monitors `journey.follow_up_not_booked` (completed visit with follow-up advised, nothing booked) and `journey.intake_missing` (upcoming visit, no pre-visit intake), added to the existing insurance/ED/ADT/discharge/pharmacy/lab/radiology/revenue/staffing/equipment monitors | ✅ | 103b05f |
| C4 forecasting foundation: `GET /forecasts` — seasonal (same-weekday mean ±1.5 SD) baselines for census, admissions, discharges, ED arrivals; nurses needed (med-surg ratio); no-show rate × tomorrow's bookings. Stored in `predictions` (migration 0025) for backtesting (actuals backfilled, MAE + range coverage). **Labeled "Baseline model — not validated", shadow mode only**; days before the data starts are ignored | ✅ | 103b05f + (C4–C6 UI commit) |
| C5 unified patient journey: `GET /patients/{id}/journey` (appointments, visits, orders, verified results, signed imaging, ED, ADT, eligibility, claims, cases), each source included only if the caller holds its permission; audited; chart → **Journey** tab | ✅ | same |
| C6 admin reports: `GET /reports/briefing` (numbered metrics M1… each with its source, high/critical cases C####, top discharge blocker; optional AI narrative kept only if every sentence cites valid refs), `GET /reports/discharge-bottlenecks`; **Insights** page (`/insights`) | ✅ | same |
| C7 AI evaluations: `ai_eval_runs` (migration 0026); suites `document_extraction_v1` (8 synthetic labeled documents incl. no-identifier and scanned cases; per-field accuracy, invented-value count) and `tool_gate_v1` (allow-list, unknown tool, malformed/extra arguments, missing permission must all be refused); `GET/POST /ai/evaluations`; Evaluations card in AI governance with per-sample drill-down. Found + fixed: tool arguments with unknown fields were silently ignored → now rejected. Known simulated-extractor misses (recorded, not hidden): discharge summary date picks admission date; insurance card effective date read as document date; correspondence typed "other" (score 93%) | ✅ | (C7 commit) |
| C8 performance & reliability: SQL-statement budgets + 2 s time guard for hot endpoints (cases, command summary, ADT/ED boards, forecasts, briefing, governance, patients) and a flat-query check for the patient journey (`test_performance`); composite indexes for time-window queries (migration 0027: ai_jobs, ed_visits, inpatient_stays admitted/discharged); census history now one query (verified identical to the per-day version on dev data); journey N+1 removed; forecast storage check batched. Reliability: dead-letter test (handler fails MAX_ATTEMPTS → `dead`, visible in `/engine/health`, replay restricted to automation managers, effect applied exactly once). Measured on dev stack: all hot endpoints < 25 ms median at demo scale (not a load test) | ✅ | (C8 commit) |
| Final 13-step synthetic hospital demo: `backend/tests/test_milestone_c_demo.py` drives one synthetic patient through the real API — ED arrival → triage/rooming/provider → admission request → bed assignment → Command Center tiles change (inpatients, awaiting bed, discharges) → medication shortage → Watchdog case routed to pharmacist + purchase request (requester can't approve; hospital admin approves) → discharge order → missing items with owner tasks (premature discharge refused) → pharmacist/nurse/physician/front desk complete items (signed discharge summary, clinician-approved instructions, booked follow-up) → discharge → facility charges in coding queue + patient journey → Hospital Operations Agent run with tool trace + sourced briefing → audit trail contains every step and approval. **Passes.** Bugs found and fixed by it: ED rooming wasn't audited (now `ed.roomed`); inpatient admission/transfer accepted **ED bays** as inpatient beds (now refused; bed-board dialogs offer inpatient units only); "Available beds" totals counted ED bays (now inpatient beds only, `ed_totals` separate; Command Center matches); "Complete discharge" clickable before readiness loaded (opened the non-override dialog) | ✅ | (demo commit) |

### Milestone C — still open (not claimed complete)
- **Realtime Voice — implemented, live validation pending.** `POST /ai/realtime/session` (ai:use + schedule:write) mints a short-lived client secret server-side via `POST https://api.openai.com/v1/realtime/client_secrets` (model + voice + guard-railed receptionist instructions set server-side; pseudonymous `OpenAI-Safety-Identifier`; PHI policy enforced; logged as an AI job + audited); `GET /ai/realtime/status`. Browser panel on AI receptionist (`RealtimeVoice.tsx`) does WebRTC to `/v1/realtime/calls` with only the ephemeral value (data channel `oai-events`, transcripts shown). Without key/model it shows simulated mode and the button is disabled (browser-checked). CSP `connect-src` now allows `https://api.openai.com` (nginx `security-headers.conf`). Tests: `test_realtime.py` (mock transport — no OpenAI calls). **Not verified against OpenAI** (no key). Model ids: OpenAI's WebRTC guide currently names `gpt-realtime-2.1` and lists no "mini" realtime id; the AI settings suggestion `gpt-4o-mini-realtime-preview` is unverified — confirm with Test connection before use.
- **Final role-based UI/UX refinement pass** across the 11 roles (layout/accessibility audit, dark mode review, empty states) — not done as a dedicated pass.
- **OpenAI live validation:** pending — no key configured; every AI path above ran on the simulated/rule-based provider (labeled in the UI).

## GitHub + AWS EC2 deployment (2026-11-20) ✅ (staging/demo, synthetic data)
- **GitHub:** https://github.com/bobbydhir2003/Unified_HWS (public). Branches `dev` (working) and `main` (release; default branch).
  - Before publishing, I scanned the full history (50 commits) for private keys, AWS/OpenAI/GitHub/Slack tokens and secret
    files. Only synthetic test placeholders were found.
  - `.env` files, `.pem` keys, dumps and runtime storage are excluded.
  - The seeded demo password and webhook secrets are now per-deployment (`SEED_DEMO_PASSWORD`); the repository default is
    refused in staging/production.
- **Live site:** **https://3-19-143-26.sslip.io**
  - Instance `i-0a190b3478787307c` (us-east-2, t3.small, Ubuntu 26.04). SSH host key verified by the owner.
  - Caddy obtains the Let's Encrypt certificate and redirects HTTP → HTTPS.
  - Stack: nginx web, FastAPI (1 process), Celery worker + beat (concurrency 1, all queues), PostgreSQL 16, Redis.
    Images are built off-host for amd64. `ENVIRONMENT=staging`; the production guard would refuse to boot without S3 and MFA.
  - Only ports 80, 443 and 22 are public; 5432, 6379, 8000 and 8080 were verified unreachable.
  - Fresh random secrets in `/opt/undeclared/.env` (mode 600). The encryption key for stored AI keys persists there.
  - Nightly backup at 03:15 UTC, 7-day retention. A restore drill passed.
- **Verified:** `e2e/deploy_smoke.py` 26/26 against the public URL; browser check of login (no demo box), Command Center
  live updates, Super Admin AI settings, and the voice panel in a secure context; full restart keeps data. Details are in
  `docs/AWS_DEPLOYMENT.md`.
- **Pending or limited:**
  - OpenAI key not entered, so AI runs in labeled simulation. Live text and Realtime Voice remain unvalidated.
  - Disk is 6.7 GB (76% used): grow the EBS volume to 20 GB.
  - No Elastic IP: a stop/start changes the IP and therefore the sslip.io hostname.
  - MFA is not enforced on the demo.
- **Quick role login:** environment-configurable.
  - Dev server: all 7 roles.
  - Opt-in `VITE_DEMO_LOGIN` builds: no admin roles.
  - Default production build, including EC2: compiled out.
- **CI (first run on GitHub):** two tests that depended on the local environment were fixed:
  - the production-guard test now passes explicit unsafe values;
  - bed-selection tests use any free inpatient bed instead of unit 4C.

## Help & About (in-app user guide, 2026-11-19) ✅
- Route **`/help`** (staff, every role; sidebar → Support → *Help & About*, and user menu → *Help & About*). Patients: **`/portal/help`** (portal nav → *Help & About*). `/about` remains the public legal-notices page (user menu → *Legal notices*).
- Sections: Overview (plain-language description + 9-stage patient journey linking to each topic), Getting started (8 steps with links the user can open), Features (19 module articles: what / who / when / steps / example / simulated note / links — step-by-step only for areas the role can use; other areas show a short non-sensitive summary marked "not part of your role"), Role guides (Doctor, Nurse, Receptionist, Billing & insurance, Pharmacist, Laboratory, Radiology, Bed manager, Hospital administrator, Super Admin — users see their own; administrators can browse all), AI & automation (10 plain-English topics, "AI assists hospital staff. It does not replace professional clinical judgment."), FAQ (12 staff / 8 patient, accordion), About (version from package metadata, modules, plain architecture, privacy/limitations, demo status, copyright from `lib/legal.ts`).
- Client-side search across all visible content (results jump to and open the topic). Native `<details>` accordions (keyboard + screen-reader friendly), focus rings, dark mode, mobile (no horizontal scroll, verified at 390 px).
- Content is typed data in `frontend/src/features/help/content.ts`; every button label/route was taken from the current screens. No backend changes, no new dependencies.
- Verified: typecheck, lint, build (copyright banner still on all 93 chunks); `e2e/help_flow.py` — all 10 staff role accounts + patient open it, role guide and allowed/locked modules correct, search → topic → real screen link, About shows version + "© 2026 Sidra Riaz Awan. All rights reserved.", mobile layout.

## Copyright attribution (owner request, 2026-11-19)
- Notice **© 2026 Sidra Riaz Awan. All rights reserved.** shown in the staff app footer, patient portal footer, sign-in page, user menu → **About & legal** page (`/about`, public), and in OpenAPI metadata.
- Single source: `frontend/src/lib/legal.ts` (holder, year, notice, third-party + code-set notices) and `backend/app/core/legal.py`.
- Production builds: Vite plugin adds a `/*! … */` legal banner to every JS chunk and `<meta name="copyright">`/`<meta name="author">` (verified: all 87 chunks contain it).
- Metadata: `frontend/package.json` (`author`, `license: "UNLICENSED"` = proprietary, npm convention), `backend/pyproject.toml` (`authors`, proprietary classifier), root `COPYRIGHT` file, README section, headers in `backend/app/main.py`, `frontend/src/main.tsx`, `vite.config.ts`, legal modules.
- Third-party licenses/notices untouched. **Flags for the owner:** (1) no LICENSE existed before — `UNLICENSED`/All rights reserved is a proprietary stance, confirm it's intended; (2) git commits are authored by "Bobby Dhir" while copyright is attributed to Sidra Riaz Awan — if these are different people, document ownership/assignment in a written agreement; (3) much of the code was produced with AI assistance — protection for AI-generated material varies by jurisdiction; seek legal advice; (4) the abbreviated CPT® list is AMA-licensed content — production use needs an AMA license.

## Milestone B validation (2026-11-19, local dev stack, no reseed, Chrome)
- Backend `pytest`: **116 passed**; ruff clean; `alembic check` clean through 0023.
- Browser flows, all passing: insurance_guardian, clinical, documents, scribe, orders, portal_telehealth, billing, ai, analytics, command_center, adt, ed, pharmacy, lab, radiology (15) + api_smoke (no 4xx/5xx for any role).
- The five Milestone B workflows are covered end to end: ED → admission → bed → transfer → discharge (`test_ed`, `adt_flow`, `ed_flow`); expiring medication → Watchdog case → task → two-person approved waste → verified resolution (`test_pharmacy`, `pharmacy_flow`); lab order → collection → independent verification → clinician result (`test_lab`, `lab_flow`); discharge → missing items → department tasks → completed discharge (`test_discharge`); prior auth → staff review → simulated approval → billing (`test_revenue`).
- Fixed during validation: outpatient charge-capture queue now excludes inpatient/ED encounters (they're coded in Revenue › Coding queue); billing E2E selects a visit whose coverage isn't payer-inactive (those claims are now correctly held).

## Tests actually executed (2026-11-19)
- Backend (latest, 2026-11-19 end of session): **142 passed** (adds test_realtime ×4). Before realtime: **138 passed** (adds 13-step demo + ED-bay guard). ruff clean; `alembic check` clean through 0027. Browser: all flows pass on the dev DB except `insurance_guardian_flow`, which needs a **fresh seed** (it consumes the portal patient's one seeded inactive-coverage scenario; CI seeds fresh). `adt_flow` made re-runnable (creates its own pending admission/free beds via normal APIs). api_smoke clean. After C8: 136 (adds test_performance ×10, dead-letter test). After C7: 125 (adds evaluation suites test). After C4–C6: 124 (adds test_insights; `insights_flow` browser flow passes). After C2: 121 (adds test_agents). After C1: 117. After B9: 116. After B12: 114. After B11: 112. After B10: 109. After B8: 105. After B7: 104. After B6: 102. After A4b: 98. After B3: 97; after B5: 95. Earlier at Milestone A: **90 passed** (new: test_facilities_rls, test_engine, test_insurance_guardian, test_openai_provider, test_command_center, test_milestone_a_journey). `ruff` clean. `alembic check` clean through 0013.
- Frontend: `npm run typecheck` and `npm run build` pass.
- Browser (local dev, fresh seed, Chrome): api_smoke (no 4xx/5xx for any role) + all 8 original flows + `insurance_guardian_flow` + `command_center_flow` passed at Milestone A completion; `adt_flow` passed after B5 and again at the B3 checkpoint; api_smoke clean (no 4xx/5xx) at checkpoint.
- OpenAI: NOT validated against the live API (no key). Simulated provider used in every run above. To validate: Super Admin → AI settings → enter key → Test connection.

## Known issues / notes
- `PATCH /organization` replaces the whole `settings` JSON; an admin saving a stale copy could roll back counters (e.g. `mrn_seq`) → duplicate MRN conflicts. Fix planned: move counters to DB sequences or merge settings server-side.
- Local Postgres user `undeclared` isn't superuser: role `undeclared_app` was created once by the local admin (`CREATE ROLE undeclared_app NOLOGIN; GRANT undeclared_app TO undeclared`). Migration 0010 raises a clear error if missing. Docker/CI users are superusers (auto-created).
- Refresh cookie path widened from `/api/auth` to `/api` (so v1 and legacy paths both work).
- Eligibility, email/SMS are simulated (labeled). Card images need a vision AI provider; in simulated mode only text PDFs (synthetic sample card) are extracted.
- Monitors run org-wide each time an insurance event fires (fine at demo scale; scope per patient before large pilots).
- Header still says "clinic" switcher; facility switcher UI to be finished with Command Center.

## Next actions (exact resume point)
Latest commit: see `git log -1`. First unfinished package: **UI/UX refinement pass per role**.
1. ~~Realtime Voice~~ done (live validation pending a key).
2. **UI/UX refinement pass** per role (Super Admin, Hospital Admin, Doctor, Nurse, Receptionist, Billing, Pharmacist, Lab, Radiology, Bed Manager, Patient): check each landing page, nav, empty/loading states, keyboard focus, dark mode, mobile width; fix dead buttons.
3. Re-run full regression (`uv run pytest -q`, every `e2e/*_flow.py` + `api_smoke`), then commit "Milestone C complete" only if 1–2 are done.
4. OpenAI live validation when a key is provided (Super Admin → AI settings → Test connection), synthetic data only; then run AI governance → Evaluations against the live provider.

## Resume checklist
- New module demo data for an existing dev DB: `uv run python -m app.seed_extend` (additive, idempotent).
- **Do not run `app.seed --reset` against the dev DB** (owner instruction: no database resets). Browser flows must create their own uniquely named data. pytest resets only the `undeclared_test` DB.
- `cd backend && uv run alembic upgrade head && uv run python -m app.seed --reset` (dev DB), API `uv run uvicorn app.main:app --port 8010 --reload --reload-dir app`, web `cd frontend && API_PROXY_TARGET=http://localhost:8010 npm run dev`.
- Local Postgres needs role `undeclared_app` (already created on this machine; see Known issues).
- Tests: `cd backend && uv run pytest -q` (97 expected), `cd frontend && npm run typecheck && npm run build`.

---

# Original 12-phase build (complete)

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
| 8 Portal & telehealth | ✅ Complete |
| 9 Billing & RCM | ✅ Complete |
| 10 Advanced AI | ✅ Complete |
| 11 Analytics & population health | ✅ Complete |
| 12 Integrations & deployment | ✅ Complete (deployment config written, not applied) |

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
- **Integrations & deployment (phase 12):** FHIR R4 read API (CapabilityStatement; Patient read/search; patient-scoped Encounter, Condition, AllergyIntolerance, MedicationStatement, Observation for vitals with LOINC codes and labs with interpretation/reference ranges; Bundles; OperationOutcome errors; same auth/tenancy/restricted-chart rules; audited); typed adapter interfaces + registry for order transmission, clearinghouse and message gateway (call sites refactored; only simulated implementations registered); hardening — per-IP sliding-window rate limits on auth and webhooks, production configuration guard that refuses unsafe settings, Prometheus `/api/metrics` with route templates only, nginx CSP (hash-pinned inline script, no eval) + HSTS on every location (fixed nginx header-inheritance bug), verified zero CSP violations on the production build; route-level code splitting (main bundle 405 → 155 kB gz); `ops/backup.sh` / `ops/restore.sh` with a completed restore drill; AWS reference Terraform (VPC, KMS, RDS PITR, Redis TLS, S3 SSE-KMS, ECS Fargate, ALB TLS, Secrets Manager, CloudWatch, AWS Backup) — not validated or applied; CI adds Docker image build and full Playwright E2E jobs; DEPLOYMENT, OPERATIONS and PRODUCTION_READINESS docs.
- **Analytics & population health (phase 11):** all metrics computed from live SQL at request time — operations (volume by day/status, no-show/cancellation/kept rates, wait-to-room, visit length, visit types, booking channels incl. portal/AI phone, provider utilization vs scheduled hours, clinic scope), provider productivity (visits, patients, open encounters, unsigned notes, hours to sign, no-shows, AI scribe use), financial (charges, collections, collection/denial rates, days to payment, by payer, monthly), population (registries for diabetes, HTN, hyperlipidemia, asthma/COPD, depression/anxiety, hypothyroidism; age/sex; multimorbidity; no visit in 12 m), care gaps (A1c overdue, A1c >9%, BP ≥140/90, lipid overdue, no visit) with idempotent bulk outreach tasks, quality measures modeled on CMS122/CMS165 (labeled not certified), audited CSV exports (operational export carries no patient identifiers). Seed extended with synthetic lab and 6-month billing history.
- **Advanced AI (phase 10):** *Chart assistant* — permission-checked retrieval over numbered chart sources (profile, allergies, meds, problems, history, vitals, signed visits, labs, filed documents, imaging/referrals), lexical retrieval with clinical synonyms, every statement cited and linked to its chart location, prescribing/ordering/diagnosis requests refused before any model call, honest "not found", Claude path with structured output that drops invalid citations; audit stores no question text. *Automation studio* — 6 templates (no-show outreach, abnormal-result escalation, document routing, patient-message triage, positive PHQ-2 follow-up, follow-up scheduling) wired to real events; each declares allowed actions; patient-facing actions wait in an approval queue; savepoint-isolated execution; run log, retry, enable/disable; rule-based classifier for messages and document routing. *Tasks* worklist (mine/roles/all, priorities, sources). *AI receptionist* sandbox — disclosure + consent, emergency safeguard (911 + urgent task), name+DOB verification with 3 attempts and non-revealing failures, slot offering and booking (`booked_via=ai_phone`), cancellations, clinic info, clinical/billing handoff tasks, call logs with summaries, authenticated telephony webhook (`X-Voice-Secret`). *AI monitoring* — every AI job with provider/model/latency/tokens/PHI-external flag.
- **Billing & RCM (phase 9):** fee schedule, charges, claims, claim events, claim submissions, invoices, payments (migration 0007; integer cents with CHECK constraints incl. `amount = units × unit_price`); charge queue of completed visits; transparent E/M + venipuncture suggestions; charge editor with diagnosis pointers validated against the encounter; claim creation with scrubbing (NPI, member ID, coverage dates, dx pointers, address); submission with mandatory `Idempotency-Key` (unique constraint, race-safe replay) to a simulated clearinghouse; deterministic simulated adjudication (allowed/paid/contractual adjustment/patient responsibility, or CARC CO-27/CO-16/CO-50 denials); appeals with simulated decisions (overturned → paid; upheld → balance transferred to patient); void returns charges to the queue; self-pay statements; idempotent payments (staff cash/check/simulated card; portal simulated card — no card data ever collected); patient statement notifications; billing overview from live data (charges/collections MTD, A/R by payer type, aging buckets, denial rate, top denial codes, 6-month collections); chart Billing tab; portal Billing page.
- **Patient portal (phase 8):** separate portal app (home, appointments, messages, visit summaries, results, health record, account; billing marked "Soon"); patient-scoped `/portal/*` API that never takes a patient id; self-booking wizard over open slots (same availability/conflict engine, ≥2h notice, 90-day horizon, no override) and cancellation ≥24h; pre-visit intake (symptoms, med/allergy reconciliation, PHQ-2, questions) shown to staff in the encounter with positive-screen flag; after-visit summaries from signed notes (+addenda, prescriptions); released results only; result-release, reply and booking notifications.
- **Secure messaging:** threads + messages (migration 0006) with unread counters per side, PCP routing and notifications; staff inbox (open/closed, my patients, compose to patient, resolve).
- **Telehealth:** sessions + signaling tables; join authorized for the appointment's patient (−30 min…+1 h window) or clinic-scoped clinical staff; joining checks the patient in and notifies the clinician; browser WebRTC with negotiation-id correlated offer/answer/ICE relayed through the API (media peer-to-peer, never via server); camera/mic toggles, audio-only and no-device fallbacks, connection state, end-for-everyone; clinician side panel to start/open visit notes; "Join video" from schedule/front desk.

## Test results (2026-11-19)

| Check | Result |
|---|---|
| `ruff check app tests` | ✅ pass |
| Backend import/startup | ✅ |
| Migrations up → down → up, `alembic check` | ✅ no drift |
| `pytest` (67 tests, incl. FHIR shape/bundles/OperationOutcome/scoping/isolation, rate limiting, production guard, PHI-free metrics, adapter status; incl. analytics access control, internal consistency, deterministic care-gap detection, idempotent outreach, quality sanity, CSV export/audit, tenant scoping; incl. assistant citations/refusal/not-found/roles/tenancy/PHI-free audit, message triage, approval-gated outreach, disabled workflows, document routing, receptionist consent/verification/booking/emergency/webhook, AI monitoring; incl. billing role gating, charge validation, scrubbed claim, idempotent submission & payment replay, overpayment rejection, denial→appeal→transfer, portal payment, DB charge-amount constraint, isolation; incl. portal/staff separation, self-booking conflicts/availability, 24h cancel rule, intake to staff, messaging privacy, telehealth join authorization + signal relay; incl. order role separation, allergy override, simulated transmission, med list update, result review/release & portal visibility, isolation; incl. scribe consent/role gates, honest STT failure, demo→draft→apply provenance, version/sign protection; incl. document upload validation, never-auto-file, matching, review permission, identity attestation, isolation, PHI gate, fax webhook auth; earlier: auth, MFA, lockout, sessions, authz, tenant isolation, restricted charts, portal scoping, audit immutability, duplicates, appointment conflicts, full visit + note integrity) | ✅ 67 passed |
| Frontend `tsc --noEmit` (TS 7) | ✅ 0 errors |
| Frontend `vite build` | ✅ code-split; main chunk 497 kB / 155 kB gz, no size warning |
| API smoke across all screens × 7 roles | ✅ 0 server errors (found & fixed INET serialization bug) |
| Browser E2E (headless Chrome via Playwright): register → … → check-out | ✅ no page errors (found & fixed override-button and UTC-message bugs) |
| Browser E2E: simulated fax → review → identity attestation → file → chart; unknown patient blocked | ✅ no page errors (found & fixed: Compose API port collided with local dev API) |
| Browser E2E (fake mic device): scribe record → honest STT failure → demo → draft → allergy discrepancy → insert → attested sign → complete | ✅ (found & fixed: missing allergy-discrepancy warning, overflowing follow-up badge) |
| Browser E2E orders: Rx with allergy warning → override sign → med list; lab → simulated result → review & release → Results tab | ✅ (found & fixed: toasts covering drawer actions) |
| Two-browser E2E (fake camera/mic): portal join → clinician join → WebRTC connected with decoded remote video both ways → mute → end for everyone; message round-trip; booking wizard; intake | ✅ (found & fixed: offer/answer mismatch from duplicate hellos → negotiation-id correlation, per-signal error isolation) |
| Browser E2E billing: capture → claim → submit → simulated payer → appeal → patient payment → overview | ✅ (found & fixed: denial report GROUP BY bug, transferred patient responsibility not reflected on claim) |
| Browser E2E AI: assistant cited summary + refusal; urgent portal message → URGENT task; receptionist verified booking; automation studio & monitoring | ✅ (found & fixed: summary intent regex, mid-word truncation, page-level scroll in simulator) |
| Browser E2E analytics: all tabs, care-gap outreach, CSV download | ✅ (found & fixed: quality numerator double-counting) |
| Production build in Docker behind nginx: CSP/HSTS headers on all paths; browser pass over login, chart, AI drawer, blob PDF preview, dashboard | ✅ 0 CSP violations |
| Backup → restore drill into a fresh DB | ✅ identical row counts, triggers intact, overwrite guard works |
| `docker compose up --build` | ✅ all services healthy; Celery task round-trip verified |

Browser E2E and API smoke scripts live in `e2e/` (manual; not yet in CI).

## Known issues / limitations

- Order catalogs are small built-in subsets; safety checks are basic (allergy class, duplicates) — no drug–drug interaction database.
- Quality measures use simplified logic (not certified eCQMs); care-gap logic depends on coded problems and structured lab names.
- E/M level suggestions are a transparent heuristic, not a coding engine; CPT descriptions are abbreviated (AMA license needed).
- ICD-10 search covers a ~120-code common subset.
- Reminder delivery and eligibility are simulated.
- No PostgreSQL RLS yet; isolation relies on the application layer + regression tests.
- AWS Terraform has not been validated (`terraform` unavailable here) or applied; CI E2E/Docker jobs have not run on GitHub yet (nothing pushed).
- Port 8000 is used by another local service on the dev machine; local API uses 8010, Docker API 8011.
- Scanned images have no OCR with the simulated provider (no tesseract installed); they're flagged unreadable with low confidence. The Anthropic provider reads images/PDFs directly but is PHI-gated.
- Message/document classification and the receptionist's language understanding are rule-based in the default (simulated) configuration; the chart assistant's retrieval is lexical (no embeddings).
- Telehealth uses STUN-only peer-to-peer WebRTC (works on local/simple networks); restrictive NATs need TURN from a video vendor. Signaling uses ~1 s polling rather than WebSockets.
- No speech-to-text vendor is integrated; recorded audio can't be transcribed until one is configured (typed transcripts and the synthetic demo work).
- The Anthropic provider path is unit-tested only for the PHI gate; it has not been exercised against the live API (no key configured, and it must not receive PHI without a BAA).

## Next steps

All twelve planned phases are implemented. Highest-value follow-ups (see `PRODUCTION_READINESS.md` for the full list):

1. Compliance groundwork and BAAs; choose certified vendors and implement real adapters (eRx, labs, clearinghouse, payments, video, telephony/ASR, speech-to-text).
2. PostgreSQL row-level security, WAF rate limiting, SSO, session idle timeout.
3. Validate and apply the Terraform in a staging account; wire alerting; load test.
4. SMART on FHIR authorization and US Core conformance testing.
5. Push to GitHub to run the CI E2E/Docker jobs; add visual regression snapshots.
