import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk


class Patient(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "patients"
    mrn: Mapped[str] = mapped_column(String(20))
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    preferred_name: Mapped[str | None] = mapped_column(String(100))
    date_of_birth: Mapped[date] = mapped_column(Date)
    sex_at_birth: Mapped[str] = mapped_column(String(10))  # female | male | intersex | unknown
    gender_identity: Mapped[str | None] = mapped_column(String(60))
    pronouns: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    phone_alt: Mapped[str | None] = mapped_column(String(40))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    address_line2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    preferred_language: Mapped[str] = mapped_column(String(40), default="English")
    marital_status: Mapped[str | None] = mapped_column(String(30))
    emergency_contact_name: Mapped[str | None] = mapped_column(String(200))
    emergency_contact_relation: Mapped[str | None] = mapped_column(String(60))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="active")
    primary_clinic_id: Mapped[uuid.UUID | None] = fk("clinics.id", nullable=True, ondelete="SET NULL")
    primary_provider_id: Mapped[uuid.UUID | None] = fk(
        "provider_profiles.id", nullable=True, ondelete="SET NULL"
    )
    portal_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    # Restricted charts (VIP, employee, sensitive) require an explicit grant or a "break-glass" reason.
    is_restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    insurances: Mapped[list["PatientInsurance"]] = relationship(
        cascade="all, delete-orphan", order_by="PatientInsurance.priority"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "mrn"),
        CheckConstraint("status in ('active','inactive','deceased')", name="status"),
        CheckConstraint("sex_at_birth in ('female','male','intersex','unknown')", name="sex"),
        Index("ix_patients_org_name", "organization_id", text("lower(last_name)"), text("lower(first_name)")),
        Index("ix_patients_org_dob", "organization_id", "date_of_birth"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class PatientInsurance(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "patient_insurances"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    priority: Mapped[str] = mapped_column(String(10), default="primary")
    payer_name: Mapped[str] = mapped_column(String(200))
    plan_name: Mapped[str | None] = mapped_column(String(200))
    member_id: Mapped[str] = mapped_column(String(60))
    group_number: Mapped[str | None] = mapped_column(String(60))
    subscriber_name: Mapped[str | None] = mapped_column(String(200))
    subscriber_relation: Mapped[str] = mapped_column(String(20), default="self")
    effective_date: Mapped[date | None] = mapped_column(Date)
    termination_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    eligibility_status: Mapped[str] = mapped_column(String(20), default="unverified")
    eligibility_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("priority in ('primary','secondary','tertiary')", name="priority"),
    )


class PatientAccessGrant(UUIDPk, OrgScoped, Base):
    """Explicit access to a restricted chart. Break-glass grants are time-limited and always audited."""

    __tablename__ = "patient_access_grants"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    reason: Mapped[str] = mapped_column(Text)
    is_break_glass: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PatientNote(UUIDPk, Timestamps, OrgScoped, Base):
    """Non-clinical administrative sticky notes (e.g. 'prefers morning appointments')."""

    __tablename__ = "patient_notes"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    author_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    body: Mapped[str] = mapped_column(Text)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
