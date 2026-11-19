"""Emergency department visits and triage. Triage acuity (ESI) is recorded by nurses — there is no AI triage."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk

ED_STATUSES = ("waiting", "triaged", "roomed", "boarding", "departed")
ED_ACTIVE = ("waiting", "triaged", "roomed", "boarding")
ED_DISPOSITIONS = ("discharged", "admitted", "transferred", "lwbs", "ama", "expired")


class EdVisit(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "ed_visits"
    facility_id: Mapped[uuid.UUID] = fk("clinics.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    arrival_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    arrival_mode: Mapped[str] = mapped_column(String(20), default="walk_in")
    chief_complaint: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(12), default="waiting")
    esi_level: Mapped[int | None] = mapped_column(SmallInteger)
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bed_id: Mapped[uuid.UUID | None] = fk("locations.id", nullable=True, ondelete="SET NULL")
    roomed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_id: Mapped[uuid.UUID | None] = fk("provider_profiles.id", nullable=True, ondelete="SET NULL", index=False)
    provider_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nurse_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    encounter_id: Mapped[uuid.UUID | None] = fk("encounters.id", nullable=True, ondelete="SET NULL", index=False)
    disposition: Mapped[str | None] = mapped_column(String(15))
    disposition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disposition_note: Mapped[str | None] = mapped_column(Text)
    departed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stay_id: Mapped[uuid.UUID | None] = fk("inpatient_stays.id", nullable=True, ondelete="SET NULL", index=False)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    patient = relationship("Patient", lazy="joined")

    __table_args__ = (
        CheckConstraint("status in (" + ",".join(f"'{s}'" for s in ED_STATUSES) + ")", name="status"),
        CheckConstraint("esi_level is null or esi_level between 1 and 5", name="esi"),
        CheckConstraint("arrival_mode in ('walk_in','ambulance','police','transfer','other')", name="arrival_mode"),
        CheckConstraint("disposition is null or disposition in (" + ",".join(f"'{s}'" for s in ED_DISPOSITIONS) + ")", name="disposition"),
        CheckConstraint("status <> 'departed' or (disposition is not null and departed_at is not null)", name="departed_complete"),
        # A bay holds one active ED patient; a patient has one active ED visit.
        Index("uq_ed_bay_active", "bed_id", unique=True, postgresql_where=text("status in ('roomed','boarding') and bed_id is not null")),
        Index("uq_ed_patient_active", "patient_id", unique=True, postgresql_where=text("status in ('waiting','triaged','roomed','boarding')")),
        Index("ix_ed_fac_status", "facility_id", "status"),
    )


class TriageAssessment(UUIDPk, OrgScoped, Base):
    """Append-only triage record (re-triage adds a new row)."""

    __tablename__ = "triage_assessments"
    ed_visit_id: Mapped[uuid.UUID] = fk("ed_visits.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    esi_level: Mapped[int] = mapped_column(SmallInteger)
    complaint: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    vitals_id: Mapped[uuid.UUID | None] = fk("vital_signs.id", nullable=True, ondelete="SET NULL", index=False)
    recorded_by_id: Mapped[uuid.UUID] = fk("users.id", index=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("esi_level between 1 and 5", name="esi"),)
