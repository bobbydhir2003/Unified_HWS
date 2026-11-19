"""Inpatient stays, ADT (admission/transfer/discharge) and bed occupancy.

Invariants enforced by PostgreSQL (migration 0014):
- a bed is occupied by at most one stay at any instant (gist exclusion on bed_id × time range),
- a stay holds at most one current bed (partial unique on stay_id where end_at is null),
- a patient has at most one active stay (partial unique on patient_id for active statuses),
- adt_events and bed_status_events are append-only.
"""

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk

STAY_STATUSES = ("pending", "admitted", "discharge_ordered", "discharged", "cancelled")
STAY_ACTIVE = ("pending", "admitted", "discharge_ordered")
DISPOSITIONS = ("home", "home_health", "snf", "rehab", "hospice", "transfer", "ama", "expired", "other")


class InpatientStay(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "inpatient_stays"
    facility_id: Mapped[uuid.UUID] = fk("clinics.id")
    department_id: Mapped[uuid.UUID | None] = fk("departments.id", nullable=True, ondelete="SET NULL")
    requested_department_id: Mapped[uuid.UUID | None] = fk("departments.id", nullable=True, ondelete="SET NULL", index=False)
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    attending_provider_id: Mapped[uuid.UUID | None] = fk("provider_profiles.id", nullable=True, ondelete="SET NULL")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    admit_source: Mapped[str] = mapped_column(String(20), default="direct")  # ed | direct | elective | transfer_in
    level_of_care: Mapped[str] = mapped_column(String(20), default="med_surg")  # med_surg | telemetry | icu | observation
    reason: Mapped[str] = mapped_column(String(300))
    isolation: Mapped[str | None] = mapped_column(String(30))  # contact | droplet | airborne
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    requested_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_discharge_date: Mapped[date | None] = mapped_column(Date)
    discharge_ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discharge_ordered_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    discharge_disposition: Mapped[str | None] = mapped_column(String(20))
    discharged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    ed_visit_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    encounter_id: Mapped[uuid.UUID | None] = fk("encounters.id", nullable=True, ondelete="SET NULL")  # inpatient documentation
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    patient = relationship("Patient", lazy="joined")
    attending = relationship("ProviderProfile", lazy="joined")

    __table_args__ = (
        CheckConstraint("status in (" + ",".join(f"'{s}'" for s in STAY_STATUSES) + ")", name="status"),
        CheckConstraint("admit_source in ('ed','direct','elective','transfer_in')", name="admit_source"),
        CheckConstraint("discharge_disposition is null or discharge_disposition in (" + ",".join(f"'{s}'" for s in DISPOSITIONS) + ")",
                        name="disposition"),
        CheckConstraint("status <> 'discharged' or discharged_at is not null", name="discharged_has_time"),
        Index("ix_stays_org_admitted", "organization_id", "admitted_at"),  # volume/forecast queries
        Index("ix_stays_org_discharged", "organization_id", "discharged_at"),
        Index("uq_stays_one_active_per_patient", "patient_id", unique=True,
              postgresql_where=text("status in ('pending','admitted','discharge_ordered')")),
        Index("ix_stays_org_fac_status", "organization_id", "facility_id", "status"),
    )


class BedAssignment(UUIDPk, OrgScoped, Base):
    __tablename__ = "bed_assignments"
    stay_id: Mapped[uuid.UUID] = fk("inpatient_stays.id")
    bed_id: Mapped[uuid.UUID] = fk("locations.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(20), default="admit")  # admit | transfer
    assigned_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)

    __table_args__ = (
        CheckConstraint("end_at is null or end_at >= start_at", name="range"),
        Index("uq_bed_assign_one_current_per_stay", "stay_id", unique=True, postgresql_where=text("end_at is null")),
    )


class AdtEvent(UUIDPk, OrgScoped, Base):
    """Append-only patient movement / ADT history (the HL7 ADT^A01/A02/A03 equivalents, internal)."""

    __tablename__ = "adt_events"
    stay_id: Mapped[uuid.UUID] = fk("inpatient_stays.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    kind: Mapped[str] = mapped_column(String(30))
    from_bed_id: Mapped[uuid.UUID | None] = fk("locations.id", nullable=True, ondelete="SET NULL", index=False)
    to_bed_id: Mapped[uuid.UUID | None] = fk("locations.id", nullable=True, ondelete="SET NULL", index=False)
    actor_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    note: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint(
        "kind in ('admission_requested','admitted','transferred','discharge_ordered','discharge_order_cancelled','discharged','cancelled')",
        name="kind"),)


class BedStatusEvent(UUIDPk, OrgScoped, Base):
    __tablename__ = "bed_status_events"
    bed_id: Mapped[uuid.UUID] = fk("locations.id")
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(200))
    actor_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CareTeamMember(UUIDPk, OrgScoped, Base):
    __tablename__ = "care_team_members"
    stay_id: Mapped[uuid.UUID] = fk("inpatient_stays.id")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    role: Mapped[str] = mapped_column(String(20))  # attending | resident | nurse | case_manager | pharmacist | therapist | other
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user = relationship("User", lazy="joined")

    __table_args__ = (Index("uq_care_team_active", "stay_id", "user_id", "role", unique=True, postgresql_where=text("end_at is null")),)


DISCHARGE_ITEM_STATUSES = ("pending", "in_progress", "done", "not_applicable")


class DischargePlan(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "discharge_plans"
    stay_id: Mapped[uuid.UUID] = fk("inpatient_stays.id")
    status: Mapped[str] = mapped_column(String(12), default="active")  # active | complete | cancelled
    target_departure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    instructions_text: Mapped[str | None] = mapped_column(Text)  # clinician-approved patient instructions
    instructions_source: Mapped[str | None] = mapped_column(String(20))  # manual | ai_draft_approved
    instructions_approved_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    instructions_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list["DischargePlanItem"]] = relationship(order_by="DischargePlanItem.sort_order", lazy="selectin")

    __table_args__ = (Index("uq_discharge_plan_stay", "stay_id", unique=True),
                      CheckConstraint("status in ('active','complete','cancelled')", name="status"))


class DischargePlanItem(UUIDPk, OrgScoped, Base):
    __tablename__ = "discharge_plan_items"
    plan_id: Mapped[uuid.UUID] = fk("discharge_plans.id")
    key: Mapped[str] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(200))
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_role: Mapped[str] = mapped_column(String(30))
    verification: Mapped[str] = mapped_column(String(10), default="manual")  # auto (computed from data) | manual (attested)
    status: Mapped[str] = mapped_column(String(15), default="pending")
    sort_order: Mapped[int] = mapped_column(default=0)
    note: Mapped[str | None] = mapped_column(String(500))
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    task_id: Mapped[uuid.UUID | None] = fk("tasks.id", nullable=True, ondelete="SET NULL", index=False)
    completed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("plan_id", "key"),
                      CheckConstraint("status in (" + ",".join(f"'{s}'" for s in DISCHARGE_ITEM_STATUSES) + ")", name="status"))


class HandoffNote(UUIDPk, OrgScoped, Base):
    """Nursing shift handoff (SBAR). Append-only; corrections are new notes."""

    __tablename__ = "handoff_notes"
    stay_id: Mapped[uuid.UUID] = fk("inpatient_stays.id")
    author_id: Mapped[uuid.UUID] = fk("users.id", index=False)
    shift: Mapped[str] = mapped_column(String(10))  # day | evening | night
    situation: Mapped[str] = mapped_column(Text)
    background: Mapped[str | None] = mapped_column(Text)
    assessment: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    acknowledged_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
