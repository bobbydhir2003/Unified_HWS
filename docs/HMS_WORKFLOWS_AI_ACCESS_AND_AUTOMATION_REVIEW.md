# HMS Workflows — Super Admin Access, Persistent OpenAI, and Automation Review

**Status:** inspection and plan only. No code, accounts, keys, settings, data or deployments were changed.

**Inspected on 23 Nov 2026:**
- **Repository** at `dev` (58b6cb8).
- **Live AWS database:** read-only queries that never select passwords, hashes or keys.
- **Local development database:** read-only.

**Evidence labels:**
- **[code]** — taken from the source;
- **[AWS]** — read from the live database;
- **[local]** — read from the development database.

---

## 1. Executive summary

1. **You already own a permanent Super Admin. You just can't conveniently use it.**
   - `admin@undeclared.dev` exists on AWS [AWS]: `is_superadmin`, active, not locked, MFA off, last signed in 23 Nov.
   - Its password is the server's `SEED_DEMO_PASSWORD`, which you can read with your own SSH key. It is shared with every seeded staff account.
   - You can change the password today on the Account page, and it survives deployments: seeding is a no-op once the hospital exists [code].
   - What's missing:
     - you can't change the email (`PATCH /auth/me` allows only name, phone and preferences [code]);
     - password-reset mails go to a simulated outbox, not to you;
     - there is no out-of-band recovery.
   - **Fix:** a one-time, SSH-only bootstrap/recovery command, plus a re-authenticated "change my email" action. There is no public registration route.
2. **Your OpenAI key disappears because you entered it as the *demo* Super Admin.**
   - Demo sessions store AI settings in `demo_ai_settings`, one row per sign-in session. A row expires after at most 4 hours (`demo_ai_ttl_hours`) and is deleted with the session [code].
   - The real platform configuration (`ai_provider_settings`, encrypted with `CREDENTIALS_ENCRYPTION_KEY`, which **is** set on AWS) persists across logouts and deployments. It has **never been configured on AWS**: there is no row [AWS].
   - Demo sessions are deliberately blind to the platform key. A shared demo key exists only as an environment variable, `DEMO_OPENAI_API_KEY`, which is **not set** [AWS env names].
   - **Fix:** an owner-managed "Public demo AI" setting, stored encrypted in the existing table under a second scope (`scope="demo"`), with an on/off switch and budgets. Demo visitors use it server-side and never see it.
3. **The automation feels unhelpful because the deterministic engine does the real work while the AI agents are disconnected from it.**
   - **What already works end to end** [code]: 22 monitors open owned cases, and some go further.
     - **Insurance Guardian monitors:** run eligibility checks (simulated payer), create staff tasks, send scheduled patient reminders, collect a new insurance card through the portal, then re-verify and close.
     - **Low-stock monitor:** prepares a purchase request with a recommended quantity, notifies the approver, and closes when stock is restored.
   - **The 7 on-demand agents** start only when someone clicks. They read cases and can propose only two things (a task or a portal message). On AWS they have produced **zero approval requests** [AWS]. They summarise the work the rules already did.
   - **Three approval mechanisms exist and aren't unified:** engine approvals, purchase-request approval, and Automation Studio runs. On AWS:
     - 77 of 86 monitor cases are open or escalated;
     - 57 of 62 automation tasks are open;
     - Automation Studio has never run [AWS].
   - **Fix:** attach AI to the case lifecycle:
     - rules detect;
     - an AI step explains and chooses among *typed, safe* next actions;
     - a person approves;
     - an executor acts;
     - the monitor verifies.
   - Show this as one simple **case story** everywhere.
4. **Live AI is partly verified, with one concrete misconfiguration.**
   - **Successful live runs:** hospital operations ×3, discharge, claims and pharmacy agents ×1 each, chart assistant ×2 [AWS], document analysis ×2 [local].
   - **Insurance Guardian agent:** hit its 6-tool-call limit both times it ran live.
   - **Scribe transcription failed live** with `NotFoundError`, because the transcription model is set to `gpt-realtime-2.1-mini`, a realtime model [local].
   - **Realtime voice:** sessions are minted successfully [local], but the conversation itself has not been verified.

---

## 2. Permanent Super Admin account — findings

| Question | Finding |
|---|---|
| Does a real Super Admin exist? | **Yes.** `admin@undeclared.dev` is the only `is_superadmin` user on AWS; active, MFA off, last login 23 Nov [AWS]. The demo Super Admin is a *different* account (`superadmin.demo@harborview.dev`, `is_superadmin = false`) [AWS, `app/core/demo.py`]. |
| How was it created? | By `app/seed.py` (`user(db, "admin@undeclared.dev", …, superadmin=True)`), with the password from `SEED_DEMO_PASSWORD` (set on AWS) [code]. |
| Still valid? | Yes. 26 successful sign-ins; 24 failures, all on 20 Nov, during first-deployment checks; not locked now [AWS]. |
| How does admin authentication work? | `POST /auth/login` (rate-limited, lockout after 5 failures for 15 min) → optional TOTP MFA step → short-lived access token + refresh cookie. `is_superadmin` adds the `super_admin` role in every organization (`app/api/deps.py:158-162`, `services/identity.py`) [code]. |
| Change email / password? | **Password: yes** (`POST /auth/password/change`, Account page). **Email: no**, because `ProfileUpdate` has no email field [code]. |
| Reset, MFA, approval? | Password reset exists, but the email goes to the simulated outbox. TOTP MFA exists (setup / enable / disable). `enforce_mfa` defaults to **false**, so it isn't required for super admins. There is no account-approval workflow; staff join by invitation [code]. |
| Safe ownership without a DB reset? | **Yes.** The seed is idempotent (it skips when Harborview exists), so a changed password survives deployments and restarts [code]. |
| Dependencies to watch | `e2e/deploy_smoke.py` signs in as `admin@undeclared.dev` with `DEMO_PASSWORD`. After you change the admin password, the smoke test needs its own credential variable. Every seeded staff account shares `SEED_DEMO_PASSWORD`, so rotating that is a separate decision. |

