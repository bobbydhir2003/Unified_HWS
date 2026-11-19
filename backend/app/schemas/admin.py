import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.permissions import Role
from app.schemas.common import ORM


class OrgOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    settings: dict
    created_at: datetime


class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9-]{2,80}$")
    first_clinic_name: str = Field(min_length=2, max_length=200)
    first_clinic_code: str = Field(min_length=1, max_length=20)
    timezone: str = "America/New_York"
    admin_email: EmailStr | None = None
    admin_first_name: str | None = None
    admin_last_name: str | None = None


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    status: str | None = Field(default=None, pattern="^(active|suspended)$")
    settings: dict | None = None


class ClinicOut(ORM):
    id: uuid.UUID
    name: str
    code: str
    timezone: str
    phone: str | None
    address_line1: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    rooms: list[str]
    is_active: bool
    facility_type: str = "clinic"


class ClinicIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str = Field(min_length=1, max_length=20)
    timezone: str = "America/New_York"
    phone: str | None = None
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    rooms: list[str] = []
    is_active: bool = True
    facility_type: Literal["clinic", "hospital", "urgent_care", "surgery_center", "lab", "pharmacy"] = "clinic"


class ProviderInfo(ORM):
    id: uuid.UUID
    npi: str | None
    specialty: str | None
    credentials: str | None
    color: str
    is_active: bool


class StaffOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    title: str | None
    roles: list[str]
    is_active: bool
    all_clinics: bool
    clinic_ids: list[uuid.UUID]
    department_ids: list[uuid.UUID] = []
    mfa_enabled: bool
    last_login_at: datetime | None
    provider: ProviderInfo | None


class ProviderIn(BaseModel):
    npi: str | None = Field(default=None, pattern=r"^\d{10}$")
    specialty: str | None = None
    credentials: str | None = None
    color: str = "blue"
    is_active: bool = True


class StaffUpdate(BaseModel):
    roles: list[Role] | None = None
    is_active: bool | None = None
    all_clinics: bool | None = None
    clinic_ids: list[uuid.UUID] | None = None
    department_ids: list[uuid.UUID] | None = None  # [] = all departments of the allowed facilities
    title: str | None = None
    provider: ProviderIn | None = None

    @field_validator("roles")
    @classmethod
    def non_empty(cls, v):
        if v is not None and not v:
            raise ValueError("At least one role is required")
        return v


class InvitationIn(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    roles: list[Role] = Field(min_length=1)
    clinic_ids: list[uuid.UUID] | None = None


class InvitationOut(ORM):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    roles: list[str]
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class InvitationCreated(InvitationOut):
    invite_link: str  # shown because email delivery is simulated in development


class AuditOut(ORM):
    _ip = field_validator("ip_address", mode="before")(lambda v: str(v) if v is not None else None)

    id: uuid.UUID
    action: str
    actor_user_id: uuid.UUID | None
    actor_name: str | None = None
    resource_type: str | None
    resource_id: str | None
    patient_id: uuid.UUID | None
    outcome: str
    ip_address: str | None = None
    details: dict
    created_at: datetime


class OutboxOut(ORM):
    id: uuid.UUID
    channel: str
    to_address: str
    subject: str
    body: str
    status: str
    created_at: datetime
