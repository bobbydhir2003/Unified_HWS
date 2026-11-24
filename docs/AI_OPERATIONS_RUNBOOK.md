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

## Workspaces (header role switcher)

A platform Super Admin can work in any of the 14 hospital roles from the header ("Workspace: …"); someone with several
roles can switch between their own. See `docs/WORKSPACES.md`. AI settings and the emergency switch above are available
only to a platform Super Admin, in the Super Admin workspace.

## Former Demo Mode (retired)

Demo Mode, its one-click demo logins, private demo hospitals and the owner-managed public demo AI were removed. On a
server that ran it, run once:

```
docker compose exec api python -m app.cli retire-demo
```

It asks for the phrase `RETIRE DEMO`, removes only demo-owned data (registered demo hospitals and their identities and
files), ends demo sessions, and deactivates the demo-only `superadmin.demo@harborview.dev` account. Real organizations,
accounts, AI settings and audit history are untouched.

## Automatic case assistance

AI assists only selected case kinds, once per trigger:

- **When the case opens:** low stock, expiring stock, insurance visit readiness, discharge not departed, claims on hold.
- **When the case escalates:** staffing gap.

There is a per-organization daily cap, `AI_AUTO_ASSIST_DAILY_LIMIT` (default 60).

Each assist produces at most one proposal from that case kind's allow-list. A proposal becomes an approval request handled by an existing executor. Nothing executes without an authorized person, and requesters cannot approve their own requests.

When AI is unavailable, the case gets an "AI assistance unavailable" event and the standard workflow continues.
