import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, SmallInteger, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk
from app.models.identity import Clinic, ProviderProfile
from app.models.patients import Patient

APPOINTMENT_STATUSES = (
    "scheduled",
    "confirmed",
    "checked_in",
    "roomed",
    "in_progress",
    "completed",
    "checked_out",
    "cancelled",
    "no_show",
)
INACTIVE_APPOINTMENT_STATUSES = ("cancelled", "no_show")


class AppointmentType(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "appointment_types"
    name: Mapped[str] = mapped_column(String(100))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=20)
    color: Mapped[str] = mapped_column(String(20), default="blue")
    is_telehealth: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProviderAvailability(UUIDPk, OrgScoped, Base):
    """Recurring weekly working hours for a provider at a clinic. weekday: 0=Mon … 6=Sun (clinic local time)."""

    __tablename__ = "provider_availability"
    provider_id: Mapped[uuid.UUID] = fk("provider_profiles.id")
    clinic_id: Mapped[uuid.UUID] = fk("clinics.id")
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    __table_args__ = (
        CheckConstraint("weekday between 0 and 6", name="weekday"),
        CheckConstraint("end_time > start_time", name="time_order"),
    )


class Appointment(UUIDPk, Timestamps, OrgScoped, Base):
    """Double-booking is prevented by a gist exclusion constraint (see migration 0002)."""

    __tablename__ = "appointments"
    clinic_id: Mapped[uuid.UUID] = fk("clinics.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    provider_id: Mapped[uuid.UUID] = fk("provider_profiles.id")
    appointment_type_id: Mapped[uuid.UUID | None] = fk("appointment_types.id", nullable=True, ondelete="SET NULL")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    mode: Mapped[str] = mapped_column(String(20), default="in_person")
    reason: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    room: Mapped[str | None] = mapped_column(String(40))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    roomed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    booked_via: Mapped[str] = mapped_column(String(10), default="staff", server_default="staff")  # staff | portal
    booked_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    rescheduled_from_id: Mapped[uuid.UUID | None] = fk("appointments.id", nullable=True, ondelete="SET NULL")

    patient: Mapped[Patient] = relationship(lazy="joined")
    provider: Mapped[ProviderProfile] = relationship(lazy="joined")
    clinic: Mapped[Clinic] = relationship(lazy="joined")
    appointment_type: Mapped[AppointmentType | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("end_at > start_at", name="time_order"),
        CheckConstraint("status in (" + ",".join(f"'{s}'" for s in APPOINTMENT_STATUSES) + ")", name="status"),
        CheckConstraint("mode in ('in_person','telehealth')", name="mode"),
        Index("ix_appointments_org_start", "organization_id", "start_at"),
        Index("ix_appointments_provider_start", "provider_id", "start_at"),
    )
