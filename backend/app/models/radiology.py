"""Radiology (B8): imaging studies from imaging orders, technologist workflow, radiologist report (draft → signed),
critical-finding communication. Images live in an external PACS (DICOMweb adapter); Undeclared never stores pixels.
Signed reports are frozen by a DB trigger; changes after signing are addenda."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk

STUDY_STATUSES = ("scheduled", "arrived", "in_progress", "completed", "preliminary", "final", "cancelled")


class ImagingStudy(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "imaging_studies"
    order_id: Mapped[uuid.UUID] = fk("orders.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    accession_number: Mapped[int] = mapped_column(BigInteger, server_default=text("nextval('accession_seq')"), unique=True)
    modality: Mapped[str] = mapped_column(String(10))  # XR | CT | MR | US | MG | ECHO
    status: Mapped[str] = mapped_column(String(12), default="scheduled")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    performed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    study_instance_uid: Mapped[str | None] = mapped_column(String(80))  # DICOM Study Instance UID (from the PACS)
    technologist_note: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[str | None] = mapped_column(Text)
    impression: Mapped[str | None] = mapped_column(Text)
    critical_finding: Mapped[bool] = mapped_column(Boolean, default=False)
    drafted_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    signed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    addenda: Mapped[list] = mapped_column(JSONB, default=list)
    critical_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    critical_ack_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    critical_read_back: Mapped[str | None] = mapped_column(Text)
    order = relationship("Order", lazy="joined")
    patient = relationship("Patient", lazy="joined")

    __table_args__ = (
        CheckConstraint("status in (" + ",".join(f"'{s}'" for s in STUDY_STATUSES) + ")", name="status"),
        CheckConstraint("status <> 'final' or (signed_by_id is not null and impression is not null)", name="final_signed"),
        Index("uq_imaging_active_order", "order_id", unique=True, postgresql_where=text("status <> 'cancelled'")),
    )