### Recommendation (simplest and secure)

**Step 1 — now, no code:** take over the existing account.
1. Over SSH, read `SEED_DEMO_PASSWORD` from `/opt/undeclared/.env` yourself. Don't paste it anywhere.
2. Sign in at `/login` as `admin@undeclared.dev`.
3. Go to **Account & security** → change the password.
4. Enable MFA.

**Step 2 — small code change (Phase 1), so you can use your own email and recover without email delivery:**
- **`backend/app/cli.py` (new).** It is run only inside the API container over SSH, so there is no HTTP route. Commands:
  - `python -m app.cli create-superadmin --email you@…` prompts twice for the password with `getpass`, refuses if a user with that email exists, sets `is_superadmin`, and writes an audit event (`user.bootstrap`, actor = system).
  - `python -m app.cli reset-password --email …` provides recovery without email; it is audited and revokes that user's sessions.
  - `python -m app.cli list-superadmins` prints emails only.
- **Change own email:** `POST /auth/email/change` with `{current_password, new_email}`. It requires the current password, checks uniqueness, revokes other sessions and is audited. Add a small form to `AccountPage.tsx`.
- **Optionally set `ENFORCE_MFA=true`.** `mfa_required_roles` already includes `super_admin`. Do this only after your own MFA works.
- **Smoke test:** `e2e/deploy_smoke.py` reads `SMOKE_ADMIN_EMAIL` / `SMOKE_ADMIN_PASSWORD` (falling back to today's behaviour).
- **Database changes:** none.
- **Tests:** `tests/test_admin_cli.py` (create, duplicate refused, reset revokes sessions, audit written) and the email change (wrong password → 403, duplicate → 409, success → sessions revoked).
- **Complexity:** low.

---

## 3. Current OpenAI persistence architecture

```
Real Super Admin ── PUT /admin/ai-settings ──▶ ai_provider_settings (scope="platform")
                                                  key: Fernet(CREDENTIALS_ENCRYPTION_KEY), hint only ever returned
                                                  models: text / vision / transcription / realtime + per-agent models
Demo Super Admin ── PUT /admin/ai-settings ──▶ demo_ai_settings (PK = sign-in session id)
                                                  expires ≤ 4 h, deleted with the session, cleanup every 10 min
AI call ─▶ app/ai/config.effective():
             demo request?  → demo_scope.resolve(session): session row → DEMO_OPENAI_API_KEY (env) → simulated
             otherwise      → platform row (30 s cache) → environment fallback → simulated
```

**Persistence:**
- The platform key survives logout, restarts and deployments because the encryption key lives in the server `.env` [code, AWS env names].
- Demo keys are per session by design (`app/models/ai_settings.py:32`, `app/ai/demo_scope.py`).

**Limits for demo AI** (`app/core/config.py:66-75`, `demo_scope.guard`):

| Limit | Value |
|---|---|
| Requests per session | 40 per hour |
| Concurrent requests per session | 2 |
| Cost per session | $1 |
| Shared key, all sessions | 300 requests per hour |

**Weaknesses found** [code]:
- Counters are **in-process memory** (`_take`, `_cost` dicts). They reset on restart and aren't shared between the API and worker processes.
- The cost cap only works if `AI_PRICES` is configured. Today `cost_tracking` is false, so the $1 cap is not enforced.
- There is no daily or monthly budget, no owner kill switch for the public demo, and no realtime-minute cap.

**Provenance:**
- `agent_runs.mode` (`openai` | `rule_based`), `model`, tokens and cost.
- `ai_jobs.provider` / `model` / tokens / status for chart Q&A, documents, scribe, transcription and realtime sessions.
- `claim_findings.source` (`rule` | `ai`) plus the model.
- The Command Center handoff narrative includes `narrative_source = "ai_cited"`.
- The UI labels results *Live AI · model* or *Simulated*.

**Configuration problem found [local].** The transcription model is set to `gpt-realtime-2.1-mini`, and live transcription fails with `NotFoundError`. The settings UI accepts any model string per capability, and Test Connection didn't flag it.

---

## 4. Why the demo AI settings disappear

1. You configured the key while signed in as **Demo Super Admin**. That writes `demo_ai_settings` for *that sign-in session*. AWS currently holds 2 such rows, with an OpenAI key, still unexpired [AWS].
2. The row expires within 4 hours and is deleted when the session ends (FK cascade; cleanup job) [code].
3. A new demo sign-in is a new session, so it gets no row and falls back.
4. The fallback (`DEMO_OPENAI_API_KEY`) isn't set, and demo sessions never read the platform row. The result is "Simulated".
5. The real platform row that *would* persist was never created on AWS, because the real Super Admin hasn't configured it [AWS].

This is working as designed for visitor isolation. The missing piece is an **owner-controlled, persistent demo provider**.

---

## 5. Recommended owner-managed demo AI configuration

**Can the current architecture do it?** Yes, with small changes. No new services are needed.

**Model (your A–D, adapted to the code):**
- **A. Owner key.**
  - The real Super Admin saves the platform key once (this already works).
  - Optionally, a **separate demo key** from a dedicated OpenAI project with its own spending limit is safer. Choose "use platform key" or "use a separate demo key".
- **B. Persistent demo provider.**
  - Add a second row in the **existing** `ai_provider_settings` table with `scope = "demo"` (the `scope` column is already unique per value).
  - It holds: `enabled`, an encrypted key or `use_platform_key`, allowed models, and budgets.
  - `demo_scope._default()` reads this row (cached ~30 s) instead of only the environment variable. The environment variable stays as the last fallback.
- **C. Visitor settings.** Unchanged: per-session model/agent preferences, plus an optional visitor key that is private and expires.
  - **New rule:** visitors choose models only from the owner's allow-list.
  - The owner's key is never returned; the API returns `"source": "owner"` and no hint to demo users.
- **D. Controls.** See §6.

**Changes by layer.**

| Layer | Changes |
|---|---|
| FastAPI (`app/api/routers/ai_admin.py`) | `GET/PUT /admin/ai-settings/demo`, real Super Admin only (`is_superadmin`, never demo); `POST /admin/ai-settings/demo/disable` (emergency switch); `GET /admin/ai-usage?scope=demo` |
| FastAPI (`app/ai/demo_scope.py`) | `_default()` resolves the owner's demo row; `guard()` enforces model allow-list, per-session and global hourly limits, a daily USD budget and a realtime-minute cap |
| FastAPI (counters) | Counters move to **Redis** (already in the stack: Celery broker) so limits hold across processes and restarts |
| FastAPI (budget) | The budget is computed from `agent_runs` + `ai_jobs` cost/tokens; `AI_PRICES` must be set so cost is known, and when it isn't, a token budget is used instead |
| FastAPI (realtime) | `app/ai/realtime.py` checks the same switch and a per-session minute/session cap before minting |
| FastAPI (failure fallback) | `app/agents/runner.py`: when OpenAI errors or is unavailable, fall back to the rule plan and label the result *"Simulated (AI provider unavailable)"* instead of failing the run |
| Frontend | `AISettingsPage.tsx`: a "Public demo AI" card for the real Super Admin with enable switch, key source, allowed models, budgets, today's usage and spend, and **Disable now**. Demo users' AI settings show "AI provided by the platform owner · limits: …" and their optional own-key field |
| Database | Migration `0030`: `ai_provider_settings.policy JSONB` (enabled, allowed_models, budgets, use_platform_key). No new tables |
| Model validation | Test Connection validates **each capability** with the right endpoint (text / vision / transcription / realtime), and the model pickers suggest only compatible models. This prevents the transcription-model failure above |

**How demo users reach OpenAI without knowing the key:** every call is server-side. The key is decrypted only in the backend process (`OpenAICore`), and the browser gets results, or, for realtime voice, a short-lived client secret (already implemented).

**If OpenAI is unavailable:** agents fall back to rules (labelled), feature jobs fail with a clear message, and the provider health endpoint (`POST /ai/provider/health`) reports the status on the AI settings page.

---

## 6. Cost and security controls

| Control | Today | Proposed |
|---|---|---|
| Per-session requests | 40/h, in memory | 40/h, Redis |
| Global requests | 300/h, only for the env shared key | Owner-set (e.g. 300/h, 2,000/day), Redis |
| Spending | $1/session, **not enforced** without `AI_PRICES` | Daily and monthly USD budget computed from recorded runs; token budget when prices are unknown; hard stop + Command Center/AI settings banner |
| Concurrency | 2/session | Same + global cap (e.g. 6) |
| Realtime voice | Needs a key; no minute cap | On/off + max 5 min/session + daily minutes |
| Models | Any string | Owner allow-list for demo |
| Tools | Read tools + 2 proposal tools; proposals need approval | Same rule: demo users can't approve; approvals by real staff only |
| Data | `ai_phi_allowed=false` default; demo org is synthetic | Demo provider only for synthetic organizations (`settings.synthetic_data`) |
| Key exposure | Never returned, only a hint (platform) | The demo key never even shows a hint to demo users; keys are never logged |
| Kill switch | None | **Disable public demo AI** button + `DEMO_AI_DISABLED` env override |
| Monitoring | Agent Studio activity, `/ai/governance` | A demo usage card: requests, tokens, spend today/month, top agents |

Also set a hard monthly limit in the OpenAI dashboard on the demo project. This is a protection outside the app.

---

## 7. Audit of the existing agents

**Triggers:**
- *manual* = runs only when a person clicks Run or Ask AI (`POST /agents/{key}/run`).
- *feature* = runs inside its own workflow.

No agent is started by a monitor or a schedule [code: `run_agent` has a single caller, `app/api/routers/agents.py`].

| Agent | Purpose | Trigger | Reads (tools) | Can propose | After approval | Seen in normal workflow? | Live evidence | Status | Value today |
|---|---|---|---|---|---|---|---|---|---|
| Hospital Operations | Explain bottlenecks | manual (Command Center, Home) | operations summary, cases, volume, staffing gaps | task | task created | Result shown in the side panel only | 3 live ✓ [AWS], 1 [local] | **Functional** | Summary; no follow-up routing UI |
| Discharge Coordination | Coordinate discharges | manual (discharge checklist, Home) | discharge cases, discharge status | task | task created | Side panel | 1 live ✓ [AWS] | **Functional** | Summary of a checklist users can already see |
| Claims Review (agent) | Missing billing info | manual (Claims) | billing cases, claim findings | task | task created | Side panel | 1 live ✓ [AWS] | **Functional** | Summary |
| Pharmacy Watchdog (agent) | Explain inventory alerts | manual (Pharmacy) | pharmacy/inventory cases, item | task | task created | Side panel | 1 live ✓ [AWS] | **Functional** | Summary; the *monitor* already drafts the purchase request |
| Insurance Guardian (agent) | Resolve verification issues | manual (Insurance, Home) | insurance cases, coverage | task, patient message | task / portal message | Side panel | 2 live runs hit the **6-tool-call limit** [AWS] | **Partially functional** | The *monitor* does the real work |
| Patient Communication | Draft admin messages | manual (Agent Studio only) | coverage, cases | patient message | portal message thread | Agent Studio only | none | **Not verified** | Not placed in any workspace |
| Staff Scheduling | Explain staffing gaps | manual (Agent Studio only) | staffing gaps, cases | task | task | Agent Studio only | none | **Not verified** | Not placed in the roster screen |
| Doctor Assistant (chart Q&A) | Cited chart answers | feature (chart "Ask AI") | chart (own pipeline) | — | — | Yes, in the chart | 2 live ✓ [AWS] | **Functional** | Useful: in context, cited |
| Medical Scribe | SOAP draft from consented conversation | feature (visit) | transcript | draft note (clinician signs) | — | Yes, in the visit | Drafting ran simulated only; **transcription failed live** (wrong model) [local] | **Not verified (misconfigured)** | Potentially high |
| Document Intelligence | Classify/extract uploads | feature (upload) | document | suggested patient/type | staff files it | Yes, in the review queue | 2 live ✓ [local] | **Functional** | Useful: in workflow |

**AI embedded in other workflows** (not listed as agents):
- **Discharge instructions:** AI draft at a 6th-grade reading level → `discharge.instructions` approval → portal [code]. Not verified live.
- **Claim review AI consistency check:** `claim_findings.source="ai"` [code]. On AWS only rule findings exist.
- **Command Center shift-handoff narrative:** every sentence must cite a case [code].
- **Realtime voice:** a session minted live 2× [local]; the conversation is not verified. It has no tools.

**Summary.** The genuinely useful AI today is **embedded in a workflow step**: chart answers, document extraction, discharge-instruction drafts and scribe drafts. The 7 manual agents mostly restate the cases. Only two action types exist (task, patient message), and on AWS they have never been proposed.

---

## 8. Audit of the automation engine

**Execution flow [code]:**
1. A beat schedule calls `run_all` about every minute (12,584 monitor runs in the last 24 h, all succeeded [AWS]).
2. `monitor.evaluate()` produces findings.
3. `open_case` deduplicates them, assigns a role, sets an SLA and logs a case event.
4. `on_open` hooks run (tasks, purchase requests, coverage requests).
5. `on_tick` handles stepwise reminders.
6. When overdue, `escalate_due` sets status `escalated` and adds `escalated_to`; the owner is kept and a notification is sent.
7. The next evaluation runs `clear()`, which **auto-resolves** the case once the condition is gone, with a resolution code.

Event handlers (`@handler`) react immediately to events such as `lab.critical_result` and `insurance.eligibility_checked`. Everything is audited.

**The 22 monitors:**

| Module | Monitors | Extra action beyond the case |
|---|---|---|
| Beds | cleaning delay, pending admission, discharge not departed | — |
| ED | boarding, door-to-provider | — |
| Equipment / inventory | maintenance due, below par | — |
| Insurance | visit readiness, stored end date | batch eligibility (simulated payer), staff **task**, **patient reminders** (portal; email/SMS to outbox), **coverage update request** → patient uploads card → staff review → re-verify → auto-resolve |
| Pharmacy | expiring, low stock, unusual usage | **purchase request** with recommended quantity (`status=submitted`) + approver notified; staff tasks |
| Lab | critical unacknowledged, turnaround | task on open |
| Radiology | unread, critical finding unacknowledged | — |
| Journey | follow-up not booked, intake missing | tasks |
| Staffing | coverage gap | — |
| Revenue | prior auth required, prior auth expiring, claims on hold | task on open (prior auth) |

**Automation Studio** (`app/services/automation.py`) runs 6 event-triggered workflows:
- no-show outreach;
- abnormal-result escalation;
- document routing;
- message triage;
- PHQ-2 follow-up;
- follow-up scheduling.

All six are enabled on AWS but have **0 runs** [AWS], because demo users haven't triggered those events. Locally there are 18 successful runs. It has its **own** approve/reject screen.

**Your example flow, checked step by step:**

| Step | Exists? |
|---|---|
| Stock becomes low | ✓ |
| Monitor detects it | ✓ `inventory.low_stock` |
| Case created | ✓ owned by pharmacist, with SLA |
| Pharmacist notified | ✓ notification |
| *AI suggests a response* | **✗ No.** The monitor itself prepares the purchase request with a rule-based quantity; no AI is involved, and the agent only runs if someone clicks |
| Authorized employee reviews it | ✓ approver role notified, but approval happens in **Pharmacy › Purchasing**, *not* in My work › Approvals |
| Approved action executed | ✓ purchase request → order (supplier simulated "SIM-PO") |
| Resolution verified | ✓ `clear()` closes the case when stock is above the reorder point |

So the chain is **largely complete with rules**. It lacks three things: an AI step, a single approval inbox, and a visible story connecting the steps.

---

## 9. Where current workflows stop (confirmed problems)

| Problem | Confirmed? | Evidence |
|---|---|---|
| Agents require a manual start every time | **Yes** | Single caller of `run_agent`; all 7 non-feature agents `trigger="manual"` |
| Too many informational summaries | **Yes** | Agent outputs are text; 0 approval requests on AWS |
| No connection between events/cases and AI | **Yes** | Monitors never invoke agents; agents only *read* cases |
| No clear next action after an agent run | **Yes** | The side panel shows text and, rarely, a proposal; no buttons to act on a specific case |
| Agents can't do meaningful operations | **Partly** | Only `create_task` and `patient_message` executors for agents; the rules have richer actions (purchase request, coverage request, reminders) that agents can't use |
| Repeated alerts / noise | **Yes** | 24 escalation notifications in 24 h; 77 of 86 cases open or escalated, many seeded days ago |
| Disconnected approval workflows | **Yes** | Three mechanisms: engine `approval_requests` (My work), purchase requests (Pharmacy), Automation Studio runs (its own page) |
| No visible outcome after an agent finishes | **Yes** | Runs aren't attached to the case timeline; results disappear when the panel closes (only in Agent Studio's activity log) |
| Tasks users must still complete manually | **Partly** | Insurance follow-ups and purchase approvals are automated up to the human step, which is correct; tasks from automation are 57 of 62 open |
| Poor automation history | **Partly** | Case timeline events exist (`actor_kind` monitor/agent/user) but aren't presented as a story |
| Agents misplaced | **Yes** | Patient Communication and Staff Scheduling live only in Agent Studio; Insurance Guardian agent exceeds its tool budget |

