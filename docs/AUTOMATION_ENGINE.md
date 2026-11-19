# Automation engine

Code: `backend/app/engine/` (events, cases, monitors, notifications, approvals, scheduler), monitors in `backend/app/monitors/`.

**Loop:** Detect (outbox events + scheduled monitors) → Prioritize (severity, SLA `due_at`) → Assign (role/user, facility/department) → Assist (tasks, drafts, patient requests) → Approve/Execute (`approval_requests`, executors re-check permissions; no self-approval) → Verify (monitor re-evaluates; case closes only when the condition is gone) → Audit (`case_events` append-only + `audit_events`).

| Guarantee | Mechanism |
|---|---|
| Events never lost | `domain_events` row written in the same transaction; dispatcher runs after commit and every 10 s (beat) |
| Exactly-once effects | handler effects + `event_handlings(event_id, handler)` unique row commit together; SKIP LOCKED |
| Retries | exponential backoff, `dead` after 6 attempts, manual retry in UI |
| One case per problem | partial unique index on `(organization_id, dedupe_key)` for open statuses |
| One reminder per step | `notification_deliveries` unique `(organization_id, dedupe_key)`; patient daily cap 3; preferences |
| Escalation once per level | conditional UPDATE on `escalation_level` |
| Rule traceability | `monitor_configs.version` stamped on each case |

Scheduling: Celery beat (`engine-dispatch` 10 s, `engine-escalations` 60 s, `engine-monitors` 300 s) on queue `engine`; dev without Redis: `ENGINE_INPROCESS_SCHEDULER=true`.

Adding a monitor: subclass `Monitor` (`evaluate` → `Finding`s with stable dedupe keys; optional `on_open`, `on_tick`, `clear`), `register()` it, import in `app/monitors/__init__.py`.
