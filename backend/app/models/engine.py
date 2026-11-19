"""Durable automation engine: transactional outbox, idempotent handlers, cases, monitors, notifications, approvals.

Detect (events + monitors) → Prioritize (severity/SLA) → Assign (role/user/department) → Assist (tasks, drafts)
→ Approve/Execute (approval_requests) → Verify (monitors re-check and auto-resolve) → Audit (case_events + audit_events).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk

SEVERITIES = ("info", "low", "medium", "high", "critical")
CASE_STATUSES = ("open", "in_progress", "waiting", "snoozed", "escalated", "resolved", "cancelled")
CASE_OPEN = ("open", "in_progress", "waiting", "snoozed", "escalated")
CASE_CATEGORIES = ("insurance", "scheduling", "clinical", "lab", "radiology", "pharmacy", "inventory", "bed", "ed", "discharge",
                   "billing", "staffing", "or", "equipment", "patient_followup", "documents", "operations", "automation")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} in (" + ",".join(f"'{v}'" for v in values) + ")"


class DomainEvent(UUIDPk, OrgScoped, Base):
    """Outbox row written in the same transaction as the state change; dispatched with retries after commit."""

    __tablename__ = "domain_events"
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    subject_type: Mapped[str | None] = mapped_column(String(40))
    subject_id: Mapped[str | None] = mapped_column(String(64))
    patient_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    facility_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status in ('pending','done','dead')", name="status"),
        Index("ix_domain_events_pending", "next_attempt_at", postgresql_where=text("status = 'pending'")),
    )


class EventHandling(UUIDPk, Base):
    """One row per (event, handler) that completed — makes redelivery a no-op (exactly-once effects)."""

    __tablename__ = "event_handlings"
    event_id: Mapped[uuid.UUID] = fk("domain_events.id")
    handler: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(10), default="done")
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("event_id", "handler"), CheckConstraint("status in ('done','failed')", name="status"))


class Case(UUIDPk, Timestamps, OrgScoped, Base):
    """An accountable operational problem with an owner, severity, SLA and full history."""

    __tablename__ = "cases"
    number: Mapped[int] = mapped_column(Integer, server_default=text("nextval('case_number_seq')"))
    facility_id: Mapped[uuid.UUID | None] = fk("clinics.id", nullable=True, ondelete="SET NULL")
    department_id: Mapped[uuid.UUID | None] = fk("departments.id", nullable=True, ondelete="SET NULL")
    category: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(60))  # e.g. insurance.visit_unverified
    dedupe_key: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(250))
    summary: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    status: Mapped[str] = mapped_column(String(12), default="open")
    patient_id: Mapped[uuid.UUID | None] = fk("patients.id", nullable=True, ondelete="SET NULL")
    subject_type: Mapped[str | None] = mapped_column(String(40))
    subject_id: Mapped[str | None] = mapped_column(String(64))
    link: Mapped[str | None] = mapped_column(String(300))
    assigned_role: Mapped[str | None] = mapped_column(String(30))
    assigned_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snooze_reason: Mapped[str | None] = mapped_column(String(300))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    resolution_code: Mapped[str | None] = mapped_column(String(40))
    resolution: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default="monitor")
    rule_key: Mapped[str | None] = mapped_column(String(60))
    rule_version: Mapped[int | None] = mapped_column(Integer)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(_in("severity", SEVERITIES), name="severity"),
        CheckConstraint(_in("status", CASE_STATUSES), name="status"),
        CheckConstraint(_in("category", CASE_CATEGORIES), name="category"),
        CheckConstraint("source in ('monitor','event','manual','agent')", name="source"),
        CheckConstraint("status <> 'snoozed' or (snoozed_until is not null and snooze_reason is not null)", name="snooze_reason"),
        # The dedupe guarantee: at most one open case per problem.
        Index("uq_cases_open_dedupe", "organization_id", "dedupe_key", unique=True,
              postgresql_where=text("status in ('open','in_progress','waiting','snoozed','escalated')")),
        Index("ix_cases_org_status_cat", "organization_id", "status", "category"),
        Index("ix_cases_org_role", "organization_id", "assigned_role", "status"),
        Index("ix_cases_due", "due_at", postgresql_where=text("status in ('open','in_progress','escalated')")),
        Index("ix_cases_rule", "organization_id", "rule_key", "status"),
    )


class CaseEvent(UUIDPk, OrgScoped, Base):
    """Append-only case timeline (enforced by trigger)."""

    __tablename__ = "case_events"
    case_id: Mapped[uuid.UUID] = fk("cases.id")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    actor_kind: Mapped[str] = mapped_column(String(10), default="system")
    kind: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(500))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (CheckConstraint("actor_kind in ('user','system','agent')", name="actor_kind"),)


class NotificationDelivery(UUIDPk, OrgScoped, Base):
    """Every outbound notification attempt. `dedupe_key` makes each reminder step send at most once."""

    __tablename__ = "notification_deliveries"
    case_id: Mapped[uuid.UUID | None] = fk("cases.id", nullable=True, ondelete="SET NULL")
    channel: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(40), default="general")
    recipient_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    recipient_patient_id: Mapped[uuid.UUID | None] = fk("patients.id", nullable=True, ondelete="SET NULL")
    address: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), default="queued")
    status_reason: Mapped[str | None] = mapped_column(String(200))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "dedupe_key"),
        CheckConstraint("channel in ('in_app','email','sms','portal')", name="channel"),
        CheckConstraint("status in ('queued','sent','simulated','failed','suppressed')", name="status"),
    )


class NotificationPreference(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "notification_preferences"
    user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True)
    patient_id: Mapped[uuid.UUID | None] = fk("patients.id", nullable=True)
    category: Mapped[str] = mapped_column(String(40), default="*")
    in_app: Mapped[bool] = mapped_column(default=True)
    email: Mapped[bool] = mapped_column(default=True)
    sms: Mapped[bool] = mapped_column(default=False)
    portal: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "patient_id", "category", postgresql_nulls_not_distinct=True),
        CheckConstraint("(user_id is null) <> (patient_id is null)", name="one_owner"),
    )


class MonitorConfig(UUIDPk, Timestamps, OrgScoped, Base):
    """Per-organization (optionally per-facility) monitor settings. Each change bumps `version` (recorded on cases)."""

    __tablename__ = "monitor_configs"
    facility_id: Mapped[uuid.UUID | None] = fk("clinics.id", nullable=True)
    monitor_key: Mapped[str] = mapped_column(String(60))
    is_enabled: Mapped[bool] = mapped_column(default=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)

    __table_args__ = (UniqueConstraint("organization_id", "facility_id", "monitor_key", postgresql_nulls_not_distinct=True),)


class MonitorRun(UUIDPk, OrgScoped, Base):
    __tablename__ = "monitor_runs"
    monitor_key: Mapped[str] = mapped_column(String(60))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(10), default="running")
    found: Mapped[int] = mapped_column(Integer, default=0)
    opened: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    closed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint("status in ('running','succeeded','failed')", name="status"),
        Index("ix_monitor_runs_key_time", "organization_id", "monitor_key", "started_at"),
    )


class ApprovalRequest(UUIDPk, Timestamps, OrgScoped, Base):
    """A proposed action (from an automation, agent, or staff member) that a permitted human must approve."""

    __tablename__ = "approval_requests"
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(250))
    summary: Mapped[str | None] = mapped_column(Text)
    case_id: Mapped[uuid.UUID | None] = fk("cases.id", nullable=True, ondelete="SET NULL")
    patient_id: Mapped[uuid.UUID | None] = fk("patients.id", nullable=True, ondelete="SET NULL")
    facility_id: Mapped[uuid.UUID | None] = fk("clinics.id", nullable=True, ondelete="SET NULL", index=False)
    requested_by_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    requested_by_agent: Mapped[str | None] = mapped_column(String(60))
    required_permission: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    decided_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(500))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status in ('pending','approved','rejected','executed','failed','expired')", name="status"),
        Index("ix_approvals_org_status", "organization_id", "status", "created_at"),
    )

