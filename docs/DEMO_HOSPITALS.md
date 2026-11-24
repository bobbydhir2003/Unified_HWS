# Private demo hospitals

With `DEMO_MODE=true` (never allowed in production), every visitor who clicks a demo button gets their own synthetic
hospital. They can switch between all 14 application roles inside it, change anything a hospital can change, and reset
it. Nobody else sees it.

## How it works

- **One organization per visitor.** A demo hospital is a separate organization, built by the same builder as Harborview
  (`app.seed.build_hospital`). It has its own patients, staff, facilities, beds, schedule, inventory, lab, radiology,
  billing and insurance scenarios, and its automation cases.
- **Isolation uses the platform's tenant model.** That means membership checks in `TenantContext` and PostgreSQL
  row-level security. A demo identity is also pinned to its own hospital (`deps.get_ctx`).
- **Identities.**
  - Each hospital has one identity per role, plus all its other staff and the portal patient.
  - Emails look like `<name>@<tag>.demo.example.com` (a reserved domain that is never delivered).
  - Identities have no password and are marked with `users.sandbox_org_id`.
  - Password sign-in, password reset and invitation acceptance refuse them.
- **Leases.**
  - `POST /auth/demo-login` leases a ready hospital from the pool, or builds one if the pool is empty and the cap allows.
  - Every session carries the lease. Every request checks that the lease is still active and belongs to that hospital.
  - If the browser already has an active hospital, a demo button opens the chosen role inside it instead of starting a
    new hospital.
- **Role switching.**
  - `POST /auth/demo/switch` takes either `{key}` (one of the 14 roles) or `{user_id}` (anyone in the same hospital).
  - It starts a new session for that identity and ends the previous one.
  - The identity's normal permissions apply. Requester and approver must still be different people, clinical
    signing still needs the clinical permissions, and restricted charts still need break-the-glass access.
- **What a demo identity can't do (platform level).** Create organizations, open the owner's AI controls, change a
  password/email/MFA, or change the settings that mark the hospital as a demo (`synthetic_data`, `sandbox`, webhook
  secrets, status). Everything else inside the hospital is editable: facilities, departments, staff and roles,
  appointment types, availability, fee schedule, monitors, workflows, agent settings and demo AI settings.
- **Adding staff.** An "invitation" in a demo hospital creates the staff member directly, without a password. They then
  appear in the role switcher. Emailed invitation links can't be accepted.
- **External effects.**
  - Every integration adapter is a simulator (the clearinghouse, eligibility checks, order transmission, the imaging
    archive), and messages go only to the outbox.
  - If an operator configures any non-simulated adapter, demo hospitals refuse to start (fail closed).
- **AI.**
  - A visitor's AI settings and agent overrides are kept for their lease, so they survive role switches. Their request
    limits are also per lease, so switching roles doesn't reset them.
  - Background AI work for a demo hospital (automatic case assistance, documents arriving without a visitor) never uses
    the platform key. It uses only the owner-managed demo provider under its shared limits, or the labelled simulation.

## Lifecycle

`building → ready (pool) → leased → releasing → purging → purged`

The Celery beat task `demo_sandbox_maintain` runs every 60 s (or the in-process scheduler in development). Each run:

- Expires leases idle for `DEMO_SANDBOX_IDLE_HOURS` (default 4) or older than `DEMO_SANDBOX_MAX_HOURS` (default 24).
- Removes released hospitals with a single cascading delete. The append-only triggers allow that delete only for an
  organization registered here with status `purging` (migration 0031). Real organizations stay immutable.
- Deletes the hospital's stored files.
- Retires pool hospitals built on an earlier day, so "today's" schedule is always current.
- Builds at most one new hospital per run, until `DEMO_SANDBOX_POOL_SIZE` (default 3) are ready.

Other behaviour:

- **Reset my hospital** (`POST /auth/demo/reset`, confirm `RESET`) leases a fresh hospital for the same visitor and
  removes the old one.
- Lifecycle events (`demo.sandbox_built`, `leased`, `released`, `purged`) are recorded in the platform audit log, without
  an organization, so they outlive the hospital. Activity inside a hospital is audited in that hospital and removed with
  it.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `DEMO_SANDBOX_ENABLED` | true | false = the old shared seven accounts (restricted) |
| `DEMO_SANDBOX_POOL_SIZE` | 3 | hospitals kept ready |
| `DEMO_SANDBOX_MAX_TOTAL` | 8 | hard cap on hospitals that exist at once |
| `DEMO_SANDBOX_PER_VISITOR` | 2 | open hospitals per client address |
| `DEMO_SANDBOX_IDLE_HOURS` / `_MAX_HOURS` | 4 / 24 | expiry |

Capacity:

- A hospital is about 2,700 rows and about 40 identities.
- Building one takes about 5 s on a laptop and is slower on a small server.
- Removing one takes well under a second.
- When the cap is reached, visitors see "All demo hospitals are in use right now".

## The Harborview organization

Harborview, the platform administrator and the seven original demo accounts are untouched. Visitors never land in
Harborview any more. If someone signs into one of the old shared accounts with a password while demo mode is on, the
original restrictions still apply.