---

## 10. Proposed intelligent automation design

**Principle:**
- Rules detect.
- AI explains and chooses *from typed, safe actions*.
- Tools prepare.
- People approve.
- Executors act.
- Monitors verify.

This reuses the case engine, the approval engine and the existing tools. **No new agent framework.**

**10.1 The case assistant** (a mode of the existing runner):
- **Per-monitor setting** `ai_assist: off | on_open | on_escalation` in the monitor config, which already exists per organization in `get_config`. The default is **off** except for chosen monitors.
- **When a case opens or escalates** with assist enabled, enqueue `tasks.run_agent` on the `ai` queue (the task already exists) with the case as the subject. It is budgeted by the §6 limits.
- **Inputs:** only the case evidence, plus read tools scoped to the case's patient, item or claim.
- **Output:** structured, not free text:
  - **explanation:** 2–3 sentences;
  - **recommended action:** one typed action, or none;
  - **draft:** message or task text.

  The proposal becomes an `ApprovalRequest` with `payload.case_id`.
- **Record:** the explanation becomes a case event (`actor_kind="agent"`, "AI assisted"). The proposal event is "Waiting for approval by X".
- **After approval:** the executor acts, a case event records it, and the monitor's `clear()` verifies and closes. Every step goes to the audit log.
- **When AI is unavailable or the budget is exhausted:** the rule-based suggestion that already exists (for example the purchase-request quantity) is used, labelled as rules.

