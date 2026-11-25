"""HMS Voice Concierge: call mode (test/live), facility, verification state, outcome code, end reason, linked records and
the tool/action event log on voice_calls. Existing calls keep their data (defaults: test, unverified, empty lists).

Revision ID: 0037
Revises: 0036
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("voice_calls", sa.Column("mode", sa.String(10), nullable=False, server_default="test"))
    op.add_column("voice_calls", sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="SET NULL"), nullable=True))
    op.add_column("voice_calls", sa.Column("verification", sa.String(20), nullable=False, server_default="unverified"))
    op.add_column("voice_calls", sa.Column("outcome_code", sa.String(30), nullable=True))
    op.add_column("voice_calls", sa.Column("end_reason", sa.String(60), nullable=True))
    op.add_column("voice_calls", sa.Column("records", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("voice_calls", sa.Column("events", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.execute("UPDATE voice_calls SET verification = 'verified' WHERE verified_patient_id IS NOT NULL")


def downgrade() -> None:
    for col in ("events", "records", "end_reason", "outcome_code", "verification", "clinic_id", "mode"):
        op.drop_column("voice_calls", col)
