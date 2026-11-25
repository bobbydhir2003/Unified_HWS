# HMS Intelligence (HMS Assist) — conversational department agents

Ten agents, one conversation runtime. Employees open the agent from the record they are working on; administrators
configure and review agents in Agent Studio.

Display names are marketing names (not trademark-cleared) defined in `backend/app/agents/runner.py` (`DISPLAY`, `ROLE`),
`frontend/src/lib/assist.ts` and `frontend/src/features/public/agents.ts`; agent keys, stored configurations,
conversations and approvals use the internal keys, so renaming never needs a migration.

| Agent (display) | Key | Opens on | Entry points |
|---|---|---|---|
| Aurelia — Insurance & Coverage AI | `insurance_guardian` | insurance case, patient, workspace | Case drawer, Insurance Guardian header, Home |
| Veyra — Pharmacy & Inventory AI | `pharmacy_watchdog` | pharmacy/inventory case, inventory item, workspace | Case drawer, item drawer, Pharmacy header |
| Elara — Discharge Coordination AI | `discharge_coordination` | discharge case, inpatient stay, workspace | Discharge checklist, case drawer |
| Orion — Hospital Operations AI | `hospital_operations` | any case, workspace | Command Center, case drawer (fallback agent) |
| Valora — Billing & Claims AI | `claims_review` | billing case, claim, workspace | Revenue claim detail, Billing claim drawer, case drawer |
| Liora — Patient Communication AI | `patient_communication` | message thread, patient, case, workspace | Message thread, Messages header |
| Nexa — Staff Scheduling AI | `staff_scheduling` | staffing case, workspace | Roster header, case drawer |
| Aster — Patient Chart AI | `doctor_assistant` | patient | Chart / encounter "Ask AI" |
| Sonara — Medical Scribe AI | `medical_scribe` | scribe session | Scribe panel ("Ask about this draft") |
| Lucent — Document Intelligence AI | `document_intelligence` | document | Document review |

## How a turn works (`backend/app/services/assist.py`)
1. The browser sends only `{agent_key, context_type, context_id}` and the message text.
2. The server checks: conversation owner, same workspace (acting role) as when the conversation started, agent enabled
   (globally/facility), user permission; then **re-resolves the record** through the normal access helpers
   (`app/agents/context.py`) — restricted charts, facility/department scope and organization isolation apply every turn.
3. One `AgentRun` per turn. Live provider: staff AI limits are admitted first (`app/ai/limits.py`), then
   `OpenAICore.tool_loop` with bounded history (`ASSIST_HISTORY_MESSAGES`), the record binding and the database status of
   this conversation's proposals. No provider: a labelled rule-based plan over the same tools.
4. Every tool call goes through `tools.execute`: allow-list → user permission → strict arguments → **record pins** (a
   tool can't name a different case/patient/claim than the conversation's record) → run.
5. The assistant message stores tool activity, citations and action references. Statuses shown in the panel come
   from `approval_requests` / `assist_action_drafts`, never from model text.

## Actions
* **Read & explain** — read tools only.
* **Confirm in chat** (`prepare_*`): case note, eligibility re-check (simulated payer), claim re-scrub, scribe draft
  section revision. Runs only when the same user confirms, through the existing service, with their permissions.
* **Request approval** (`propose_*`): staff task, patient portal message, insurance update request, purchase-request
  quantity. Records requester, facility, conversation and run; a **different person** must approve (same user id is
  refused whatever workspace they switch to); duplicates are folded into the pending one; failures can be retried by
  another authorized person; pending agent proposals expire after `APPROVAL_EXPIRY_DAYS`. The conversation gets a
  system message on every outcome.
* Never: prescribe/verify/dispense/administer, sign/apply notes, diagnose, discharge, edit/submit/void claims, send
  messages without approval, purchase, change shifts. Mandatory controls are appended to every run (`runner.MANDATORY`)
  and are not editable in Agent Studio.

## Limits and switches
* `AI_USER_DAILY_REQUESTS`, `AI_AGENT_DAILY_REQUESTS`, `AI_ORG_DAILY_REQUESTS`, `AI_ORG_MONTHLY_BUDGET_USD` (reserved
  before each live call, reconciled after), `AI_USER_CONCURRENCY`, `AI_MAX_OUTPUT_TOKENS`.
* Kill switches: platform (AI settings → disable), per agent (Agent Studio switch / facility override — honored by
  conversations, Studio runs, chart Q&A, scribe, documents and automatic case assistance, re-checked in workers),
  per monitor AI (Monitors page).
* `ASSIST_CONVERSATIONS=off|synthetic|all` (default `synthetic`: organizations flagged `synthetic_data`). With `off`
  the original one-shot buttons and chart assistant are used.
* `ASSIST_AUTO_ACTIONS=false` — no automatic execution of any action.

## Monitors
6 monitors keep AI assistance on (insurance readiness, low stock, expiring stock, discharge not departed, claims on
hold, staffing gap on escalation). 7 more can be switched on per monitor (unusual usage, pending admission, bed cleaning
delay, ED boarding — on escalation; prior auth required/expiring; follow-up not booked). Critical lab, critical imaging
and ED door-to-provider are **rule-only** and can't be switched to AI. Each case is assisted once per trigger (atomic
claim), within the daily automatic cap and the organization's monthly budget.

## Retention and access
Conversations are operational records, not part of the chart. Content is redacted after `ASSIST_RETENTION_DAYS`
(metadata, audit and approvals stay; legal hold flag blocks redaction). Messages are append-only (DB trigger). Owners see
their own conversations; administrators with `ai:manage` review them in Agent Studio (every review audited; restricted
charts excluded). Audit events carry ids and tool names, never message text.
