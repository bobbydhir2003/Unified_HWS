"""Hospital structure: Organization → Facility (table `clinics`) → Department → Location tree (unit → room → bed).

The historical `clinics` table *is* the facility table (a clinic is a facility of type `clinic`); keeping the name
avoids a destructive rename across 50+ tables. New code and the UI call it "facility".
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk

FACILITY_TYPES = ("clinic", "hospital", "urgent_care", "surgery_center", "lab", "pharmacy")
DEPARTMENT_KINDS = ("outpatient", "emergency", "inpatient", "icu", "surgery", "pharmacy", "laboratory", "radiology",
                    "billing", "administration", "support")
LOCATION_KINDS = ("unit", "room", "bed", "bay", "or_room", "storage", "area")
BED_STATUSES = ("available", "occupied", "reserved", "cleaning", "blocked")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} in (" + ",".join(f"'{v}'" for v in values) + ")"


class Department(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "departments"
    facility_id: Mapped[uuid.UUID] = fk("clinics.id")
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20), default="outpatient")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (UniqueConstraint("facility_id", "code"), CheckConstraint(_in("kind", DEPARTMENT_KINDS), name="kind"))


class Location(UUIDPk, Timestamps, OrgScoped, Base):
    """A physical place. Beds carry operational status; occupancy itself lives in bed_assignments (Milestone B)."""

    __tablename__ = "locations"
    facility_id: Mapped[uuid.UUID] = fk("clinics.id")
    department_id: Mapped[uuid.UUID | None] = fk("departments.id", nullable=True, ondelete="SET NULL")
    parent_id: Mapped[uuid.UUID | None] = fk("locations.id", nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(40))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)  # e.g. {"isolation": true, "telemetry": true}
    bed_status: Mapped[str | None] = mapped_column(String(20))
    bed_status_reason: Mapped[str | None] = mapped_column(String(200))
    bed_status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    children: Mapped[list["Location"]] = relationship(order_by="Location.sort_order")

    __table_args__ = (
        UniqueConstraint("facility_id", "code"),
        CheckConstraint(_in("kind", LOCATION_KINDS), name="kind"),
        CheckConstraint("(kind = 'bed') = (bed_status is not null)", name="bed_status_only_beds"),
        CheckConstraint("bed_status is null or " + _in("bed_status", BED_STATUSES), name="bed_status"),
        Index("ix_locations_facility_kind", "facility_id", "kind"),
    )


class MembershipDepartment(UUIDPk, Base):
    """Optional department scope. A membership with no rows here may act in every department of its facilities."""

    __tablename__ = "membership_departments"
    membership_id: Mapped[uuid.UUID] = fk("memberships.id")
    department_id: Mapped[uuid.UUID] = fk("departments.id")
    __table_args__ = (UniqueConstraint("membership_id", "department_id"),)
