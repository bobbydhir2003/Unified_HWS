import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORM


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class MfaVerifyIn(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=8)


class ClinicBrief(ORM):
    id: uuid.UUID
    name: str
    code: str
    timezone: str


class MembershipOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    roles: list[str]
    permissions: list[str]
    clinics: list[ClinicBrief]
    provider_id: uuid.UUID | None = None
    patient_id: uuid.UUID | None = None


class UserOut(ORM):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    title: str | None
    phone: str | None
    is_superadmin: bool
    mfa_enabled: bool
    last_login_at: datetime | None
    preferences: dict


class MeOut(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]
    mfa_enrollment_required: bool = False
    demo_hospital: bool = False  # an identity of a private demo hospital (GET /auth/demo/session for the details)


class TokenOut(BaseModel):
    status: Literal["ok"] = "ok"
    access_token: str
    expires_in: int
    me: MeOut


class MfaChallengeOut(BaseModel):
    status: Literal["mfa_required"] = "mfa_required"
    mfa_token: str


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=10, max_length=200)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaDisableIn(BaseModel):
    password: str
    code: str


class SessionOut(ORM):
    _ip = field_validator("ip_address", mode="before")(lambda v: str(v) if v is not None else None)

    id: uuid.UUID
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    current: bool = False


class InvitationPreview(BaseModel):
    email: str
    first_name: str
    last_name: str
    organization_name: str
    roles: list[str]
    existing_account: bool


class AcceptInviteIn(BaseModel):
    token: str
    password: str | None = Field(default=None, max_length=200)


class ProfileUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=40)
    preferences: dict | None = None
