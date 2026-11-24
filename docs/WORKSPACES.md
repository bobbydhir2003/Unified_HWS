# Workspaces (header role switcher)

You sign in once with your own account and choose which hospital role you're working in from the header:
**Workspace: Doctor ▾**. The sidebar, dashboard and available actions follow the workspace you choose, and so does
every API request.

## Who can switch

- **A platform Super Admin** (`users.is_superadmin`, for example `admin@undeclared.dev`) can choose any of the 14 roles:
  Super Admin, Hospital Administrator, Facility Admin, Doctor, Nurse / MA, Receptionist, Billing Specialist, Insurance
  Specialist, Pharmacist, Laboratory Technologist, Radiology Technologist, Radiologist, Bed Manager and Patient.
- **Someone with several roles** (for example a doctor who is also a facility admin) can switch between their own
  roles.
- **Everyone else** has a single role. They don't see a switcher, and the server refuses any other role.

## How it is enforced

- The browser sends `X-Acting-Role` with each request. `app.api.deps.get_ctx` checks the request against
  `workspace_roles()`, which is the same rule `/auth/me` uses to list workspaces. The request then runs with **only
  that role's permissions**.
- An unknown role returns 400. A role you aren't allowed returns 403 and is written to the audit log.
- The person never changes. Every audit event records the real signed-in user as the actor, and adds
  `details.acting_role`.
- **Safeguards don't depend on the role:**
  - "Requester can't approve" and the two-person checks (lab verification, pharmacy waste, handoff acknowledgement)
    compare people, not roles. Switching workspaces never makes you two different people.
  - Clinical signing needs a real provider profile for the signed-in person. A Super Admin working as Doctor can draft
    orders and notes, but a provider has to sign them.
  - Restricted charts still need the patient's own provider or a recorded access grant, in every workspace.
  - The Patient workspace (the portal) shows only the signed-in person's own patient record. For a staff account, it
    explains that there isn't one.
- **Platform settings** (AI provider and key, the emergency AI switch, creating organizations) are available only to a
  platform Super Admin, in the Super Admin workspace. An organization-level Super Admin role isn't enough.

The browser remembers your workspace per account, so a refresh keeps it. It's always re-checked against the list from
`/auth/me`.

## Former Demo Mode

Demo Mode was retired. Its endpoints no longer exist, and `python -m app.cli retire-demo` removes what it left behind
(see `docs/AI_OPERATIONS_RUNBOOK.md`). The database tables and columns it added (`demo_sandboxes`,
`users.sandbox_org_id`, `user_sessions.sandbox_lease_id`) are kept so migration history stays intact, and they stay
empty.
