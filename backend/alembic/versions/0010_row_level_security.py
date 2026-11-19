"""row level security

Revision ID: 0010
Revises: 0009
"""
from collections.abc import Sequence

from alembic import op
from app.core.rls import APP_ROLE, POLICY, RLS_EXEMPT, enable_rls_all

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(f"""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            IF (SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user) THEN
                CREATE ROLE {APP_ROLE} NOLOGIN;
            ELSE
                RAISE EXCEPTION 'Role {APP_ROLE} is missing. A database administrator must run: CREATE ROLE {APP_ROLE} NOLOGIN; GRANT {APP_ROLE} TO %;', current_user;
            END IF;
        END IF;
        -- SET ROLE requires membership (non-superuser owners such as the RDS master user).
        IF NOT pg_has_role(current_user, '{APP_ROLE}', 'MEMBER') THEN
            EXECUTE format('GRANT {APP_ROLE} TO %I', current_user);
        END IF;
    END $$""")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}")
    enable_rls_all(op)


def downgrade() -> None:
    conn = op.get_bind()
    rows = conn.exec_driver_sql("SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
                                "AND column_name='organization_id'").all()
    for (table,) in rows:
        if table in RLS_EXEMPT:
            continue
        op.execute(f'DROP POLICY IF EXISTS {POLICY} ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
