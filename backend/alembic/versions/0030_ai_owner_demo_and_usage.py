"""Owner-managed demo AI policy, agent run trigger/source, durable AI usage counters (additive only).

Revision ID: 0030
Revises: 0029
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ai_provider_settings", sa.Column("policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"))
    op.add_column("agent_runs", sa.Column("trigger", sa.String(length=30), nullable=False, server_default="manual"))
    op.add_column("agent_runs", sa.Column("ai_source", sa.String(length=20), nullable=True))
    op.create_table(
        "ai_usage_counters",
        sa.Column("key", sa.String(length=160), primary_key=True),
        sa.Column("requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(14, 6), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ai_usage_counters")
    op.drop_column("agent_runs", "ai_source")
    op.drop_column("agent_runs", "trigger")
    op.drop_column("ai_provider_settings", "policy")
