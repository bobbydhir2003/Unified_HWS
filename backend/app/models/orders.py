import uuid
from datetime import datetime

from sqlalchemy import ARRAY, CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk
from app.models.identity import User

ORDER_TYPES = ("medication", "lab", "imaging", "referral")
ORDER_STATUSES = ("draft", "signed", "transmitted", "in_progress", "resulted", "completed", "cancelled")


class Order(UUIDPk, Timestamps, OrgScoped, Base):
    """Clinical order. Drafts may be created by nurses; only clinicians with orders:sign can sign/transmit."""

    __tablename__ = "orders"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    encounter_id: Mapped[uuid.UUID | None] = fk("encounters.id", nullable=True, ondelete="SET NULL")
    order_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    priority: Mapped[str] = mapped_column(String(10), default="routine")
    title: Mapped[str] = mapped_column(String(300))
    code: Mapped[str | None] = mapped_column(String(30))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    indication_codes: Mapped[list[str]] = mapped_column(ARRAY(String(10)), default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    ordered_by_id: Mapped[uuid.UUID] = fk("users.id", ondelete=None)
    signed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete=None)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    safety_override_reason: Mapped[str | None] = mapped_column(String(500))
    safety_warnings: Mapped[list | None] = mapped_column(JSONB)
    transmitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transmission: Mapped[dict | None] = mapped_column(JSONB)  # {channel, reference, simulated: true}
    resulted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_text: Mapped[str | None] = mapped_column(Text)  # imaging report / referral outcome
    results_reviewed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete=None)
    results_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_to_patient_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_reason: Mapped[str | None] = mapped_column(String(300))

    ordered_by: Mapped[User] = relationship(foreign_keys=[ordered_by_id], lazy="joined")
    signed_by: Mapped[User | None] = relationship(foreign_keys=[signed_by_id], lazy="joined")
    results: Mapped[list["LabResult"]] = relationship(order_by="LabResult.name", lazy="selectin")

    __table_args__ = (
        CheckConstraint("order_type in (" + ",".join(f"'{t}'" for t in ORDER_TYPES) + ")", name="type"),
        CheckConstraint("status in (" + ",".join(f"'{t}'" for t in ORDER_STATUSES) + ")", name="status"),
        CheckConstraint("priority in ('routine','urgent','stat')", name="priority"),
        CheckConstraint("status in ('draft','cancelled') or signed_by_id is not null", name="signed_requires_signer"),
        Index("ix_orders_org_status", "organization_id", "status", "order_type"),
        Index("ix_orders_patient", "patient_id", "created_at"),
    )


class LabResult(UUIDPk, OrgScoped, Base):
    __tablename__ = "lab_results"
    order_id: Mapped[uuid.UUID] = fk("orders.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    name: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(String(60))
    unit: Mapped[str | None] = mapped_column(String(30))
    reference_range: Mapped[str | None] = mapped_column(String(60))
    flag: Mapped[str] = mapped_column(String(20), default="normal")  # normal|high|low|critical_high|critical_low|abnormal
    status: Mapped[str] = mapped_column(String(20), default="final")
    entered_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    verified_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_id: Mapped[uuid.UUID | None] = fk("lab_results.id", nullable=True, ondelete="SET NULL", index=False)
    correction_reason: Mapped[str | None] = mapped_column(String(300))
    specimen_id: Mapped[uuid.UUID | None] = fk("specimens.id", nullable=True, ondelete="SET NULL", index=False)
    resulted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(String(20), default="simulated")

    __table_args__ = (Index("ix_lab_results_patient_name", "patient_id", "name", "resulted_at"),)