**10.2 Typed actions (executors).** These are safe, permissioned and approval-gated:
- **Existing:**
  - `agent.create_task`;
  - `agent.patient_message`, which must also respect contact preferences and consent through `engine.notifications.deliver`;
  - `discharge.instructions`;
  - `inventory.removal`.
- **Add:**

| Executor | What it does |
|---|---|
| `insurance.request_update` | Wraps `ensure_update_request` (a coverage request to the patient) |
| `pharmacy.review_purchase_request` | Adjusts quantity or adds a note on an existing purchase request; ordering still needs PR approval |
| `discharge.route_task` | Creates or assigns the missing checklist task to the owning department |
| `case.route` | Routes a follow-up task to a team for a group of cases (Command Center) |
| `claim.review_task` | A billing task listing the findings; never edits or submits claims |

**Never added:** prescribing, dispensing, order changes, claim submission, coding, and clinical discharge authorization.

**10.3 One approval inbox.**
- My work › Approvals lists, through read adapters:
  - engine approvals;
  - **submitted purchase requests** (for users with purchasing approval);
  - **pending Automation Studio runs**.
- Each item shows its type, its source case and Approve/Reject buttons that call the **existing** endpoints, so there is no new approval system.

**10.4 Noise control.**
- Reduce escalation notifications to **one digest per role per hour** instead of one per case.
- Group same-kind cases in notifications (the UI already groups them).
- A one-time synthetic-data housekeeping script to close stale seeded cases needs your explicit approval, because it changes data.

