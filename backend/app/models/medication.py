"""Medication administration record (eMAR).

One row per documented administration event. Rows are append-only (DB trigger); a witness for a high-alert dose is
recorded in a separate append-only row (`MedicationAdministrationWitness`) so the original event never changes.
A scheduled dose can be documented once: UNIQUE (order_id, scheduled_for); PRN doses (scheduled_for NULL) are
protected by the minimum-interval rule in services/medication.py.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScoped, UUIDPk, fk

ADMIN_STATUSES = ("given", "held", "refused", "omitted")


class MedicationAdministration(UUIDPk, OrgScoped, Base):
    __tablename__ = "medication_administrations"
    order_id: Mapped[uuid.UUID] = fk("orders.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    stay_id: Mapped[uuid.UUID | None] = fk("inpatient_stays.id", nullable=True, ondelete="SET NULL")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NULL = PRN / one-off
    status: Mapped[str] = mapped_column(String(10))
    dose: Mapped[str | None] = mapped_column(String(60))
    route: Mapped[str | None] = mapped_column(String(40))
    site: Mapped[str | None] = mapped_column(String(60))
    reason: Mapped[str | None] = mapped_column(Text)  # required unless given on time
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    administered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    administered_by_id: Mapped[uuid.UUID] = fk("users.id", ondelete=None, index=False)
    dispense_movement_id: Mapped[uuid.UUID | None] = fk("stock_movements.id", nullable=True, ondelete="SET NULL", index=False)
    scan: Mapped[dict] = mapped_column(JSONB, default=dict)  # {patient: ok, medication: ok, simulated: true, ...}
    requires_witness: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("order_id", "scheduled_for", name="uq_med_admin_order_slot"),
        CheckConstraint("status in ('given','held','refused','omitted')", name="status"),
        CheckConstraint("status = 'given' OR reason IS NOT NULL", name="reason_required"),
        Index("ix_med_admin_patient_time", "patient_id", "administered_at"),
    )


class MedicationAdministrationWitness(UUIDPk, OrgScoped, Base):
    """Independent second-person confirmation of a high-alert administration (the witness is never the administrator)."""

    __tablename__ = "medication_administration_witnesses"
    administration_id: Mapped[uuid.UUID] = fk("medication_administrations.id")
    witness_id: Mapped[uuid.UUID] = fk("users.id", ondelete=None, index=False)
    note: Mapped[str | None] = mapped_column(String(300))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("administration_id"),)
