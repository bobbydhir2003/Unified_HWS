import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk


class AutomationWorkflow(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "automation_workflows"
    template_key: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(String(50))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)  # e.g. {"assign_role": "nurse"}
    requires_approval: Mapped[bool] = mapped_column(default=True)
    is_enabled: Mapped[bool] = mapped_column(default=False)
    created_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")

    __table_args__ = (Index("ix_workflows_org_trigger", "organization_id", "trigger", "is_enabled"),)


class AutomationRun(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "automation_runs"
    workflow_id: Mapped[uuid.UUID] = fk("automation_workflows.id")
    trigger_event: Mapped[str] = mapped_column(String(50))
    subject_type: Mapped[str | None] = mapped_column(String(40))
    subject_id: Mapped[str | None] = mapped_column(String(64))
    patient_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    proposed_actions: Mapped[list] = mapped_column(JSONB, default=list)
    log: Mapped[list] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    decided_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status in ('pending','pending_approval','approved','rejected','running','succeeded','failed','skipped')", name="status"),
        Index("ix_runs_org_status", "organization_id", "status", "created_at"),
    )


class Task(UUIDPk, Timestamps, OrgScoped, Base):
    """Staff worklist item, created by people or by automations."""

    __tablename__ = "tasks"
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    patient_id: Mapped[uuid.UUID | None] = fk("patients.id", nullable=True, ondelete="SET NULL")
    assigned_role: Mapped[str | None] = mapped_column(String(30))
    assigned_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    status: Mapped[str] = mapped_column(String(10), default="open")
    link: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | automation | receptionist
    run_id: Mapped[uuid.UUID | None] = fk("automation_runs.id", nullable=True, ondelete="SET NULL")
    completed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("priority in ('low','normal','high','urgent')", name="priority"),
        CheckConstraint("status in ('open','done','cancelled')", name="status"),
        Index("ix_tasks_org_status", "organization_id", "status", "assigned_role"),
    )


class VoiceCall(UUIDPk, Timestamps, OrgScoped, Base):
    """AI receptionist call (sandbox). Transcript is stored; PHI is only disclosed after identity verification."""

    __tablename__ = "voice_calls"
    from_number: Mapped[str | None] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(20), default="sandbox")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | completed | transferred | abandoned
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    consented: Mapped[bool] = mapped_column(default=False)
    verified_patient_id: Mapped[uuid.UUID | None] = fk("patients.id", nullable=True, ondelete="SET NULL")
    transcript: Mapped[list] = mapped_column(JSONB, default=list)
    intent: Mapped[str | None] = mapped_column(String(40))
    outcome: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    created_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