---

## 11. Department examples (what exists → what changes)

| Workflow | Exists today [code] | Change |
|---|---|---|
| **A. Insurance Guardian** | Detect (batch eligibility, simulated payer), identify the appointment, case, staff task, patient reminders (portal real; email/SMS outbox), coverage update request, card upload, staff review, re-verify, auto-resolve | AI assist **on_open** for `insurance.visit_readiness`: explain *why* in plain words and propose the best next action (`insurance.request_update` vs staff call task), drafting the patient message from the template; the approval appears in My work; the case story shows each step. Fix the agent's tool budget by giving it the case directly instead of searching. **Label:** "Payer response simulated" stays visible |
| **B. Pharmacy Watchdog** | Detect, identify the item, recommended quantity from usage, purchase request (submitted), approver notified, auto-resolve when stock is restored | AI assist **on_open** for low stock and expiring stock: explain the usage trend and whether to order, transfer stock between locations or let it expire; propose an adjusted quantity (`pharmacy.review_purchase_request`); approval in My work. No prescribing or dispensing |
| **C. Discharge** | Checklist with owner tasks; "Waiting on" summary; AI draft of patient instructions → approval → portal; `discharge.not_departed` monitor; physician-only override | AI assist **on_escalation** for `discharge.not_departed`: name the blocking items and owners, propose `discharge.route_task` for missing tasks, and draft coordination notes. Clinical discharge stays with the physician |
| **D. Hospital Operations** | Command Center three levels; "Explain bottlenecks" agent (text); handoff narrative citing cases | The Explain result lists **problem groups with case references**, each with a **Route follow-up** button that creates a `case.route` proposal for the owning team (e.g. "3 discharges waiting for pharmacy review → task to Pharmacy"). The admin inspects the cases via existing links |
| **E. Claims Review** | Rule findings plus an optional AI consistency check (`claim_findings`); claims on hold monitor | AI explains each finding in plain words and proposes a `claim.review_task` with suggested corrections as *suggestions*. It never submits or invents codes |
| **F. Patient Communication** | Agent drafts a message → approval → portal thread + notification | Place it where staff work: a "Draft reply/reminder" button in Messages and on insurance/follow-up cases. The executor must honour contact preferences and consent through `deliver()`, and portal delivery is real |

