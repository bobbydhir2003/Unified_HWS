"""Private demo hospitals: demo_sandboxes, sandbox identities (users.sandbox_org_id), lease-bound sessions, and an
authorised-purge exception in the append-only triggers.

The exception is deliberately narrow. A row of an append-only table (or a signed note / final imaging report) may be
deleted or nulled ONLY when ALL of these hold:
  * the transaction set app.sandbox_purge to an organization id (system code in app/demo/sandbox.py does this);
  * that organization is registered in demo_sandboxes with status 'purging';
  * the row belongs to that organization (or, for audit_events, its actor is an identity of that demo hospital).
Real organizations are never registered in demo_sandboxes, so their records stay immutable exactly as before.

Revision ID: 0031
Revises: 0030
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PURGE_FUNCTIONS = """
CREATE OR REPLACE FUNCTION sandbox_purge_allows(tbl text, old jsonb) RETURNS boolean AS $$
DECLARE purge text := coalesce(current_setting('app.sandbox_purge', true), '');
BEGIN
  IF purge = '' THEN
    RETURN false;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM demo_sandboxes s WHERE s.organization_id::text = purge AND s.status = 'purging') THEN
    RETURN false;
  END IF;
  IF old->>'organization_id' = purge THEN
    RETURN true;
  END IF;
  RETURN tbl = 'audit_events' AND EXISTS (
    SELECT 1 FROM users u WHERE u.id::text = old->>'actor_user_id' AND u.sandbox_org_id::text = purge);
END $$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
  -- Authorised removal of a private demo hospital (see sandbox_purge_allows).
  IF sandbox_purge_allows(TG_TABLE_NAME, to_jsonb(OLD)) THEN
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
  END IF;
  -- Patient identity reconciliation may re-point patient_id (and nothing else) while app.patient_merge = 'on'.
  -- The audit log is never rewritten.
  IF TG_OP = 'UPDATE' AND TG_TABLE_NAME <> 'audit_events' AND current_setting('app.patient_merge', true) = 'on'
     AND (to_jsonb(NEW) - 'patient_id') = (to_jsonb(OLD) - 'patient_id') THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION '% is append-only (% blocked)', TG_TABLE_NAME, TG_OP USING ERRCODE = 'integrity_constraint_violation';
END $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION freeze_signed_note() RETURNS trigger AS $$
BEGIN
  IF OLD.status = 'signed' THEN
    IF sandbox_purge_allows(TG_TABLE_NAME, to_jsonb(OLD)) THEN
      RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'UPDATE' AND current_setting('app.patient_merge', true) = 'on'
       AND (to_jsonb(NEW) - 'patient_id') = (to_jsonb(OLD) - 'patient_id') THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION 'signed clinical note % cannot be modified; add an addendum', OLD.id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION freeze_final_report() RETURNS trigger AS $$
BEGIN
  IF OLD.status = 'final' THEN
    IF sandbox_purge_allows(TG_TABLE_NAME, to_jsonb(OLD)) THEN
      RETURN NEW;
    END IF;
    -- After signing, only addenda and critical-finding acknowledgment may change.
    IF (to_jsonb(NEW) - 'addenda' - 'critical_ack_at' - 'critical_ack_by_id' - 'critical_read_back' - 'updated_at')
       IS DISTINCT FROM (to_jsonb(OLD) - 'addenda' - 'critical_ack_at' - 'critical_ack_by_id' - 'critical_read_back' - 'updated_at') THEN
      RAISE EXCEPTION 'signed imaging report % cannot be modified; add an addendum', OLD.id USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
"""

# Exactly the bodies in force before this revision (0016 merge-aware versions and 0020).
RESTORE_FUNCTIONS = """
CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger AS $$
BEGIN
  -- Patient identity reconciliation may re-point patient_id (and nothing else) while app.patient_merge = 'on'.
  -- The audit log is never rewritten.
  IF TG_OP = 'UPDATE' AND TG_TABLE_NAME <> 'audit_events' AND current_setting('app.patient_merge', true) = 'on'
     AND (to_jsonb(NEW) - 'patient_id') = (to_jsonb(OLD) - 'patient_id') THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION '% is append-only (% blocked)', TG_TABLE_NAME, TG_OP USING ERRCODE = 'integrity_constraint_violation';
END $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION freeze_signed_note() RETURNS trigger AS $$
BEGIN
  IF OLD.status = 'signed' THEN
    IF TG_OP = 'UPDATE' AND current_setting('app.patient_merge', true) = 'on'
       AND (to_jsonb(NEW) - 'patient_id') = (to_jsonb(OLD) - 'patient_id') THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION 'signed clinical note % cannot be modified; add an addendum', OLD.id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION freeze_final_report() RETURNS trigger AS $$
BEGIN
  IF OLD.status = 'final' THEN
    -- After signing, only addenda and critical-finding acknowledgment may change.
    IF (to_jsonb(NEW) - 'addenda' - 'critical_ack_at' - 'critical_ack_by_id' - 'critical_read_back' - 'updated_at')
       IS DISTINCT FROM (to_jsonb(OLD) - 'addenda' - 'critical_ack_at' - 'critical_ack_by_id' - 'critical_read_back' - 'updated_at') THEN
      RAISE EXCEPTION 'signed imaging report % cannot be modified; add an addendum', OLD.id USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP FUNCTION IF EXISTS sandbox_purge_allows(text, jsonb);
"""


def upgrade() -> None:
    op.create_table(
        "demo_sandboxes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag", sa.String(length=12), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("root_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("visitor_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.String(length=20), nullable=True),
        sa.Column("build_seconds", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('building', 'ready', 'leased', 'releasing', 'purging', 'purged', 'failed')",
                           name="ck_demo_sandboxes_status"),
        sa.PrimaryKeyConstraint("id", name="pk_demo_sandboxes"),
        sa.UniqueConstraint("tag", name="uq_demo_sandboxes_tag"),
        sa.UniqueConstraint("organization_id", name="uq_demo_sandboxes_organization_id"),
        sa.UniqueConstraint("lease_id", name="uq_demo_sandboxes_lease_id"),
    )
    op.create_index(op.f("ix_demo_sandboxes_status"), "demo_sandboxes", ["status"])
    op.create_index(op.f("ix_demo_sandboxes_visitor_hash"), "demo_sandboxes", ["visitor_hash"])
    op.add_column("users", sa.Column("sandbox_org_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_users_sandbox_org_id_organizations", "users", "organizations", ["sandbox_org_id"], ["id"], ondelete="CASCADE")
    op.create_index(op.f("ix_users_sandbox_org_id"), "users", ["sandbox_org_id"])
    op.add_column("user_sessions", sa.Column("sandbox_lease_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_user_sessions_sandbox_lease_id"), "user_sessions", ["sandbox_lease_id"])
    op.execute(PURGE_FUNCTIONS)


def downgrade() -> None:
    op.execute(RESTORE_FUNCTIONS)
    op.drop_index(op.f("ix_user_sessions_sandbox_lease_id"), table_name="user_sessions")
    op.drop_column("user_sessions", "sandbox_lease_id")
    op.drop_index(op.f("ix_users_sandbox_org_id"), table_name="users")
    op.drop_constraint("fk_users_sandbox_org_id_organizations", "users", type_="foreignkey")
    op.drop_column("users", "sandbox_org_id")
    op.drop_index(op.f("ix_demo_sandboxes_visitor_hash"), table_name="demo_sandboxes")
    op.drop_index(op.f("ix_demo_sandboxes_status"), table_name="demo_sandboxes")
    op.drop_table("demo_sandboxes")
