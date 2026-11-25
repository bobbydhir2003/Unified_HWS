"""HMS Assist conversations: persistent, record-bound chats with the ten department agents.

* A conversation belongs to ONE user, ONE agent and (optionally) ONE record context, resolved and access-checked by the
  server on every turn (app/agents/context.py). The acting role at creation is recorded; a turn from another workspace
  is refused.
* Messages are append-only (DB trigger); retention redacts content after `expires_at` but keeps metadata for audit.
* Conversations are operational records, NOT part of the legal health record: nothing here is exported, printed or shown
  in the patient portal. A clinician who wants content in the chart writes and signs a note through the normal workflow.
* Action drafts are "confirm in chat" actions: prepared by an agent, executed only when the same user confirms, through
  the existing service and under that user's own permissions.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScoped, UUIDPk, fk


class AssistConversation(UUIDPk, OrgScoped, Base):
    __tablename__ = "assist_conversations"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    agent_key: Mapped[str] = mapped_column(String(40))
    agent_version: Mapped[int] = mapped_column(Integer, default=1)
    acting_role: Mapped[str | None] = mapped_column(String(30))
    context_type: Mapped[str] = mapped_column(String(30), default="workspace")
    context_id: Mapped[str | None] = mapped_column(String(80))
    context_label: Mapped[str | None] = mapped_column(String(250))
    patient_id: Mapped[uuid.UUID | None] = fk("patients.id", nullable=True, ondelete="SET NULL")
    facility_id: Mapped[uuid.UUID | None] = fk("clinics.id", nullable=True, ondelete="SET NULL", index=False)
    case_id: Mapped[uuid.UUID | None] = fk("cases.id", nullable=True, ondelete="SET NULL")
    title: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    legal_hold: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (CheckConstraint("status in ('active','closed','expired')", name="status"),
                      Index("ix_assist_conv_user", "organization_id", "user_id", "last_message_at"),
                      Index("ix_assist_conv_context", "organization_id", "context_type", "context_id"))


class AssistMessage(UUIDPk, OrgScoped, Base):
    __tablename__ = "assist_messages"
    conversation_id: Mapped[uuid.UUID] = fk("assist_conversations.id")
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    agent_run_id: Mapped[uuid.UUID | None] = fk("agent_runs.id", nullable=True, ondelete="SET NULL", index=False)
    mode: Mapped[str | None] = mapped_column(String(12))  # openai | rule_based | policy
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    actions: Mapped[list] = mapped_column(JSONB, default=list)  # [{"type": "approval"|"draft", "id": "..."}]
    tool_activity: Mapped[list] = mapped_column(JSONB, default=list)  # [{"tool", "ok", "summary"}] — no raw PHI payloads
    error: Mapped[str | None] = mapped_column(String(400))
    redacted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("conversation_id", "seq"),
                      CheckConstraint("role in ('user','assistant','system')", name="role"))


class AssistActionDraft(UUIDPk, OrgScoped, Base):
    __tablename__ = "assist_action_drafts"
    conversation_id: Mapped[uuid.UUID] = fk("assist_conversations.id")
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(250))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    required_permission: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(12), default="draft")
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_by_agent: Mapped[str] = mapped_column(String(40))
    confirmed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("status in ('draft','confirmed','discarded','failed','expired')", name="status"),)
