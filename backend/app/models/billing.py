import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk

CLAIM_STATUSES = ("draft", "ready", "submitted", "accepted", "rejected", "paid", "partially_paid", "denied", "appealed", "closed", "void")


class FeeScheduleItem(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "fee_schedule"
    code: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(String(200))
    price_cents: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (UniqueConstraint("organization_id", "code"), CheckConstraint("price_cents >= 0", name="price"))


class Claim(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "claims"
    claim_number: Mapped[str] = mapped_column(String(30))
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    encounter_id: Mapped[uuid.UUID] = fk("encounters.id")
    insurance_id: Mapped[uuid.UUID | None] = fk("patient_insurances.id", nullable=True, ondelete="SET NULL")
    payer_name: Mapped[str] = mapped_column(String(200))
    member_id: Mapped[str] = mapped_column(String(60))
    rendering_provider_id: Mapped[uuid.UUID] = fk("provider_profiles.id")
    service_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    total_charge_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    allowed_cents: Mapped[int | None] = mapped_column(BigInteger)
    paid_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    patient_responsibility_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    adjustment_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    scrub_errors: Mapped[list] = mapped_column(JSONB, default=list)
    clearinghouse_ref: Mapped[str | None] = mapped_column(String(60))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    adjudicated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    denial_code: Mapped[str | None] = mapped_column(String(20))
    denial_reason: Mapped[str | None] = mapped_column(String(300))
    appeal_text: Mapped[str | None] = mapped_column(Text)
    appeal_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submission_count: Mapped[int] = mapped_column(Integer, default=0)

    charges: Mapped[list["Charge"]] = relationship(order_by="Charge.created_at", lazy="selectin")
    events: Mapped[list["ClaimEvent"]] = relationship(order_by="ClaimEvent.created_at", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("organization_id", "claim_number"),
        CheckConstraint("status in (" + ",".join(f"'{s}'" for s in CLAIM_STATUSES) + ")", name="status"),
        CheckConstraint("total_charge_cents >= 0 and paid_cents >= 0 and patient_responsibility_cents >= 0", name="amounts"),
        Index("ix_claims_org_status", "organization_id", "status", "created_at"),
    )


class Charge(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "charges"
    encounter_id: Mapped[uuid.UUID] = fk("encounters.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    claim_id: Mapped[uuid.UUID | None] = fk("claims.id", nullable=True, ondelete="SET NULL")
    code: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(String(200))
    modifiers: Mapped[list[str]] = mapped_column(ARRAY(String(4)), default=list)
    units: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    diagnosis_codes: Mapped[list[str]] = mapped_column(ARRAY(String(10)), default=list)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | billed | void
    created_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")

    __table_args__ = (
        CheckConstraint("units between 1 and 99 and unit_price_cents >= 0 and amount_cents = units * unit_price_cents", name="amount"),
        CheckConstraint("status in ('pending','billed','void')", name="status"),
    )


class ClaimEvent(UUIDPk, OrgScoped, Base):
    __tablename__ = "claim_events"
    claim_id: Mapped[uuid.UUID] = fk("claims.id")
    event: Mapped[str] = mapped_column(String(40))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    actor_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaimSubmission(UUIDPk, OrgScoped, Base):
    """Idempotency record: the same Idempotency-Key never submits a claim twice."""

    __tablename__ = "claim_submissions"
    claim_id: Mapped[uuid.UUID] = fk("claims.id")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    clearinghouse_ref: Mapped[str] = mapped_column(String(60))
    response: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key"),)


class Invoice(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "invoices"
    number: Mapped[str] = mapped_column(String(30))
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    claim_id: Mapped[uuid.UUID | None] = fk("claims.id", nullable=True, ondelete="SET NULL")
    encounter_id: Mapped[uuid.UUID | None] = fk("encounters.id", nullable=True, ondelete="SET NULL")
    description: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | paid | void
    total_cents: Mapped[int] = mapped_column(BigInteger)
    balance_cents: Mapped[int] = mapped_column(BigInteger)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    due_date: Mapped[date] = mapped_column(Date)

    __table_args__ = (
        UniqueConstraint("organization_id", "number"),
        CheckConstraint("total_cents >= 0 and balance_cents >= 0 and balance_cents <= total_cents", name="amounts"),
        CheckConstraint("status in ('open','paid','void')", name="status"),
    )


class Payment(UUIDPk, OrgScoped, Base):
    __tablename__ = "payments"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    invoice_id: Mapped[uuid.UUID | None] = fk("invoices.id", nullable=True, ondelete="SET NULL")
    claim_id: Mapped[uuid.UUID | None] = fk("claims.id", nullable=True, ondelete="SET NULL")
    source: Mapped[str] = mapped_column(String(10))  # patient | insurance
    method: Mapped[str] = mapped_column(String(20))  # cash | check | card_simulated | eft_simulated
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    reference: Mapped[str | None] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(12), default="succeeded")
    created_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key"),
        CheckConstraint("amount_cents > 0", name="amount"),
        CheckConstraint("source in ('patient','insurance')", name="source"),
        Index("ix_payments_org_created", "organization_id", "created_at"),
    )
