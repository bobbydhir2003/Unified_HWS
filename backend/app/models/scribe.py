import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk

SCRIBE_STATUSES = ("recording", "transcribing", "transcribed", "drafting", "ready", "applied", "discarded", "failed")


class ScribeSession(UUIDPk, Timestamps, OrgScoped, Base):
    """Ambient documentation session for one encounter. Consent is mandatory and recorded before any capture."""

    __tablename__ = "scribe_sessions"
    encounter_id: Mapped[uuid.UUID] = fk("encounters.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    clinician_id: Mapped[uuid.UUID] = fk("users.id", ondelete=None)
    status: Mapped[str] = mapped_column(String(20), default="recording")
    consent_method: Mapped[str] = mapped_column(String(20))  # verbal | written
    consent_recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    transcript_source: Mapped[str | None] = mapped_column(String(20))  # audio | manual | synthetic_demo
    audio_storage_key: Mapped[str | None] = mapped_column(String(300))
    audio_content_type: Mapped[str | None] = mapped_column(String(60))
    audio_seconds: Mapped[int | None] = mapped_column(Integer)
    audio_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transcript: Mapped[list | None] = mapped_column(JSONB)  # [{speaker: clinician|patient|other, text}]
    transcript_edited: Mapped[bool] = mapped_column(default=False)
    draft: Mapped[dict | None] = mapped_column(JSONB)  # SOAP + extracted items + uncertainties
    draft_count: Mapped[int] = mapped_column(Integer, default=0)
    applied_note_version: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status in (" + ",".join(f"'{s}'" for s in SCRIBE_STATUSES) + ")", name="status"),
        CheckConstraint("consent_method in ('verbal','written')", name="consent"),
    )
