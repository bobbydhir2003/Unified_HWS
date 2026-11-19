"""AI Agent Studio (C2) + feedback (C7). Agents act only through backend tools; every call is permission-checked and
writes are proposals in the approval queue. Config changes are versioned (append-only snapshots)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk


class AgentConfig(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "agent_configs"
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    purpose: Mapped[str] = mapped_column(Text)
    instructions: Mapped[str] = mapped_column(Text)
    allowed_tools: Mapped[list] = mapped_column(JSONB, default=list)
    model: Mapped[str | None] = mapped_column(String(80))  # null → per-agent/text model from AI settings
    trigger: Mapped[str] = mapped_column(String(10), default="manual")  # manual | case | schedule
    required_permission: Mapped[str] = mapped_column(String(40))
    max_tool_calls: Mapped[int] = mapped_column(Integer, default=6)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    max_cost_usd: Mapped[float] = mapped_column(Float, default=0.25)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    facility_overrides: Mapped[dict] = mapped_column(JSONB, default=dict)  # {facility_id: bool}
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)

    __table_args__ = (UniqueConstraint("organization_id", "key"),
                      CheckConstraint("max_tool_calls between 1 and 20 and timeout_seconds between 5 and 600 and max_cost_usd >= 0", name="limits"))


class AgentConfigVersion(UUIDPk, OrgScoped, Base):
    __tablename__ = "agent_config_versions"
    agent_key: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    changed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    note: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRun(UUIDPk, OrgScoped, Base):
    __tablename__ = "agent_runs"
    agent_key: Mapped[str] = mapped_column(String(40))
    agent_version: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    facility_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    subject_type: Mapped[str | None] = mapped_column(String(40))
    subject_id: Mapped[str | None] = mapped_column(String(64))
    patient_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    input: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(12))  # openai | rule_based
    model: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(15), default="running")
    output: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[list] = mapped_column(JSONB, default=list)
    approvals: Mapped[list] = mapped_column(JSONB, default=list)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("status in ('running','succeeded','failed','limit_reached','blocked')", name="status"),
                      Index("ix_agent_runs_org_time", "organization_id", "started_at"))


class AIFeedback(UUIDPk, OrgScoped, Base):
    __tablename__ = "ai_feedback"
    agent_run_id: Mapped[uuid.UUID | None] = fk("agent_runs.id", nullable=True, ondelete="SET NULL")
    ai_job_id: Mapped[uuid.UUID | None] = fk("ai_jobs.id", nullable=True, ondelete="SET NULL")
    user_id: Mapped[uuid.UUID] = fk("users.id", index=False)
    rating: Mapped[str] = mapped_column(String(5))  # up | down
    comment: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("rating in ('up','down')", name="rating"),)
