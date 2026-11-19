import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk
from app.models.identity import ProviderProfile, User
from app.models.patients import Patient


class Allergy(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "allergies"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    substance: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20), default="medication")
    reaction: Mapped[str | None] = mapped_column(String(300))
    severity: Mapped[str] = mapped_column(String(20), default="moderate")
    status: Mapped[str] = mapped_column(String(20), default="active")
    onset_date: Mapped[date | None] = mapped_column(Date)
    recorded_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")

    __table_args__ = (
        CheckConstraint("severity in ('mild','moderate','severe','life_threatening')", name="severity"),
        CheckConstraint("status in ('active','inactive','entered_in_error')", name="status"),
        CheckConstraint("category in ('medication','food','environmental','other')", name="category"),
    )


class PatientMedication(UUIDPk, Timestamps, OrgScoped, Base):
    """Medication list entry (what the patient takes). Prescriptions/orders come in phase 7."""

    __tablename__ = "patient_medications"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    name: Mapped[str] = mapped_column(String(200))
    dose: Mapped[str | None] = mapped_column(String(60))
    route: Mapped[str | None] = mapped_column(String(40))
    frequency: Mapped[str | None] = mapped_column(String(100))
    indication: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(30), default="reported")  # reported | prescribed | imported
    recorded_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")

    __table_args__ = (
        CheckConstraint("status in ('active','completed','discontinued','entered_in_error')", name="status"),
    )


class Problem(UUIDPk, Timestamps, OrgScoped, Base):
    """Problem list / diagnoses. ICD-10-CM code optional for free-text entries."""

    __tablename__ = "problems"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    code: Mapped[str | None] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="active")
    is_chronic: Mapped[bool] = mapped_column(Boolean, default=False)
    onset_date: Mapped[date | None] = mapped_column(Date)
    resolved_date: Mapped[date | None] = mapped_column(Date)
    encounter_id: Mapped[uuid.UUID | None] = fk("encounters.id", nullable=True, ondelete="SET NULL")
    recorded_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")

    __table_args__ = (
        CheckConstraint("status in ('active','resolved','inactive','entered_in_error')", name="status"),
    )


class HistoryEntry(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "history_entries"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    category: Mapped[str] = mapped_column(String(20))
    condition: Mapped[str] = mapped_column(String(300))
    relation: Mapped[str | None] = mapped_column(String(60))  # family history only
    details: Mapped[str | None] = mapped_column(Text)
    occurred_on: Mapped[str | None] = mapped_column(String(40))  # free-text dates ("2015", "childhood")
    recorded_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")

    __table_args__ = (
        CheckConstraint("category in ('medical','surgical','family','social')", name="category"),
    )


class Encounter(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "encounters"
    clinic_id: Mapped[uuid.UUID] = fk("clinics.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    provider_id: Mapped[uuid.UUID] = fk("provider_profiles.id")
    appointment_id: Mapped[uuid.UUID | None] = fk("appointments.id", nullable=True, ondelete="SET NULL")
    encounter_type: Mapped[str] = mapped_column(String(30), default="office_visit")
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    chief_complaint: Mapped[str | None] = mapped_column(String(300))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    follow_up: Mapped[str | None] = mapped_column(String(300))

    patient: Mapped[Patient] = relationship(lazy="joined")
    provider: Mapped[ProviderProfile] = relationship(lazy="joined")
    diagnoses: Mapped[list["EncounterDiagnosis"]] = relationship(
        cascade="all, delete-orphan", order_by="EncounterDiagnosis.rank", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("status in ('in_progress','completed','cancelled')", name="status"),
        UniqueConstraint("appointment_id"),
    )


class EncounterDiagnosis(UUIDPk, OrgScoped, Base):
    __tablename__ = "encounter_diagnoses"
    encounter_id: Mapped[uuid.UUID] = fk("encounters.id")
    code: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(String(300))
    rank: Mapped[int] = mapped_column(SmallInteger, default=1)

    __table_args__ = (UniqueConstraint("encounter_id", "code"),)


class VitalSigns(UUIDPk, OrgScoped, Base):
    __tablename__ = "vital_signs"
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    encounter_id: Mapped[uuid.UUID | None] = fk("encounters.id", nullable=True, ondelete="SET NULL")
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    systolic: Mapped[int | None] = mapped_column(SmallInteger)
    diastolic: Mapped[int | None] = mapped_column(SmallInteger)
    heart_rate: Mapped[int | None] = mapped_column(SmallInteger)
    respiratory_rate: Mapped[int | None] = mapped_column(SmallInteger)
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    spo2: Mapped[int | None] = mapped_column(SmallInteger)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    pain_score: Mapped[int | None] = mapped_column(SmallInteger)
    recorded_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("systolic is null or systolic between 40 and 300", name="systolic"),
        CheckConstraint("diastolic is null or diastolic between 20 and 200", name="diastolic"),
        CheckConstraint("heart_rate is null or heart_rate between 20 and 250", name="hr"),
        CheckConstraint("spo2 is null or spo2 between 50 and 100", name="spo2"),
        CheckConstraint("pain_score is null or pain_score between 0 and 10", name="pain"),
    )

    @property
    def bmi(self) -> float | None:
        if self.height_cm and self.weight_kg:
            m = float(self.height_cm) / 100
            return round(float(self.weight_kg) / (m * m), 1)
        return None


class ClinicalTemplate(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "clinical_templates"
    name: Mapped[str] = mapped_column(String(120))
    note_type: Mapped[str] = mapped_column(String(30), default="soap")
    specialty: Mapped[str | None] = mapped_column(String(80))
    content: Mapped[dict] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ClinicalNote(UUIDPk, Timestamps, OrgScoped, Base):
    """Once status='signed' the row is frozen by a DB trigger; corrections go into addenda."""

    __tablename__ = "clinical_notes"
    encounter_id: Mapped[uuid.UUID] = fk("encounters.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    author_id: Mapped[uuid.UUID] = fk("users.id", ondelete=None)
    note_type: Mapped[str] = mapped_column(String(30), default="soap")
    title: Mapped[str] = mapped_column(String(200), default="Progress note")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[dict] = mapped_column(JSONB, default=dict)  # mirrors latest version
    has_ai_content: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete=None)

    author: Mapped[User] = relationship(foreign_keys=[author_id], lazy="joined")
    signed_by: Mapped[User | None] = relationship(foreign_keys=[signed_by_id], lazy="joined")
    addenda: Mapped[list["NoteAddendum"]] = relationship(order_by="NoteAddendum.created_at", lazy="selectin")

    __table_args__ = (CheckConstraint("status in ('draft','signed')", name="status"),)


class ClinicalNoteVersion(UUIDPk, OrgScoped, Base):
    """Immutable snapshot of a note at each save (trigger blocks UPDATE/DELETE)."""

    __tablename__ = "clinical_note_versions"
    note_id: Mapped[uuid.UUID] = fk("clinical_notes.id")
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | ai_scribe | template | sign
    created_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    created_by: Mapped[User | None] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("note_id", "version"),)


class NoteAddendum(UUIDPk, OrgScoped, Base):
    __tablename__ = "note_addenda"
    note_id: Mapped[uuid.UUID] = fk("clinical_notes.id")
    author_id: Mapped[uuid.UUID] = fk("users.id", ondelete=None)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author: Mapped[User] = relationship(lazy="joined")
