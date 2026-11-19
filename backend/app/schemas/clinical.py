import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORM


class AllergyIn(BaseModel):
    substance: str = Field(min_length=1, max_length=200)
    category: Literal["medication", "food", "environmental", "other"] = "medication"
    reaction: str | None = Field(default=None, max_length=300)
    severity: Literal["mild", "moderate", "severe", "life_threatening"] = "moderate"
    status: Literal["active", "inactive", "entered_in_error"] = "active"
    onset_date: date | None = None


class AllergyOut(AllergyIn, ORM):
    id: uuid.UUID
    created_at: datetime


class MedicationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    dose: str | None = None
    route: str | None = None
    frequency: str | None = None
    indication: str | None = None
    status: Literal["active", "completed", "discontinued", "entered_in_error"] = "active"
    start_date: date | None = None
    end_date: date | None = None


class MedicationOut(MedicationIn, ORM):
    id: uuid.UUID
    source: str
    created_at: datetime


class ProblemIn(BaseModel):
    code: str | None = Field(default=None, max_length=10)
    description: str = Field(min_length=1, max_length=300)
    status: Literal["active", "resolved", "inactive", "entered_in_error"] = "active"
    is_chronic: bool = False
    onset_date: date | None = None
    resolved_date: date | None = None
    encounter_id: uuid.UUID | None = None


class ProblemOut(ProblemIn, ORM):
    id: uuid.UUID
    created_at: datetime


class HistoryIn(BaseModel):
    category: Literal["medical", "surgical", "family", "social"]
    condition: str = Field(min_length=1, max_length=300)
    relation: str | None = None
    details: str | None = None
    occurred_on: str | None = None


class HistoryOut(HistoryIn, ORM):
    id: uuid.UUID
    created_at: datetime


class VitalsIn(BaseModel):
    encounter_id: uuid.UUID | None = None
    measured_at: datetime | None = None
    systolic: int | None = Field(default=None, ge=40, le=300)
    diastolic: int | None = Field(default=None, ge=20, le=200)
    heart_rate: int | None = Field(default=None, ge=20, le=250)
    respiratory_rate: int | None = Field(default=None, ge=4, le=80)
    temperature_c: Decimal | None = Field(default=None, ge=30, le=45)
    spo2: int | None = Field(default=None, ge=50, le=100)
    height_cm: Decimal | None = Field(default=None, ge=20, le=260)
    weight_kg: Decimal | None = Field(default=None, ge=0.5, le=400)
    pain_score: int | None = Field(default=None, ge=0, le=10)


class VitalsOut(VitalsIn, ORM):
    id: uuid.UUID
    measured_at: datetime
    bmi: float | None
    recorded_by_id: uuid.UUID | None


class DiagnosisIn(BaseModel):
    code: str = Field(min_length=3, max_length=10)
    description: str = Field(min_length=1, max_length=300)
    add_to_problem_list: bool = False


class DiagnosisOut(ORM):
    id: uuid.UUID
    code: str
    description: str
    rank: int


class EncounterCreate(BaseModel):
    patient_id: uuid.UUID
    appointment_id: uuid.UUID | None = None
    clinic_id: uuid.UUID | None = None
    encounter_type: Literal["office_visit", "telehealth", "phone", "procedure", "follow_up"] = "office_visit"
    chief_complaint: str | None = Field(default=None, max_length=300)


class EncounterUpdate(BaseModel):
    chief_complaint: str | None = Field(default=None, max_length=300)
    follow_up: str | None = Field(default=None, max_length=300)
    encounter_type: Literal["office_visit", "telehealth", "phone", "procedure", "follow_up"] | None = None


class NoteContent(BaseModel):
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""

    @field_validator("*")
    @classmethod
    def limit(cls, v: str) -> str:
        if len(v) > 20000:
            raise ValueError("Section too long")
        return v


class NoteCreate(BaseModel):
    template_id: uuid.UUID | None = None
    title: str = "Progress note"
    note_type: Literal["soap", "progress", "nursing", "discharge_summary", "consult"] = "soap"


class NoteSave(BaseModel):
    content: NoteContent
    expected_version: int  # optimistic concurrency: reject if someone saved in between
    title: str | None = None
    source: Literal["manual", "ai_scribe", "template"] = "manual"


class NoteSign(BaseModel):
    expected_version: int
    attest_ai_reviewed: bool = False


class AddendumIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class UserRef(BaseModel):
    id: uuid.UUID
    name: str


class AddendumOut(BaseModel):
    id: uuid.UUID
    body: str
    author: UserRef
    created_at: datetime


class NoteOut(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    note_type: str
    title: str
    status: str
    current_version: int
    content: NoteContent
    has_ai_content: bool
    ai_reviewed: bool
    author: UserRef
    signed_by: UserRef | None
    signed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    addenda: list[AddendumOut]


class NoteVersionOut(BaseModel):
    version: int
    content: NoteContent
    source: str
    created_by: UserRef | None
    created_at: datetime


class EncounterOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    patient: dict
    provider: UserRef
    provider_id: uuid.UUID
    clinic_id: uuid.UUID
    appointment_id: uuid.UUID | None
    encounter_type: str
    status: str
    chief_complaint: str | None
    follow_up: str | None
    started_at: datetime
    completed_at: datetime | None
    diagnoses: list[DiagnosisOut]
    note_status: str | None = None


class EncounterDetail(EncounterOut):
    notes: list[NoteOut]
    vitals: list[VitalsOut]


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    specialty: str | None = None
    content: NoteContent
    is_active: bool = True


class TemplateOut(ORM):
    id: uuid.UUID
    name: str
    note_type: str
    specialty: str | None
    content: NoteContent
    is_active: bool
