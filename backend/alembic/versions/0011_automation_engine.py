"""automation engine

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-19 14:57:57.794488
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS case_number_seq START 1001")
    op.create_table('domain_events',
    sa.Column('event_type', sa.String(length=60), nullable=False),
    sa.Column('subject_type', sa.String(length=40), nullable=True),
    sa.Column('subject_id', sa.String(length=64), nullable=True),
    sa.Column('patient_id', sa.UUID(), nullable=True),
    sa.Column('facility_id', sa.UUID(), nullable=True),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("status in ('pending','done','dead')", name=op.f('ck_domain_events_status')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_domain_events_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_domain_events'))
    )
    op.create_index(op.f('ix_domain_events_event_type'), 'domain_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_domain_events_organization_id'), 'domain_events', ['organization_id'], unique=False)
    op.create_index('ix_domain_events_pending', 'domain_events', ['next_attempt_at'], unique=False, postgresql_where=sa.text("status = 'pending'"))
    op.create_table('monitor_runs',
    sa.Column('monitor_key', sa.String(length=60), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('found', sa.Integer(), nullable=False),
    sa.Column('opened', sa.Integer(), nullable=False),
    sa.Column('updated', sa.Integer(), nullable=False),
    sa.Column('closed', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("status in ('running','succeeded','failed')", name=op.f('ck_monitor_runs_status')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_monitor_runs_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_monitor_runs'))
    )
    op.create_index('ix_monitor_runs_key_time', 'monitor_runs', ['organization_id', 'monitor_key', 'started_at'], unique=False)
    op.create_index(op.f('ix_monitor_runs_organization_id'), 'monitor_runs', ['organization_id'], unique=False)
    op.create_table('event_handlings',
    sa.Column('event_id', sa.UUID(), nullable=False),
    sa.Column('handler', sa.String(length=60), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint("status in ('done','failed')", name=op.f('ck_event_handlings_status')),
    sa.ForeignKeyConstraint(['event_id'], ['domain_events.id'], name=op.f('fk_event_handlings_event_id_domain_events'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_event_handlings')),
    sa.UniqueConstraint('event_id', 'handler', name=op.f('uq_event_handlings_event_id'))
    )
    op.create_index(op.f('ix_event_handlings_event_id'), 'event_handlings', ['event_id'], unique=False)
    op.create_table('monitor_configs',
    sa.Column('facility_id', sa.UUID(), nullable=True),
    sa.Column('monitor_key', sa.String(length=60), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('updated_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['facility_id'], ['clinics.id'], name=op.f('fk_monitor_configs_facility_id_clinics'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_monitor_configs_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], name=op.f('fk_monitor_configs_updated_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_monitor_configs')),
    sa.UniqueConstraint('organization_id', 'facility_id', 'monitor_key', name=op.f('uq_monitor_configs_organization_id'), postgresql_nulls_not_distinct=True)
    )
    op.create_index(op.f('ix_monitor_configs_facility_id'), 'monitor_configs', ['facility_id'], unique=False)
    op.create_index(op.f('ix_monitor_configs_organization_id'), 'monitor_configs', ['organization_id'], unique=False)
    op.create_table('cases',
    sa.Column('number', sa.Integer(), server_default=sa.text("nextval('case_number_seq')"), nullable=False),
    sa.Column('facility_id', sa.UUID(), nullable=True),
    sa.Column('department_id', sa.UUID(), nullable=True),
    sa.Column('category', sa.String(length=20), nullable=False),
    sa.Column('kind', sa.String(length=60), nullable=False),
    sa.Column('dedupe_key', sa.String(length=200), nullable=False),
    sa.Column('title', sa.String(length=250), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('severity', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('patient_id', sa.UUID(), nullable=True),
    sa.Column('subject_type', sa.String(length=40), nullable=True),
    sa.Column('subject_id', sa.String(length=64), nullable=True),
    sa.Column('link', sa.String(length=300), nullable=True),
    sa.Column('assigned_role', sa.String(length=30), nullable=True),
    sa.Column('assigned_user_id', sa.UUID(), nullable=True),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('escalation_level', sa.Integer(), nullable=False),
    sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('snoozed_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('snooze_reason', sa.String(length=300), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_by_id', sa.UUID(), nullable=True),
    sa.Column('resolution_code', sa.String(length=40), nullable=True),
    sa.Column('resolution', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=10), nullable=False),
    sa.Column('rule_key', sa.String(length=60), nullable=True),
    sa.Column('rule_version', sa.Integer(), nullable=True),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('first_detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("category in ('insurance','scheduling','clinical','lab','radiology','pharmacy','inventory','bed','ed','discharge','billing','staffing','or','equipment','patient_followup','documents','operations','automation')", name=op.f('ck_cases_category')),
    sa.CheckConstraint("severity in ('info','low','medium','high','critical')", name=op.f('ck_cases_severity')),
    sa.CheckConstraint("source in ('monitor','event','manual','agent')", name=op.f('ck_cases_source')),
    sa.CheckConstraint("status <> 'snoozed' or (snoozed_until is not null and snooze_reason is not null)", name=op.f('ck_cases_snooze_reason')),
    sa.CheckConstraint("status in ('open','in_progress','waiting','snoozed','escalated','resolved','cancelled')", name=op.f('ck_cases_status')),
    sa.ForeignKeyConstraint(['assigned_user_id'], ['users.id'], name=op.f('fk_cases_assigned_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name=op.f('fk_cases_department_id_departments'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['facility_id'], ['clinics.id'], name=op.f('fk_cases_facility_id_clinics'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_cases_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_cases_patient_id_patients'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['resolved_by_id'], ['users.id'], name=op.f('fk_cases_resolved_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_cases'))
    )
    op.create_index(op.f('ix_cases_assigned_user_id'), 'cases', ['assigned_user_id'], unique=False)
    op.create_index(op.f('ix_cases_department_id'), 'cases', ['department_id'], unique=False)
    op.create_index('ix_cases_due', 'cases', ['due_at'], unique=False, postgresql_where=sa.text("status in ('open','in_progress','escalated')"))
    op.create_index(op.f('ix_cases_facility_id'), 'cases', ['facility_id'], unique=False)
    op.create_index('ix_cases_org_role', 'cases', ['organization_id', 'assigned_role', 'status'], unique=False)
    op.create_index('ix_cases_org_status_cat', 'cases', ['organization_id', 'status', 'category'], unique=False)
    op.create_index(op.f('ix_cases_organization_id'), 'cases', ['organization_id'], unique=False)
    op.create_index(op.f('ix_cases_patient_id'), 'cases', ['patient_id'], unique=False)
    op.create_index(op.f('ix_cases_resolved_by_id'), 'cases', ['resolved_by_id'], unique=False)
    op.create_index('ix_cases_rule', 'cases', ['organization_id', 'rule_key', 'status'], unique=False)
    op.create_index('uq_cases_open_dedupe', 'cases', ['organization_id', 'dedupe_key'], unique=True, postgresql_where=sa.text("status in ('open','in_progress','waiting','snoozed','escalated')"))
    op.create_table('notification_preferences',
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('patient_id', sa.UUID(), nullable=True),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('in_app', sa.Boolean(), nullable=False),
    sa.Column('email', sa.Boolean(), nullable=False),
    sa.Column('sms', sa.Boolean(), nullable=False),
    sa.Column('portal', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint('(user_id is null) <> (patient_id is null)', name=op.f('ck_notification_preferences_one_owner')),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_notification_preferences_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_notification_preferences_patient_id_patients'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notification_preferences_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notification_preferences')),
    sa.UniqueConstraint('organization_id', 'user_id', 'patient_id', 'category', name=op.f('uq_notification_preferences_organization_id'), postgresql_nulls_not_distinct=True)
    )
    op.create_index(op.f('ix_notification_preferences_organization_id'), 'notification_preferences', ['organization_id'], unique=False)
    op.create_index(op.f('ix_notification_preferences_patient_id'), 'notification_preferences', ['patient_id'], unique=False)
    op.create_index(op.f('ix_notification_preferences_user_id'), 'notification_preferences', ['user_id'], unique=False)
    op.create_table('approval_requests',
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=250), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('case_id', sa.UUID(), nullable=True),
    sa.Column('patient_id', sa.UUID(), nullable=True),
    sa.Column('facility_id', sa.UUID(), nullable=True),
    sa.Column('requested_by_user_id', sa.UUID(), nullable=True),
    sa.Column('requested_by_agent', sa.String(length=60), nullable=True),
    sa.Column('required_permission', sa.String(length=40), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('decided_by_id', sa.UUID(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_note', sa.String(length=500), nullable=True),
    sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("status in ('pending','approved','rejected','executed','failed','expired')", name=op.f('ck_approval_requests_status')),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_approval_requests_case_id_cases'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['decided_by_id'], ['users.id'], name=op.f('fk_approval_requests_decided_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['facility_id'], ['clinics.id'], name=op.f('fk_approval_requests_facility_id_clinics'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_approval_requests_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], name=op.f('fk_approval_requests_patient_id_patients'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], name=op.f('fk_approval_requests_requested_by_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_approval_requests'))
    )
    op.create_index(op.f('ix_approval_requests_case_id'), 'approval_requests', ['case_id'], unique=False)
    op.create_index(op.f('ix_approval_requests_organization_id'), 'approval_requests', ['organization_id'], unique=False)
    op.create_index(op.f('ix_approval_requests_patient_id'), 'approval_requests', ['patient_id'], unique=False)
    op.create_index('ix_approvals_org_status', 'approval_requests', ['organization_id', 'status', 'created_at'], unique=False)
    op.create_table('case_events',
    sa.Column('case_id', sa.UUID(), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actor_id', sa.UUID(), nullable=True),
    sa.Column('actor_kind', sa.String(length=10), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('message', sa.String(length=500), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("actor_kind in ('user','system','agent')", name=op.f('ck_case_events_actor_kind')),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_case_events_actor_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_case_events_case_id_cases'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_case_events_organization_id_organizations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_case_events'))
    )
    op.create_index(op.f('ix_case_events_case_id'), 'case_events', ['case_id'], unique=False)
    op.create_index(op.f('ix_case_events_organization_id'), 'case_events', ['organization_id'], unique=False)
    op.create_table('notification_deliveries',
    sa.Column('case_id', sa.UUID(), nullable=True),
    sa.Column('channel', sa.String(length=10), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('recipient_user_id', sa.UUID(), nullable=True),
    sa.Column('recipient_patient_id', sa.UUID(), nullable=True),
    sa.Column('address', sa.String(length=320), nullable=True),
    sa.Column('subject', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('link', sa.String(length=300), nullable=True),
    sa.Column('dedupe_key', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('status_reason', sa.String(length=200), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.CheckConstraint("channel in ('in_app','email','sms','portal')", name=op.f('ck_notification_deliveries_channel')),
    sa.CheckConstraint("status in ('queued','sent','simulated','failed','suppressed')", name=op.f('ck_notification_deliveries_status')),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], name=op.f('fk_notification_deliveries_case_id_cases'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name=op.f('fk_notification_deliveries_organization_id_organizations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recipient_patient_id'], ['patients.id'], name=op.f('fk_notification_deliveries_recipient_patient_id_patients'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['recipient_user_id'], ['users.id'], name=op.f('fk_notification_deliveries_recipient_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notification_deliveries')),
    sa.UniqueConstraint('organization_id', 'dedupe_key', name=op.f('uq_notification_deliveries_organization_id'))
    )
    op.create_index(op.f('ix_notification_deliveries_case_id'), 'notification_deliveries', ['case_id'], unique=False)
    op.create_index(op.f('ix_notification_deliveries_created_at'), 'notification_deliveries', ['created_at'], unique=False)
    op.create_index(op.f('ix_notification_deliveries_organization_id'), 'notification_deliveries', ['organization_id'], unique=False)
    op.create_index(op.f('ix_notification_deliveries_recipient_patient_id'), 'notification_deliveries', ['recipient_patient_id'], unique=False)
    op.create_index(op.f('ix_notification_deliveries_recipient_user_id'), 'notification_deliveries', ['recipient_user_id'], unique=False)
    op.add_column('tasks', sa.Column('case_id', sa.UUID(), nullable=True))
    op.add_column('tasks', sa.Column('dedupe_key', sa.String(length=200), nullable=True))
    op.add_column('tasks', sa.Column('due_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tasks', sa.Column('facility_id', sa.UUID(), nullable=True))
    op.add_column('tasks', sa.Column('department_id', sa.UUID(), nullable=True))
    op.add_column('tasks', sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tasks', sa.Column('acknowledged_by_id', sa.UUID(), nullable=True))
    op.add_column('tasks', sa.Column('kind', sa.String(length=60), nullable=True))
    op.create_index(op.f('ix_tasks_case_id'), 'tasks', ['case_id'], unique=False)
    op.create_index(op.f('ix_tasks_department_id'), 'tasks', ['department_id'], unique=False)
    op.create_index('uq_tasks_open_dedupe', 'tasks', ['organization_id', 'dedupe_key'], unique=True, postgresql_where=sa.text("status in ('open','in_progress') and dedupe_key is not null"))
    op.create_foreign_key(op.f('fk_tasks_facility_id_clinics'), 'tasks', 'clinics', ['facility_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_tasks_department_id_departments'), 'tasks', 'departments', ['department_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_tasks_acknowledged_by_id_users'), 'tasks', 'users', ['acknowledged_by_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_tasks_case_id_cases'), 'tasks', 'cases', ['case_id'], ['id'], ondelete='SET NULL')
    op.execute("CREATE TRIGGER case_events_append_only BEFORE UPDATE OR DELETE ON case_events FOR EACH ROW EXECUTE FUNCTION forbid_mutation()")
    from app.core.rls import enable_rls_all

    enable_rls_all(op)


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(op.f('fk_tasks_case_id_cases'), 'tasks', type_='foreignkey')
    op.drop_constraint(op.f('fk_tasks_acknowledged_by_id_users'), 'tasks', type_='foreignkey')
    op.drop_constraint(op.f('fk_tasks_department_id_departments'), 'tasks', type_='foreignkey')
    op.drop_constraint(op.f('fk_tasks_facility_id_clinics'), 'tasks', type_='foreignkey')
    op.drop_index('uq_tasks_open_dedupe', table_name='tasks', postgresql_where=sa.text("status in ('open','in_progress') and dedupe_key is not null"))
    op.drop_index(op.f('ix_tasks_department_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_case_id'), table_name='tasks')
    op.drop_column('tasks', 'kind')
    op.drop_column('tasks', 'acknowledged_by_id')
    op.drop_column('tasks', 'acknowledged_at')
    op.drop_column('tasks', 'department_id')
    op.drop_column('tasks', 'facility_id')
    op.drop_column('tasks', 'due_at')
    op.drop_column('tasks', 'dedupe_key')
    op.drop_column('tasks', 'case_id')
    op.drop_index(op.f('ix_notification_deliveries_recipient_user_id'), table_name='notification_deliveries')
    op.drop_index(op.f('ix_notification_deliveries_recipient_patient_id'), table_name='notification_deliveries')
    op.drop_index(op.f('ix_notification_deliveries_organization_id'), table_name='notification_deliveries')
    op.drop_index(op.f('ix_notification_deliveries_created_at'), table_name='notification_deliveries')
    op.drop_index(op.f('ix_notification_deliveries_case_id'), table_name='notification_deliveries')
    op.drop_table('notification_deliveries')
    op.drop_index(op.f('ix_case_events_organization_id'), table_name='case_events')
    op.drop_index(op.f('ix_case_events_case_id'), table_name='case_events')
    op.drop_table('case_events')
    op.drop_index('ix_approvals_org_status', table_name='approval_requests')
    op.drop_index(op.f('ix_approval_requests_patient_id'), table_name='approval_requests')
    op.drop_index(op.f('ix_approval_requests_organization_id'), table_name='approval_requests')
    op.drop_index(op.f('ix_approval_requests_case_id'), table_name='approval_requests')
    op.drop_table('approval_requests')
    op.drop_index(op.f('ix_notification_preferences_user_id'), table_name='notification_preferences')
    op.drop_index(op.f('ix_notification_preferences_patient_id'), table_name='notification_preferences')
    op.drop_index(op.f('ix_notification_preferences_organization_id'), table_name='notification_preferences')
    op.drop_table('notification_preferences')
    op.drop_index('uq_cases_open_dedupe', table_name='cases', postgresql_where=sa.text("status in ('open','in_progress','waiting','snoozed','escalated')"))
    op.drop_index('ix_cases_rule', table_name='cases')
    op.drop_index(op.f('ix_cases_resolved_by_id'), table_name='cases')
    op.drop_index(op.f('ix_cases_patient_id'), table_name='cases')
    op.drop_index(op.f('ix_cases_organization_id'), table_name='cases')
    op.drop_index('ix_cases_org_status_cat', table_name='cases')
    op.drop_index('ix_cases_org_role', table_name='cases')
    op.drop_index(op.f('ix_cases_facility_id'), table_name='cases')
    op.drop_index('ix_cases_due', table_name='cases', postgresql_where=sa.text("status in ('open','in_progress','escalated')"))
    op.drop_index(op.f('ix_cases_department_id'), table_name='cases')
    op.drop_index(op.f('ix_cases_assigned_user_id'), table_name='cases')
    op.drop_table('cases')
    op.drop_index(op.f('ix_monitor_configs_organization_id'), table_name='monitor_configs')
    op.drop_index(op.f('ix_monitor_configs_facility_id'), table_name='monitor_configs')
    op.drop_table('monitor_configs')
    op.drop_index(op.f('ix_event_handlings_event_id'), table_name='event_handlings')
    op.drop_table('event_handlings')
    op.drop_index(op.f('ix_monitor_runs_organization_id'), table_name='monitor_runs')
    op.drop_index('ix_monitor_runs_key_time', table_name='monitor_runs')
    op.drop_table('monitor_runs')
    op.drop_index('ix_domain_events_pending', table_name='domain_events', postgresql_where=sa.text("status = 'pending'"))
    op.drop_index(op.f('ix_domain_events_organization_id'), table_name='domain_events')
    op.drop_index(op.f('ix_domain_events_event_type'), table_name='domain_events')
    op.drop_table('domain_events')
    op.execute("DROP SEQUENCE IF EXISTS case_number_seq")
    # ### end Alembic commands ###
