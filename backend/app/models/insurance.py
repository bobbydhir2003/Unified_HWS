"""Insurance Guardian data: payer-verified eligibility history and patient coverage-update requests.

Two different truths are kept apart on purpose:
- `patient_insurances.termination_date` is what someone *entered* (card, patient, staff). It is never proof of anything.
- `eligibility_checks` is what the *payer reported* (270/271 — simulated until a clearinghouse is connected), for a date of
  service, at a point in time. Only an active check makes a visit "verified".
"""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk


class EligibilityCheck(UUIDPk, OrgScoped, Base):
    __tablename__ = "eligibility_checks"
    insurance_id: Mapped[uuid.UUID] = fk("patient_insurances.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    appointment_id: Mapped[uuid.UUID | None] = fk("appointments.id", nullable=True, ondelete="SET NULL")
    date_of_service: Mapped[date] = mapped_column(Date)
    result: Mapped[str] = mapped_column(String(10))  # active | inactive | error
    coverage_start: Mapped[date | None] = mapped_column(Date)  # as reported by the payer
    coverage_end: Mapped[date | None] = mapped_column(Date)
    plan_description: Mapped[str | None] = mapped_column(String(200))
    copay_cents: Mapped[int | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(20))  # simulated | clearinghouse | manual
    trigger: Mapped[str] = mapped_column(String(20), default="staff")  # staff | auto_batch | recheck | portal
    payer_trace: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str | None] = mapped_column(String(300))
    response: Mapped[dict] = mapped_column(JSONB, default=dict)
    checked_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("result in ('active','inactive','error')", name="result"),
        CheckConstraint("source in ('simulated','clearinghouse','manual')", name="source"),
        Index("ix_elig_ins_time", "insurance_id", "checked_at"),
    )


class CoverageUpdateRequest(UUIDPk, Timestamps, OrgScoped, Base):
    """Asks a patient for updated insurance; the patient submits a card image and/or details; staff confirms."""

    __tablename__ = "coverage_update_requests"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    case_id: Mapped[uuid.UUID | None] = fk("cases.id", nullable=True, ondelete="SET NULL")
    appointment_id: Mapped[uuid.UUID | None] = fk("appointments.id", nullable=True, ondelete="SET NULL", index=False)
    reason: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(12), default="requested")
    document_id: Mapped[uuid.UUID | None] = fk("documents.id", nullable=True, ondelete="SET NULL", index=False)
    submitted: Mapped[dict] = mapped_column(JSONB, default=dict)  # what the patient typed
    extracted: Mapped[dict] = mapped_column(JSONB, default=dict)  # what document AI read from the card (draft)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_insurance_id: Mapped[uuid.UUID | None] = fk("patient_insurances.id", nullable=True, ondelete="SET NULL", index=False)
    reviewed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status in ('requested','submitted','confirmed','rejected','cancelled')", name="status"),
        Index("ix_cur_org_status", "organization_id", "status"),
    )
