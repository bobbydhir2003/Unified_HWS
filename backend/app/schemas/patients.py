import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORM

Sex = Literal["female", "male", "intersex", "unknown"]


class InsuranceIn(BaseModel):
    priority: Literal["primary", "secondary", "tertiary"] = "primary"
    payer_name: str = Field(min_length=1, max_length=200)
    plan_name: str | None = None
    member_id: str = Field(min_length=1, max_length=60)
    group_number: str | None = None
    subscriber_name: str | None = None
    subscriber_relation: Literal["self", "spouse", "child", "other"] = "self"
    effective_date: date | None = None
    termination_date: date | None = None
    is_active: bool = True


class InsuranceOut(InsuranceIn, ORM):
    id: uuid.UUID
    eligibility_status: str
    eligibility_checked_at: datetime | None


class PatientBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    preferred_name: str | None = Field(default=None, max_length=100)
    date_of_birth: date
    sex_at_birth: Sex
    gender_identity: str | None = None
    pronouns: str | None = None
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    phone_alt: str | None = Field(default=None, max_length=40)
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    preferred_language: str = "English"
    marital_status: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_relation: str | None = None
    emergency_contact_phone: str | None = None
    primary_clinic_id: uuid.UUID | None = None
    primary_provider_id: uuid.UUID | None = None
    notes: str | None = None

    @field_validator("date_of_birth")
    @classmethod
    def dob_reasonable(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        if v.year < 1900:
            raise ValueError("Date of birth looks incorrect")
        return v

    @field_validator("email", "phone", "middle_name", "preferred_name", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class PatientCreate(PatientBase):
    insurance: InsuranceIn | None = None
    confirm_not_duplicate: bool = False


class PatientUpdate(PatientBase):
    status: Literal["active", "inactive", "deceased"] = "active"


class PatientListItem(ORM):
    id: uuid.UUID
    mrn: str
    first_name: str
    last_name: str
    preferred_name: str | None
    date_of_birth: date
    sex_at_birth: str
    phone: str | None
    email: str | None
    status: str
    is_restricted: bool
    primary_provider_name: str | None = None
    last_visit_at: datetime | None = None


class PatientOut(PatientBase, ORM):
    id: uuid.UUID
    mrn: str
    status: str
    is_restricted: bool
    has_portal_access: bool = False
    created_at: datetime
    updated_at: datetime
    insurances: list[InsuranceOut] = []


class DuplicateCheckIn(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    phone: str | None = None
    email: str | None = None
    exclude_id: uuid.UUID | None = None


class DuplicateCandidate(BaseModel):
    id: uuid.UUID
    mrn: str
    name: str
    date_of_birth: date
    phone: str | None
    reasons: list[str]
    score: float


class BreakGlassIn(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


class PatientNoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    is_pinned: bool = False


class PatientNoteOut(ORM):
    id: uuid.UUID
    body: str
    is_pinned: bool
    author_id: uuid.UUID | None
    author_name: str | None = None
    created_at: datetime
