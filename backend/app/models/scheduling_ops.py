"""Operating rooms & staff rostering (B11).

DB invariants (migration 0022): an OR room can't host overlapping cases (including turnover), a surgeon can't be in two
cases at once, and a staff member can't hold overlapping shifts. Suggestions never override these hard constraints.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk


class SurgicalCase(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "surgical_cases"
    facility_id: Mapped[uuid.UUID] = fk("clinics.id")
    or_room_id: Mapped[uuid.UUID] = fk("locations.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    surgeon_provider_id: Mapped[uuid.UUID] = fk("provider_profiles.id")
    procedure: Mapped[str] = mapped_column(String(200))
    procedure_code: Mapped[str | None] = mapped_column(String(10))
    priority: Mapped[str] = mapped_column(String(10), default="elective")
    anesthesia: Mapped[str] = mapped_column(String(15), default="general")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    turnover_minutes: Mapped[int] = mapped_column(Integer, default=30)
    blocked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # end_at + turnover (room unavailable until)
    status: Mapped[str] = mapped_column(String(12), default="scheduled")
    in_room_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    patient = relationship("Patient", lazy="joined")
    surgeon = relationship("ProviderProfile", lazy="joined")

    __table_args__ = (
        CheckConstraint("end_at > start_at", name="range"),
        CheckConstraint("status in ('scheduled','in_room','completed','cancelled')", name="status"),
        CheckConstraint("priority in ('elective','urgent','emergent')", name="priority"),
        CheckConstraint("turnover_minutes between 0 and 240", name="turnover"),
        CheckConstraint("blocked_until >= end_at", name="blocked_until"),
        Index("ix_surgical_cases_room_time", "or_room_id", "start_at"),
    )


class Shift(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "shifts"
    facility_id: Mapped[uuid.UUID] = fk("clinics.id")
    department_id: Mapped[uuid.UUID] = fk("departments.id")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    role: Mapped[str] = mapped_column(String(30))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12), default="scheduled")
    notes: Mapped[str | None] = mapped_column(String(300))
    created_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    user = relationship("User", lazy="joined", foreign_keys=[user_id])

    __table_args__ = (
        CheckConstraint("end_at > start_at and end_at - start_at <= interval '16 hours'", name="range"),
        CheckConstraint("status in ('scheduled','cancelled')", name="status"),
        Index("ix_shifts_dept_time", "department_id", "start_at"),
    )


class StaffSkill(UUIDPk, OrgScoped, Base):
    __tablename__ = "staff_skills"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    skill: Mapped[str] = mapped_column(String(40))  # e.g. ICU, ACLS, PALS, charge, OR_circulator
    expires_on: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (UniqueConstraint("user_id", "skill"),)


class TimeOff(UUIDPk, OrgScoped, Base):
    __tablename__ = "time_off"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (CheckConstraint("end_at > start_at", name="range"),)


class SwapRequest(UUIDPk, Timestamps, OrgScoped, Base):
    """Shift swap/cover: requester offers a shift; a colleague accepts; a manager approves (reassigns the shift)."""

    __tablename__ = "shift_swap_requests"
    shift_id: Mapped[uuid.UUID] = fk("shifts.id")
    requested_by_id: Mapped[uuid.UUID] = fk("users.id", index=False)
    target_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | accepted | approved | rejected | cancelled
    reason: Mapped[str | None] = mapped_column(String(300))
    decided_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("status in ('open','accepted','approved','rejected','cancelled')", name="status"),)
