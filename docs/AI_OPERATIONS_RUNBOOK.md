# AI operations runbook (platform owner)

## Super Admin recovery (server access required)

There is no public Super Admin registration. On the server:

```
docker compose exec api python -m app.cli list-superadmins
docker compose exec api python -m app.cli reset-password --email <owner email> [--disable-mfa]
docker compose exec api python -m app.cli set-email --email <old> --new-email <new>
docker compose exec api python -m app.cli create-superadmin --email <email> [--org <slug>]
```

Each command asks for a typed confirmation. Passwords are read without echo and never printed. Every command signs out the account's sessions and writes an audit event. In the app, Account → Sign-in email / Password / Two-factor covers routine changes.

## Platform AI

Super Admin → AI settings: provider, encrypted key (write-only), models per capability, and per-agent models.

- **Test connection** makes one tiny real call per configured capability: text, vision, transcription and realtime.
- Model slots are validated by family. A realtime model can't be saved as the transcription model.
- **Emergency: switch off all AI** (owner card) makes every AI feature show its labelled simulation immediately. Rules, tasks, notifications and approvals keep working.

## Public demo AI (owner-managed)

It is off by default. To turn it on:

1. Create a separate OpenAI project for the demo.
2. Set a monthly spending limit on that project in the OpenAI dashboard. The in-app budget is an estimate, not a billing cap.
3. In AI settings → Public demo AI, enter the project key and models, choose the assistants, and review the limits.
   - Defaults: 25 requests per visitor per day, 200 per day overall, $10 estimated per month, 2 concurrent requests per visitor, voice off.
4. Click **Test demo provider**, then **Turn on**.

Visitors never receive the key. A visitor who enters their own temporary key uses only that key, for their session only.

Enforcement:

- Request counts and estimated spend are atomic and durable, in the `ai_usage_counters` table.
- Concurrency is limited through Redis. In staging and production, the request is refused if Redis is unreachable.

To stop demo AI:

- From the app: **Turn off now**.
- From the server, without the app: set `DEMO_AI_DISABLED=true` and restart the api and worker.

## Automatic case assistance

AI assists only selected case kinds, once per trigger:

- **When the case opens:** low stock, expiring stock, insurance visit readiness, discharge not departed, claims on hold.
- **When the case escalates:** staffing gap.

There is a per-organization daily cap, `AI_AUTO_ASSIST_DAILY_LIMIT` (default 60).

Each assist produces at most one proposal from that case kind's allow-list. A proposal becomes an approval request handled by an existing executor. Nothing executes without an authorized person, and requesters cannot approve their own requests.

When AI is unavailable, the case gets an "AI assistance unavailable" event and the standard workflow continues.
