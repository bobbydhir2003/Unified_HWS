"""Terminology releases/concepts (ICD-10-CM FY2026, public domain) and versioned order sets.

Revision ID: 0033
Revises: 0032
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import enable_rls_all

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "terminology_releases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("system", sa.String(30), nullable=False),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column("license_note", sa.String(300), nullable=False),
        sa.Column("concept_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("system", "version", name="uq_terminology_releases_system"),
    )
    op.create_table(
        "terminology_concepts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("system", sa.String(30), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("display", sa.String(400), nullable=False),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.UniqueConstraint("system", "code", name="uq_terminology_concepts_system"),
        sa.CheckConstraint("status in ('active','retired')", name="ck_terminology_concepts_status"),
    )
    op.execute("CREATE INDEX ix_terminology_display ON terminology_concepts (system, lower(display))")
    op.create_table(
        "order_sets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(60)),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column("is_demonstration", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("published_by_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "key", "version", name="uq_order_sets_organization_id"),
        sa.CheckConstraint("status in ('draft','published','retired')", name="ck_order_sets_status"),
    )
    op.create_table(
        "order_set_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("order_set_id", UUID, sa.ForeignKey("order_sets.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="routine"),
        sa.Column("default_selected", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("note", sa.String(300)),
    )
    from app.services.terminology import load_icd10cm

    load_icd10cm(op.get_bind())
    enable_rls_all(op)


def downgrade() -> None:
    op.drop_table("order_set_items")
    op.drop_table("order_sets")
    op.drop_table("terminology_concepts")
    op.drop_table("terminology_releases")
