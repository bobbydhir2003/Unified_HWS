"""Nursing documentation: flowsheet observations (append-only), assessments (signed = frozen), care plans.

Revision ID: 0034
Revises: 0033
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import enable_rls_all

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

U = postgresql.UUID(as_uuid=True)


def _base(name):
    return [sa.Column("id", U, primary_key=True),
            sa.Column("organization_id", U, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("patient_id", U, sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("stay_id", U, sa.ForeignKey("inpatient_stays.id", ondelete="SET NULL"), index=True)]


def upgrade() -> None:
    op.create_table(
        "nursing_observations", *_base("nursing_observations"),
        sa.Column("row_key", sa.String(40), nullable=False),
        sa.Column("value_num", sa.Numeric(10, 2)),
        sa.Column("value_text", sa.String(300)),
        sa.Column("unit", sa.String(20)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by_id", U, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("supersedes_id", U, sa.ForeignKey("nursing_observations.id")),
        sa.Column("correction_reason", sa.String(300)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("value_num IS NOT NULL OR value_text IS NOT NULL", name="ck_nursing_observations_has_value"),
    )
    op.create_index("ix_nursing_obs_patient_time", "nursing_observations", ["patient_id", "observed_at"])
    op.create_table(
        "nursing_assessments", *_base("nursing_assessments"),
        sa.Column("template_key", sa.String(40), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column("author_id", U, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("signed_by_id", U, sa.ForeignKey("users.id")),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.Column("amends_id", U, sa.ForeignKey("nursing_assessments.id")),
        sa.Column("amendment_reason", sa.String(300)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('draft','signed','amended')", name="ck_nursing_assessments_status"),
        sa.CheckConstraint("status = 'draft' OR signed_by_id IS NOT NULL", name="ck_nursing_assessments_signed_has_signer"),
    )
    op.create_table(
        "nursing_care_plans", *_base("nursing_care_plans"),
        sa.Column("problem", sa.String(300), nullable=False),
        sa.Column("goal", sa.String(500), nullable=False),
        sa.Column("interventions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("responsible_role", sa.String(40)),
        sa.Column("status", sa.String(12), nullable=False, server_default="active"),
        sa.Column("review_due_at", sa.DateTime(timezone=True)),
        sa.Column("progress", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_by_id", U, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('active','met','not_met','discontinued')", name="ck_nursing_care_plans_status"),
    )
    op.execute("CREATE TRIGGER nursing_observations_append_only BEFORE UPDATE OR DELETE ON nursing_observations "
               "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()")
    # A signed assessment is frozen except for the single transition signed -> amended (when its amendment is signed).
    op.execute("""
CREATE OR REPLACE FUNCTION freeze_signed_assessment() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' AND OLD.status <> 'draft' THEN
    RAISE EXCEPTION 'signed nursing assessments cannot be deleted' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.status <> 'draft' AND NOT (OLD.status = 'signed' AND NEW.status = 'amended'
      AND (to_jsonb(NEW) - 'status' - 'updated_at') = (to_jsonb(OLD) - 'status' - 'updated_at')) THEN
    RAISE EXCEPTION 'signed nursing assessments are frozen; create an amendment' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$ LANGUAGE plpgsql""")
    op.execute("CREATE TRIGGER nursing_assessments_freeze BEFORE UPDATE OR DELETE ON nursing_assessments "
               "FOR EACH ROW EXECUTE FUNCTION freeze_signed_assessment()")
    enable_rls_all(op)


def downgrade() -> None:
    op.drop_table("nursing_care_plans")
    op.drop_table("nursing_assessments")
    op.execute("DROP FUNCTION IF EXISTS freeze_signed_assessment")
    op.drop_table("nursing_observations")