---

## 12. AI user experience — the case story

**One component used everywhere:** `CaseStory`, built from case events and approval/execution records.

```
● Problem detected    Low stock: Ondansetron — 6 on hand (reorder at 20)          Rule · 10:02
● AI assisted         Usage rose 40% this week; recommends ordering 120.          Live AI · gpt-4.1-mini · 10:03
● Action proposed     Purchase request #57 for 120 vials                            System · 10:03
◐ Waiting for approval  Pharmacist or hospital admin                               ← you can approve
○ Action executed     (after approval: order placed — supplier simulated)
○ Resolution verified (closes automatically when stock is above the reorder point)
```

**States:**
- Problem detected;
- AI assisted;
- Action proposed;
- Waiting for approval;
- Action executed;
- Resolution verified;
- **Needs human attention** (AI unavailable, failed, rejected or over budget).

Each state shows **who acts** and whether it is **automatic** or **needs a person**, using the existing icon+label status chips and provenance chips.

**Where it appears:**

| Screen | How |
|---|---|
| My work | Each case row shows the current story step chip; the case drawer shows the full story; Approvals is one inbox (§10.3) |
| Home | Priorities show "Waiting for your approval" items first among equal severity |
| Department workspaces | Pharmacy, Insurance, Discharge and Claims show the story inline on the case or item |
| Command Center | Level 2 rows show the stage chip per group (e.g. "4 waiting for approval") |
| Agent Studio | An **Outcomes** column per agent: cases assisted, proposals made, approved, executed, verified resolved (from `agent_runs` + approvals + case events), instead of only tool lists |
| Approval screens | The proposal shows the case story above Approve/Reject so the approver sees why |

---

## 13. Live OpenAI verification plan (small, synthetic data)

**Before testing:**
- Use the **real Super Admin**.
- Save the platform key.
- Set the transcription model to an OpenAI transcription model your account supports (e.g. `whisper-1` or a `gpt-4o-*-transcribe` model), and run **Test connection** for each capability.
- Expect about 12–15 calls on `gpt-4.1-mini`; the cost should be small, but confirm it in the OpenAI usage dashboard.

