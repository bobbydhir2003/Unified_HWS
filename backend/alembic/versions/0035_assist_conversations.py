"""HMS Assist conversations: conversations, append-only messages, confirm-in-chat drafts; approval/agent-run provenance.

All changes are additive (new tables, nullable columns, one partial unique index), so the downgrade is a clean drop.

Revision ID: 0035
Revises: 0034
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import enable_rls_all

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

U = postgresql.UUID(as_uuid=True)
J = postgresql.JSONB()


def _org():
    return sa.Column("organization_id", U, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


def upgrade() -> None:
    op.create_table(
        "assist_conversations",
        sa.Column("id", U, primary_key=True), _org(),
        sa.Column("user_id", U, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("agent_key", sa.String(40), nullable=False),
        sa.Column("agent_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("acting_role", sa.String(30)),
        sa.Column("context_type", sa.String(30), nullable=False, server_default="workspace"),
        sa.Column("context_id", sa.String(80)),
        sa.Column("context_label", sa.String(250)),
        sa.Column("patient_id", U, sa.ForeignKey("patients.id", ondelete="SET NULL"), index=True),
        sa.Column("facility_id", U, sa.ForeignKey("clinics.id", ondelete="SET NULL")),
        sa.Column("case_id", U, sa.ForeignKey("cases.id", ondelete="SET NULL"), index=True),
        sa.Column("title", sa.String(200)),
        sa.Column("status", sa.String(12), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("status in ('active','closed','expired')", name="ck_assist_conversations_status"),
    )
    op.create_index("ix_assist_conv_user", "assist_conversations", ["organization_id", "user_id", "last_message_at"])
    op.create_index("ix_assist_conv_context", "assist_conversations", ["organization_id", "context_type", "context_id"])

    op.create_table(
        "assist_messages",
        sa.Column("id", U, primary_key=True), _org(),
        sa.Column("conversation_id", U, sa.ForeignKey("assist_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("agent_run_id", U, sa.ForeignKey("agent_runs.id", ondelete="SET NULL")),
        sa.Column("mode", sa.String(12)),
        sa.Column("citations", J, nullable=False, server_default="[]"),
        sa.Column("actions", J, nullable=False, server_default="[]"),
        sa.Column("tool_activity", J, nullable=False, server_default="[]"),
        sa.Column("error", sa.String(400)),
        sa.Column("redacted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_assist_messages_conversation_id"),
        sa.CheckConstraint("role in ('user','assistant','system')", name="ck_assist_messages_role"),
    )
    # Messages are never edited. The only permitted update is retention redaction (content cleared, redacted=true).
    op.execute("""
CREATE OR REPLACE FUNCTION assist_messages_guard() RETURNS trigger AS $$
BEGIN
  IF NOT (NEW.redacted AND NOT OLD.redacted AND NEW.id = OLD.id AND NEW.conversation_id = OLD.conversation_id
          AND NEW.seq = OLD.seq AND NEW.role = OLD.role AND NEW.created_at = OLD.created_at) THEN
    RAISE EXCEPTION 'assist messages are append-only (only retention redaction is allowed)' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql""")
    op.execute("CREATE TRIGGER assist_messages_append_only BEFORE UPDATE ON assist_messages FOR EACH ROW EXECUTE FUNCTION assist_messages_guard()")

    op.create_table(
        "assist_action_drafts",
        sa.Column("id", U, primary_key=True), _org(),
        sa.Column("conversation_id", U, sa.ForeignKey("assist_conversations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("payload", J, nullable=False, server_default="{}"),
        sa.Column("required_permission", sa.String(40), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("result", J, nullable=False, server_default="{}"),
        sa.Column("error", sa.Text()),
        sa.Column("created_by_agent", sa.String(40), nullable=False),
        sa.Column("confirmed_by_id", U, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status in ('draft','confirmed','discarded','failed','expired')", name="ck_assist_action_drafts_status"),
    )

    op.add_column("approval_requests", sa.Column("conversation_id", U, sa.ForeignKey("assist_conversations.id", ondelete="SET NULL")))
    op.add_column("approval_requests", sa.Column("agent_run_id", U, sa.ForeignKey("agent_runs.id", ondelete="SET NULL")))
    op.add_column("approval_requests", sa.Column("dedupe_key", sa.String(200)))
    op.create_index("uq_approvals_pending_dedupe", "approval_requests", ["organization_id", "dedupe_key"], unique=True,
                    postgresql_where=sa.text("status = 'pending' AND dedupe_key IS NOT NULL"))
    op.add_column("agent_runs", sa.Column("conversation_id", U))
    op.add_column("agent_runs", sa.Column("context_type", sa.String(30)))
    op.add_column("agent_runs", sa.Column("context_id", sa.String(80)))
    op.create_index("ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"])
    enable_rls_all(op)


def downgrade() -> None:
    op.drop_index("ix_agent_runs_conversation_id", table_name="agent_runs")
    for c in ("context_id", "context_type", "conversation_id"):
        op.drop_column("agent_runs", c)
    op.drop_index("uq_approvals_pending_dedupe", table_name="approval_requests")
    for c in ("dedupe_key", "agent_run_id", "conversation_id"):
        op.drop_column("approval_requests", c)
    op.drop_table("assist_action_drafts")
    op.drop_table("assist_messages")
    op.execute("DROP FUNCTION IF EXISTS assist_messages_guard")
    op.drop_table("assist_conversations")
