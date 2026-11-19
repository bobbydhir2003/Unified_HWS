import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk
from app.models.identity import User


class MessageThread(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "message_threads"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    subject: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30), default="general")  # general|medication|results|appointment|billing
    status: Mapped[str] = mapped_column(String(20), default="open")
    assigned_provider_id: Mapped[uuid.UUID | None] = fk("provider_profiles.id", nullable=True, ondelete="SET NULL")
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    patient_unread: Mapped[int] = mapped_column(default=0)
    staff_unread: Mapped[int] = mapped_column(default=0)
    messages: Mapped[list["SecureMessage"]] = relationship(order_by="SecureMessage.created_at", lazy="selectin")

    __table_args__ = (
        CheckConstraint("status in ('open','closed')", name="status"),
        Index("ix_threads_org_status", "organization_id", "status", "last_message_at"),
    )


class SecureMessage(UUIDPk, OrgScoped, Base):
    __tablename__ = "secure_messages"
    thread_id: Mapped[uuid.UUID] = fk("message_threads.id")
    sender_id: Mapped[uuid.UUID] = fk("users.id", ondelete=None)
    sender_is_patient: Mapped[bool]
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sender: Mapped[User] = relationship(lazy="joined")


class IntakeSubmission(UUIDPk, OrgScoped, Base):
    __tablename__ = "intake_submissions"
    appointment_id: Mapped[uuid.UUID] = fk("appointments.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    answers: Mapped[dict] = mapped_column(JSONB)
    submitted_by_id: Mapped[uuid.UUID] = fk("users.id", ondelete=None)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("appointment_id"),)


class TelehealthSession(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "telehealth_sessions"
    appointment_id: Mapped[uuid.UUID] = fk("appointments.id")
    status: Mapped[str] = mapped_column(String(20), default="waiting")  # waiting | active | ended
    patient_joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("appointment_id"), CheckConstraint("status in ('waiting','active','ended')", name="status"))


class TelehealthSignal(Base):
    """Short-lived WebRTC signaling messages (offer/answer/ICE). Media never touches the server."""

    __tablename__ = "telehealth_signals"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[uuid.UUID] = fk("telehealth_sessions.id")
    sender_role: Mapped[str] = mapped_column(String(10))  # patient | provider
    kind: Mapped[str] = mapped_column(String(20))  # offer | answer | ice | hangup | hello
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
