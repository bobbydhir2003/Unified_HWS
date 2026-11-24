"""Inpatient nursing documentation: flowsheet observations (incl. intake/output), structured assessments and care plans.

* Observations are append-only; a correction is a new row that supersedes the old one (both kept).
* Assessments: draft (author edits) → signed (frozen, DB trigger) → amendment = a new draft linked to the signed one;
  signing the amendment marks the original `amended`. Nothing is deleted.
* Care plans: problem/need, goal, interventions, responsible role, status and a timestamped progress log.
Rows/templates are configurable, organization-reviewed demonstrations — not a formal nursing taxonomy.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScoped, UUIDPk, fk


class NursingObservation(UUIDPk, OrgScoped, Base):
    __tablename__ = "nursing_observations"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    stay_id: Mapped[uuid.UUID | None] = fk("inpatient_stays.id", nullable=True, ondelete="SET NULL")
    row_key: Mapped[str] = mapped_column(String(40))
    value_num: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    value_text: Mapped[str | None] = mapped_column(String(300))
    unit: Mapped[str | None] = mapped_column(String(20))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_by_id: Mapped[uuid.UUID] = fk("users.id", ondelete=None, index=False)
    supersedes_id: Mapped[uuid.UUID | None] = fk("nursing_observations.id", nullable=True, ondelete=None, index=False)
    correction_reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_nursing_obs_patient_time", "patient_id", "observed_at"),
                      CheckConstraint("value_num IS NOT NULL OR value_text IS NOT NULL", name="has_value"))


class NursingAssessment(UUIDPk, OrgScoped, Base):
    __tablename__ = "nursing_assessments"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    stay_id: Mapped[uuid.UUID | None] = fk("inpatient_stays.id", nullable=True, ondelete="SET NULL")
    template_key: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft | signed | amended
    author_id: Mapped[uuid.UUID] = fk("users.id", ondelete=None, index=False)
    signed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete=None, index=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amends_id: Mapped[uuid.UUID | None] = fk("nursing_assessments.id", nullable=True, ondelete=None, index=False)
    amendment_reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (CheckConstraint("status in ('draft','signed','amended')", name="status"),
                      CheckConstraint("status = 'draft' OR signed_by_id IS NOT NULL", name="signed_has_signer"))


class NursingCarePlan(UUIDPk, OrgScoped, Base):
    __tablename__ = "nursing_care_plans"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    stay_id: Mapped[uuid.UUID | None] = fk("inpatient_stays.id", nullable=True, ondelete="SET NULL")
    problem: Mapped[str] = mapped_column(String(300))
    goal: Mapped[str] = mapped_column(String(500))
    interventions: Mapped[list] = mapped_column(JSONB, default=list)
    responsible_role: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | met | not_met | discontinued
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress: Mapped[list] = mapped_column(JSONB, default=list)  # [{at, by, note, status}]
    created_by_id: Mapped[uuid.UUID] = fk("users.id", ondelete=None, index=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("status in ('active','met','not_met','discontinued')", name="status"),)