**Proof of a genuine call:**
- **UI:** a *Live AI · model* label.
- **Database:**
  - `agent_runs.mode='openai'` with input/output tokens > 0;
  - or `ai_jobs.provider='openai'` with tokens;
  - an audit event (`agent.run` or the feature's event).
- **OpenAI dashboard:** matching request count.
- **Tool activity:** Agent Studio › Activity log (or `agent_runs.tool_calls`).

| # | Feature | Account · screen | Input / action | Expected | Approval / audit |
|---|---|---|---|---|---|
| 1 | Provider & models | Super Admin · AI settings | Test connection | Each capability ✓; a wrong transcription model is flagged | `ai_provider_settings.last_test_result` |
| 2 | Hospital Operations | Hospital Admin · Command Center | Explain bottlenecks | Cites case refs; may propose a task | `agent.run`; approval if proposed |
| 3 | Insurance Guardian agent | Insurance Specialist · Insurance | Summarize coverage issues | Completes within the tool limit (after the fix) | `agent.run` |
| 4 | Pharmacy Watchdog | Pharmacist · Pharmacy | Summarize inventory risks | Names items and purchase requests | `agent.run` |
| 5 | Discharge Coordination | Nurse · discharge checklist | What's this waiting on? | Names blocking steps and owners; proposes a task | approval request → approve as charge nurse → task appears |
| 6 | Claims Review | Billing · Claims | Explain claim problems; *and* run claim review on one claim | Text answer; `claim_findings.source='ai'` row | `claim.reviewed` audit with `ai_model` |
| 7 | Doctor Assistant | Doctor · chart › Ask AI | "Summarize this patient's history" | Cited answer | `ai_jobs` kind `chart_qa`, provider `openai` |
| 8 | Medical Scribe | Doctor · visit › AI scribe | Consent → record 20–30 s of synthetic dialogue → Stop | Transcript, then SOAP draft, "AI draft" until signed | `ai_jobs` `scribe_transcription` and `scribe_note` openai |
| 9 | Document Intelligence | Front desk · Documents | Upload a synthetic referral PDF | Type, patient match, extracted fields for review | `ai_jobs` `document_analysis` openai |
| 10 | Realtime Voice | Front desk · AI receptionist › voice | Start voice session, speak, end | Spoken replies + transcript; no record access (by design) | `ai_jobs` `realtime_session` openai; session ends within limits |

---

## 14. Four-phase implementation roadmap

### Phase 1 — Permanent Super Admin and persistent OpenAI
| | |
|---|---|
| **Existing** | Seeded `admin@undeclared.dev`; password change; TOTP MFA; encrypted platform AI settings; session-scoped demo AI; `DEMO_OPENAI_API_KEY` fallback |
| **Root cause** | No email change or out-of-band recovery; key entered in demo scope; no owner-managed demo provider; in-memory, unenforced limits |
| **Changes** | `app/cli.py` (create-superadmin, reset-password, list-superadmins); `POST /auth/email/change`; `ai_provider_settings` `scope="demo"` + `policy` JSONB; `/admin/ai-settings/demo` endpoints and kill switch; Redis counters; budgets from recorded usage; model allow-list; per-capability Test connection; rule fallback when OpenAI fails; Account page email form; AI settings "Public demo AI" card |
| **Files** | `backend/app/cli.py` (new), `api/routers/auth.py`, `schemas/auth.py`, `api/routers/ai_admin.py`, `ai/demo_scope.py`, `ai/config.py`, `ai/realtime.py`, `agents/runner.py`, `models/ai_settings.py`, `alembic/versions/0030_*`, `frontend/src/features/account/AccountPage.tsx`, `features/admin/AISettingsPage.tsx`, `e2e/deploy_smoke.py` |
| **DB** | One additive migration (JSONB column). No resets |
| **Security / cost** | No public registration; CLI only over SSH; keys never returned to demo users; kill switch; daily and monthly budgets; synthetic organizations only |
| **Tests** | CLI and email-change tests; demo row resolution (owner key used, never returned); limits across processes (Redis); kill switch; transcription-model validation; fallback labelling |
| **Complexity** | Low–medium |
| **Benefit** | You sign in as yourself; AI works for every demo visitor after one setup, within a budget you control |

### Phase 2 — Reliable live AI
| | |
|---|---|
| **Existing** | 6 live agent runs and 2 chart Q&A [AWS]; document AI live [local]; scribe transcription failing; voice unverified |
| **Root cause** | Untested capabilities; wrong transcription model; Insurance Guardian agent over its tool budget |
| **Changes** | Run the §13 plan; fix model configuration; give agents case-scoped context (fewer tool calls); raise `max_tool_calls` only where justified; record results in `docs/` |
| **Files** | `agents/runner.py` (case-scoped input), `agents/tools.py` (case-scoped variants), settings only |
| **DB** | None |
| **Security / cost** | About 15 calls; synthetic data; `AI_PHI_ALLOWED` stays as configured |
| **Tests** | The §13 checklist; existing mocked tests remain |
| **Complexity** | Low |
| **Benefit** | Every AI feature is either verified live or clearly labelled |

### Phase 3 — Intelligent workflow automation
| | |
|---|---|
| **Existing** | Rules engine with cases, tasks, purchase requests, coverage requests, reminders and auto-resolution; approval engine with 4 executors; agents with 2 propose tools |
| **Root cause** | AI not attached to cases; few typed actions; three approval systems |
| **Changes** | Per-monitor `ai_assist`; case assistant run on `ai` queue with structured output; new executors (§10.2); unified Approvals inbox (adapters); Command Center "Route follow-up"; escalation digest |
| **Files** | `engine/monitors.py`, `engine/cases.py`, `engine/approvals.py`, `agents/runner.py`, `agents/tools.py`, `monitors/{insurance,pharmacy,beds,revenue}.py`, `tasks.py`, `engine/notifications.py`, `api/routers/operations.py` (approvals list), `features/ops/*`, `features/command/CommandCenter.tsx` |
| **DB** | Probably none (`approval_requests.payload` and `case_events.data` are JSON); optional index on `approval_requests(payload->>'case_id')` |
| **Security / cost** | Assist off by default and enabled per monitor; budgeted; approvals by real staff; no clinical or claim-submitting actions |
| **Tests** | Per workflow: case opens → assist runs (mocked AI) → proposal → approve → executor → `clear()` resolves; budget exhaustion falls back to rules; demo users can't approve |
| **Complexity** | Medium |
| **Benefit** | Rules → AI → action → approval → verified, without users starting anything |

### Phase 4 — UX and demonstration
| | |
|---|---|
| **Existing** | Status and provenance chips; case drawer timeline; Agent Studio activity log |
| **Root cause** | No single "story"; outcomes invisible; agents misplaced |
| **Changes** | `CaseStory` component (§12) in My work, the case drawer, departments and Command Center; Agent Studio Outcomes; move Patient Communication into Messages and cases, Staff Scheduling into Roster; a guided demo script on the AI & Automation page |
| **Files** | `components/common/CaseStory.tsx` (new), `features/ops/*`, `features/pharmacy`, `features/insurance`, `features/inpatient`, `features/revenue`, `features/ai/AgentStudio.tsx`, `features/command/CommandCenter.tsx` |
| **DB** | None |
| **Security / cost** | Read-only presentation |
| **Tests** | Component test via E2E: a low-stock case shows the 6 steps; approvals appear in My work |
| **Complexity** | Low–medium |
| **Benefit** | Staff see what happened, what the system did and what they need to do |

**All four phases run on the existing infrastructure** (FastAPI, Postgres, Redis, Celery, EC2). The only outside item is a dedicated OpenAI project with a spending limit (recommended, not required).

---

## 15. Risks and tradeoffs

- **Cost exposure.** Real calls are made from a public demo. Mitigated by budgets, Redis limits, the kill switch and OpenAI project limits.
- **Approval fatigue.** Assisting every case would flood approvals. Enable assist per monitor, starting with low stock, insurance readiness and discharge-not-departed.
- **AI error.** Proposals can be wrong. They are limited to typed, reversible actions; every one needs a human and is verified by rules.
- **Patient data.** The demo is synthetic only. Keep `ai_phi_allowed` off for real organizations until a BAA and review exist.
- **Shared seed password.** After you take over the admin account, other seeded staff accounts still share `SEED_DEMO_PASSWORD`; rotating it is separate and affects tests.
- **Data cleanup.** Closing stale seeded cases changes data and needs your approval.
- **Small server.** A t3.small runs AI on Celery's `ai` queue. Keep global concurrency low (≈6).

---

## 16. Top 10 changes to prioritise

1. **Take over `admin@undeclared.dev` now:** sign in, change the password, enable MFA. No code needed.
2. **SSH-only `create-superadmin` / `reset-password` CLI** and re-authenticated email change.
3. **Owner-managed "Public demo AI"** (scope `demo` row, enable switch, key source, allowed models).
4. **Redis-backed limits, daily and monthly budgets, set `AI_PRICES`, kill switch.**
5. **Fix the transcription model** and add per-capability Test connection.
6. **Rule fallback with a "Simulated (AI unavailable)" label** when OpenAI fails.
7. **One Approvals inbox** in My work (engine approvals + purchase requests + Automation Studio runs).
8. **Case assistant on case open or escalation** for three monitors, with typed executors.
9. **CaseStory** in My work, the case drawer, departments and Command Center; Agent Studio Outcomes.
10. **Run the §13 live verification** and publish the verified list (update the website's product status).

---

## Recommendation

HMS Workflows already has the hard part: a deterministic engine that finds hospital problems, assigns an owner, prepares many next steps and verifies resolution. It feels like "assistants and alerts" because the AI sits beside that engine as on-demand summaries, and because the engine's progress is invisible and its approvals are scattered.

Make it genuinely useful by:
- **attaching AI to the case lifecycle**, so that rules detect, AI explains and picks a typed, safe action, a person approves in one inbox, the system executes, and the rules confirm it's fixed;
- **showing that sequence as one story** wherever staff already work.

Do this after you own the Super Admin account and the demo AI runs on a persistent, owner-controlled, budgeted key, so every visitor sees the same live behaviour without anyone re-entering a key.
