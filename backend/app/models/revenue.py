"""Revenue cycle expansion (B10): prior authorizations and claim review findings.

Claim findings are advisory: rules and AI only *flag* issues. Nothing here changes a claim, its codes or submits it."""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk

PA_STATUSES = ("draft", "submitted", "pended", "approved", "denied", "expired", "cancelled")


class PriorAuthorization(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "prior_authorizations"
    number: Mapped[int] = mapped_column(BigInteger, server_default=text("nextval('prior_auth_seq')"))
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    insurance_id: Mapped[uuid.UUID | None] = fk("patient_insurances.id", nullable=True, ondelete="SET NULL", index=False)
    order_id: Mapped[uuid.UUID | None] = fk("orders.id", nullable=True, ondelete="SET NULL")
    service_code: Mapped[str] = mapped_column(String(10))
    service_description: Mapped[str] = mapped_column(String(200))
    payer_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default="draft")
    checklist: Mapped[list] = mapped_column(JSONB, default=list)  # [{key, label, done, note}]
    clinical_summary: Mapped[str | None] = mapped_column(Text)
    auth_number: Mapped[str | None] = mapped_column(String(40))
    units_approved: Mapped[int | None] = mapped_column(Integer)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    denial_reason: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual | monitor
    channel: Mapped[str] = mapped_column(String(12), default="simulated")  # simulated | portal | x12_278
    created_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    patient = relationship("Patient", lazy="joined")

    __table_args__ = (
        CheckConstraint("status in (" + ",".join(f"'{s}'" for s in PA_STATUSES) + ")", name="status"),
        CheckConstraint("status <> 'approved' or (auth_number is not null and valid_from is not null and valid_to is not null)", name="approved_complete"),
        Index("uq_pa_active_order", "order_id", unique=True, postgresql_where=text("order_id is not null and status not in ('denied','expired','cancelled')")),
        Index("ix_pa_org_status", "organization_id", "status"),
    )


class ClaimFinding(UUIDPk, OrgScoped, Base):
    __tablename__ = "claim_findings"
    claim_id: Mapped[uuid.UUID] = fk("claims.id")
    source: Mapped[str] = mapped_column(String(10))  # rule | ai
    code: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(8), default="warning")  # blocker | warning | info
    message: Mapped[str] = mapped_column(String(500))
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | resolved | dismissed
    resolution_note: Mapped[str | None] = mapped_column(String(300))
    resolved_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    model: Mapped[str | None] = mapped_column(String(80))

    __table_args__ = (CheckConstraint("severity in ('blocker','warning','info')", name="severity"),
                      CheckConstraint("status in ('open','resolved','dismissed')", name="status"),
                      CheckConstraint("source in ('rule','ai')", name="source"))
