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
| 8 Portal & telehealth | ✅ Complete |
| 9 Billing & RCM | ✅ Complete |
| 10 Advanced AI | ✅ Complete |
| 11 Analytics & population health | ✅ Complete |
| 12 Integrations & deployment | ⏭ Next |

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
| `pytest` (60 tests, incl. analytics access control, internal consistency, deterministic care-gap detection, idempotent outreach, quality sanity, CSV export/audit, tenant scoping; incl. assistant citations/refusal/not-found/roles/tenancy/PHI-free audit, message triage, approval-gated outreach, disabled workflows, document routing, receptionist consent/verification/booking/emergency/webhook, AI monitoring; incl. billing role gating, charge validation, scrubbed claim, idempotent submission & payment replay, overpayment rejection, denial→appeal→transfer, portal payment, DB charge-amount constraint, isolation; incl. portal/staff separation, self-booking conflicts/availability, 24h cancel rule, intake to staff, messaging privacy, telehealth join authorization + signal relay; incl. order role separation, allergy override, simulated transmission, med list update, result review/release & portal visibility, isolation; incl. scribe consent/role gates, honest STT failure, demo→draft→apply provenance, version/sign protection; incl. document upload validation, never-auto-file, matching, review permission, identity attestation, isolation, PHI gate, fax webhook auth; earlier: auth, MFA, lockout, sessions, authz, tenant isolation, restricted charts, portal scoping, audit immutability, duplicates, appointment conflicts, full visit + note integrity) | ✅ 60 passed |
| Frontend `tsc --noEmit` (TS 7) | ✅ 0 errors |
| Frontend `vite build` | ✅ (bundle 1.37 MB / 405 kB gz — warning) |
| API smoke across all screens × 7 roles | ✅ 0 server errors (found & fixed INET serialization bug) |
| Browser E2E (headless Chrome via Playwright): register → … → check-out | ✅ no page errors (found & fixed override-button and UTC-message bugs) |
| Browser E2E: simulated fax → review → identity attestation → file → chart; unknown patient blocked | ✅ no page errors (found & fixed: Compose API port collided with local dev API) |
| Browser E2E (fake mic device): scribe record → honest STT failure → demo → draft → allergy discrepancy → insert → attested sign → complete | ✅ (found & fixed: missing allergy-discrepancy warning, overflowing follow-up badge) |
| Browser E2E orders: Rx with allergy warning → override sign → med list; lab → simulated result → review & release → Results tab | ✅ (found & fixed: toasts covering drawer actions) |
| Two-browser E2E (fake camera/mic): portal join → clinician join → WebRTC connected with decoded remote video both ways → mute → end for everyone; message round-trip; booking wizard; intake | ✅ (found & fixed: offer/answer mismatch from duplicate hellos → negotiation-id correlation, per-signal error isolation) |
| Browser E2E billing: capture → claim → submit → simulated payer → appeal → patient payment → overview | ✅ (found & fixed: denial report GROUP BY bug, transferred patient responsibility not reflected on claim) |
| Browser E2E AI: assistant cited summary + refusal; urgent portal message → URGENT task; receptionist verified booking; automation studio & monitoring | ✅ (found & fixed: summary intent regex, mid-word truncation, page-level scroll in simulator) |
| Browser E2E analytics: all tabs, care-gap outreach, CSV download | ✅ (found & fixed: quality numerator double-counting) |
| `docker compose up --build` | ✅ all services healthy; Celery task round-trip verified |

Browser E2E and API smoke scripts live in `e2e/` (manual; not yet in CI).

## Known issues / limitations

- Frontend bundle not code-split yet (single ~405 kB gz chunk).
- Order catalogs are small built-in subsets; safety checks are basic (allergy class, duplicates) — no drug–drug interaction database.
- Quality measures use simplified logic (not certified eCQMs); care-gap logic depends on coded problems and structured lab names.
- E/M level suggestions are a transparent heuristic, not a coding engine; CPT descriptions are abbreviated (AMA license needed).
- ICD-10 search covers a ~120-code common subset.
- Reminder delivery and eligibility are simulated.
- No RLS yet; isolation relies on application layer + tests.
- Port 8000 is used by another local service on the dev machine; local API uses 8010, Docker API 8011.
- Scanned images have no OCR with the simulated provider (no tesseract installed); they're flagged unreadable with low confidence. The Anthropic provider reads images/PDFs directly but is PHI-gated.
- Message/document classification and the receptionist's language understanding are rule-based in the default (simulated) configuration; the chart assistant's retrieval is lexical (no embeddings).
- Telehealth uses STUN-only peer-to-peer WebRTC (works on local/simple networks); restrictive NATs need TURN from a video vendor. Signaling uses ~1 s polling rather than WebSockets.
- No speech-to-text vendor is integrated; recorded audio can't be transcribed until one is configured (typed transcripts and the synthetic demo work).
- The Anthropic provider path is unit-tested only for the PHI gate; it has not been exercised against the live API (no key configured, and it must not receive PHI without a BAA).

## Next steps

1. Phase 12 — FHIR R4 read API, adapter interfaces, route-level code splitting, security hardening (rate limiting, security headers, PostgreSQL RLS), AWS reference deployment, backup/restore runbook, production readiness checklist, E2E in CI.
2. Route-level code splitting; run `e2e/` in CI.
