"""revenue expansion

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-19 16:16:58.198638
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0021'
down_revision: str | None = '0020'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS prior_auth_seq START 7001")
    op.create_table('claim_findings',
    sa.Column('claim_id', sa.UUID(), nullable=False),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('severity', sa.String(length=8), nullable=False),
    sa.Column('message', sa.String(length=500), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('resolution_note', sa.String(length=300), nullable=True),
    sa.Column('resolved_by_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('model', sa.String(length=80), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("severity in ('blocker','warning','info')", name=op.f('ck_claim_findings_severity')),
    sa.CheckConstraint("source in ('rule','ai')", name=op.f('ck_claim_findings_source')),
    sa.CheckConstraint("status in ('open','resolved','dismissed')", name=op.f('ck_claim_findings_status')),
    sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], name=op.f('fk_claim_findings_claim_id_claims'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_claim_findings_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['resolved_by_id'], ['users.id'], name=op.f('fk_claim_findings_resolved_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_claim_findings'))
    )
    op.create_index(op.f('ix_claim_findings_claim_id'), 'claim_findings', ['claim_id'], unique=False)
    op.create_index(op.f('ix_claim_findings_organization_id'), 'claim_findings', ['organization_id'], unique=False)
    op.create_table('prior_authorizations',
    sa.Column('number', sa.BigInteger(), server_default=sa.text("nextval('prior_auth_seq')"), nullable=False),
    sa.Column('patient_id', sa.UUID(), nullable=False),
    sa.Column('insurance_id', sa.UUID(), nullable=True),
    sa.Column('order_id', sa.UUID(), nullable=True),
    sa.Column('service_code', sa.String(length=10), nullable=False),
    sa.Column('service_description', sa.String(length=200), nullable=False),
    sa.Column('payer_name', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('checklist', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('clinical_summary', sa.Text(), nullable=True),
    sa.Column('auth_number', sa.String(length=40), nullable=True),
    sa.Column('units_approved', sa.Integer(), nullable=True),
    sa.Column('valid_from', sa.Date(), nullable=True),
    sa.Column('valid_to', sa.Date(), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('denial_reason', sa.String(length=300), nullable=True),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('channel', sa.String(length=12), nullable=False),
    sa.Column('created_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("status <> 'approved' or (auth_number is not null and valid_from is not null and valid_to is not null)", name=op.f('ck_prior_authorizations_approved_complete')),
    sa.CheckConstraint("status in ('draft','submitted','pended','approved','denied','expired','cancelled')", name=op.f('ck_prior_authorizations_status')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_prior_authorizations_created_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['insurance_id'], ['patient_insurances.id'], name=op.f('fk_prior_authorizations_insurance_id_patient_insurances'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_prior_authorizations_order_id_orders'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_prior_authorizations_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_prior_authorizations_patient_id_patients'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_prior_authorizations'))
    )
    op.create_index('ix_pa_org_status', 'prior_authorizations', ['organization_id', 'status'], unique=False)
    op.create_index(op.f('ix_prior_authorizations_order_id'), 'prior_authorizations', ['order_id'], unique=False)
    op.create_index(op.f('ix_prior_authorizations_organization_id'), 'prior_authorizations', ['organization_id'], unique=False)
    op.create_index(op.f('ix_prior_authorizations_patient_id'), 'prior_authorizations', ['patient_id'], unique=False)
    op.create_index('uq_pa_active_order', 'prior_authorizations', ['order_id'], unique=True, postgresql_where=sa.text("order_id is not null and status not in ('denied','expired','cancelled')"))
    from app.core.rls import enable_rls_all

    enable_rls_all(op)


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('uq_pa_active_order', table_name='prior_authorizations', postgresql_where=sa.text("order_id is not null and status not in ('denied','expired','cancelled')"))
    op.drop_index(op.f('ix_prior_authorizations_patient_id'), table_name='prior_authorizations')
    op.drop_index(op.f('ix_prior_authorizations_organization_id'), table_name='prior_authorizations')
    op.drop_index(op.f('ix_prior_authorizations_order_id'), table_name='prior_authorizations')
    op.drop_index('ix_pa_org_status', table_name='prior_authorizations')
    op.drop_table('prior_authorizations')
    op.drop_index(op.f('ix_claim_findings_organization_id'), table_name='claim_findings')
    op.drop_index(op.f('ix_claim_findings_claim_id'), table_name='claim_findings')
    op.drop_table('claim_findings')
    op.execute("DROP SEQUENCE IF EXISTS prior_auth_seq")
    # ### end Alembic commands ###
