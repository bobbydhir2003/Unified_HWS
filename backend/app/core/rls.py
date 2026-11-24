"""PostgreSQL row-level security helpers (defense in depth behind TenantContext checks).

Requests that resolve a tenant run every transaction as the restricted role `undeclared_app` with
`app.org_id` set (see `app.core.db`). Policies then hide and reject rows from other organizations even if
application code forgets a filter. System code (auth, webhooks, Celery, seed) keeps the owner role.
"""

APP_ROLE = "undeclared_app"

# Tables with organization_id that intentionally stay outside RLS: a user's memberships across organizations are
# needed to switch orgs, and are only ever read through the authenticated user.
# demo_sandboxes is the platform's registry of private demo hospitals (lifecycle only, no tenant data); it is read by
# system code and to recognise the caller's own hospital, and must stay readable while a hospital is being purged.
RLS_EXEMPT = {"memberships", "demo_sandboxes"}

POLICY = "tenant_isolation"


def policy_sql(table: str, nullable: bool) -> list[str]:
    cond = "organization_id = nullif(current_setting('app.org_id', true), '')::uuid"
    if nullable:
        cond = f"(organization_id IS NULL OR {cond})"
    return [
        f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY',
        f'DROP POLICY IF EXISTS {POLICY} ON "{table}"',
        f'CREATE POLICY {POLICY} ON "{table}" USING ({cond}) WITH CHECK ({cond})',
    ]


def enable_rls_all(op) -> None:
    """Enable RLS on every table that has organization_id (except exemptions). Idempotent; call from migrations."""
    conn = op.get_bind()
    rows = conn.exec_driver_sql(
        "SELECT table_name, is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name = 'organization_id'"
    ).all()
    for table, nullable in rows:
        if table in RLS_EXEMPT:
            continue
        for stmt in policy_sql(table, nullable == "YES"):
            op.execute(stmt)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
