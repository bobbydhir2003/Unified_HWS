"""laboratory

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-19 16:07:34.799284
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0019'
down_revision: str | None = '0018'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS accession_seq START 2600001")
    op.create_table('specimens',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('patient_id', sa.UUID(), nullable=False),
    sa.Column('accession_number', sa.BigInteger(), server_default=sa.text("nextval('accession_seq')"), nullable=False),
    sa.Column('specimen_type', sa.String(length=30), nullable=False),
    sa.Column('container', sa.String(length=40), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('collected_by_id', sa.UUID(), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('received_by_id', sa.UUID(), nullable=True),
    sa.Column('rejected_reason', sa.String(length=200), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("status <> 'rejected' or rejected_reason is not null", name=op.f('ck_specimens_rejected_reason')),
    sa.CheckConstraint("status in ('collected','received','in_process','resulted','rejected')", name=op.f('ck_specimens_status')),
    sa.ForeignKeyConstraint(['collected_by_id'], ['users.id'], name=op.f('fk_specimens_collected_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_specimens_order_id_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_specimens_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_specimens_patient_id_patients'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['received_by_id'], ['users.id'], name=op.f('fk_specimens_received_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_specimens')),
    sa.UniqueConstraint('accession_number', name=op.f('uq_specimens_accession_number'))
    )
    op.create_index(op.f('ix_specimens_order_id'), 'specimens', ['order_id'], unique=False)
    op.create_index(op.f('ix_specimens_organization_id'), 'specimens', ['organization_id'], unique=False)
    op.create_index(op.f('ix_specimens_patient_id'), 'specimens', ['patient_id'], unique=False)
    op.create_index('uq_specimen_active_order', 'specimens', ['order_id'], unique=True, postgresql_where=sa.text("status <> 'rejected'"))
    op.create_table('critical_result_alerts',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('result_id', sa.UUID(), nullable=False),
    sa.Column('patient_id', sa.UUID(), nullable=False),
    sa.Column('clinician_user_id', sa.UUID(), nullable=True),
    sa.Column('summary', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('acknowledged_by_id', sa.UUID(), nullable=True),
    sa.Column('read_back', sa.Text(), nullable=True),
    sa.Column('case_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['acknowledged_by_id'], ['users.id'], name=op.f('fk_critical_result_alerts_acknowledged_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_critical_result_alerts_case_id_cases'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['clinician_user_id'], ['users.id'], name=op.f('fk_critical_result_alerts_clinician_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_critical_result_alerts_order_id_orders'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_critical_result_alerts_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_critical_result_alerts_patient_id_patients'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['result_id'], ['lab_results.id'], name=op.f('fk_critical_result_alerts_result_id_lab_results'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_critical_result_alerts'))
    )
    op.create_index(op.f('ix_critical_result_alerts_order_id'), 'critical_result_alerts', ['order_id'], unique=False)
    op.create_index(op.f('ix_critical_result_alerts_organization_id'), 'critical_result_alerts', ['organization_id'], unique=False)
    op.create_index(op.f('ix_critical_result_alerts_patient_id'), 'critical_result_alerts', ['patient_id'], unique=False)
    op.create_index(op.f('ix_critical_result_alerts_result_id'), 'critical_result_alerts', ['result_id'], unique=False)
    op.add_column('lab_results', sa.Column('entered_by_id', sa.UUID(), nullable=True))
    op.add_column('lab_results', sa.Column('verified_by_id', sa.UUID(), nullable=True))
    op.add_column('lab_results', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('lab_results', sa.Column('supersedes_id', sa.UUID(), nullable=True))
    op.add_column('lab_results', sa.Column('correction_reason', sa.String(length=300), nullable=True))
    op.add_column('lab_results', sa.Column('specimen_id', sa.UUID(), nullable=True))
    op.create_foreign_key(op.f('fk_lab_results_entered_by_id_users'), 'lab_results', 'users', ['entered_by_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_lab_results_supersedes_id_lab_results'), 'lab_results', 'lab_results', ['supersedes_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_lab_results_specimen_id_specimens'), 'lab_results', 'specimens', ['specimen_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_lab_results_verified_by_id_users'), 'lab_results', 'users', ['verified_by_id'], ['id'], ondelete='SET NULL')
    from app.core.rls import enable_rls_all

    enable_rls_all(op)


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(op.f('fk_lab_results_verified_by_id_users'), 'lab_results', type_='foreignkey')
    op.drop_constraint(op.f('fk_lab_results_specimen_id_specimens'), 'lab_results', type_='foreignkey')
    op.drop_constraint(op.f('fk_lab_results_supersedes_id_lab_results'), 'lab_results', type_='foreignkey')
    op.drop_constraint(op.f('fk_lab_results_entered_by_id_users'), 'lab_results', type_='foreignkey')
    op.drop_column('lab_results', 'specimen_id')
    op.drop_column('lab_results', 'correction_reason')
    op.drop_column('lab_results', 'supersedes_id')
    op.drop_column('lab_results', 'verified_at')
    op.drop_column('lab_results', 'verified_by_id')
    op.drop_column('lab_results', 'entered_by_id')
    op.drop_index(op.f('ix_critical_result_alerts_result_id'), table_name='critical_result_alerts')
    op.drop_index(op.f('ix_critical_result_alerts_patient_id'), table_name='critical_result_alerts')
    op.drop_index(op.f('ix_critical_result_alerts_organization_id'), table_name='critical_result_alerts')
    op.drop_index(op.f('ix_critical_result_alerts_order_id'), table_name='critical_result_alerts')
    op.drop_table('critical_result_alerts')
    op.drop_index('uq_specimen_active_order', table_name='specimens', postgresql_where=sa.text("status <> 'rejected'"))
    op.drop_index(op.f('ix_specimens_patient_id'), table_name='specimens')
    op.drop_index(op.f('ix_specimens_organization_id'), table_name='specimens')
    op.drop_index(op.f('ix_specimens_order_id'), table_name='specimens')
    op.drop_table('specimens')
    op.execute("DROP SEQUENCE IF EXISTS accession_seq")
    # ### end Alembic commands ###
