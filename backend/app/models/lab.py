"""Laboratory (B7): specimens with accession numbers, and critical-result call-back tracking.

Result lifecycle (lab_results.status): preliminary (entered) → final (verified by a *different* lab user) →
corrected results create a new row and mark the old one superseded (history kept). Only orders whose results are all
final can be released to the patient portal.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk

SPECIMEN_STATUSES = ("collected", "received", "in_process", "resulted", "rejected")


class Specimen(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "specimens"
    order_id: Mapped[uuid.UUID] = fk("orders.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    accession_number: Mapped[int] = mapped_column(BigInteger, server_default=text("nextval('accession_seq')"), unique=True)
    specimen_type: Mapped[str] = mapped_column(String(30), default="blood")
    container: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(12), default="collected")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    collected_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    rejected_reason: Mapped[str | None] = mapped_column(String(200))
    order = relationship("Order", lazy="joined")
    patient = relationship("Patient", lazy="joined")

    __table_args__ = (
        CheckConstraint("status in (" + ",".join(f"'{s}'" for s in SPECIMEN_STATUSES) + ")", name="status"),
        CheckConstraint("status <> 'rejected' or rejected_reason is not null", name="rejected_reason"),
        Index("uq_specimen_active_order", "order_id", unique=True, postgresql_where=text("status <> 'rejected'")),
    )


class CriticalResultAlert(UUIDPk, OrgScoped, Base):
    """Critical value call-back: who was notified, and when the responsible clinician acknowledged (read-back)."""

    __tablename__ = "critical_result_alerts"
    order_id: Mapped[uuid.UUID] = fk("orders.id")
    result_id: Mapped[uuid.UUID] = fk("lab_results.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    clinician_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    summary: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    read_back: Mapped[str | None] = mapped_column(Text)
    case_id: Mapped[uuid.UUID | None] = fk("cases.id", nullable=True, ondelete="SET NULL", index=False)
