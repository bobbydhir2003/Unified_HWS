import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk

ROLE_VALUES = (
    "super_admin",
    "clinic_admin",
    "doctor",
    "nurse",
    "receptionist",
    "billing",
    "patient",
    "hospital_admin",
    "pharmacist",
    "lab_tech",
    "radiology_tech",
    "radiologist",
    "bed_manager",
    "insurance_specialist",
)


class Organization(UUIDPk, Timestamps, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    clinics: Mapped[list["Clinic"]] = relationship(back_populates="organization", order_by="Clinic.name")

    __table_args__ = (CheckConstraint("status in ('active','suspended')", name="status"),)


class Clinic(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "clinics"
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    phone: Mapped[str | None] = mapped_column(String(40))
    address_line1: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    rooms: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    facility_type: Mapped[str] = mapped_column(String(20), default="clinic", server_default="clinic")
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")  # per-facility feature flags/config
    organization: Mapped[Organization] = relationship(back_populates="clinics")

    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        CheckConstraint("facility_type in ('clinic','hospital','urgent_care','surgery_center','lab','pharmacy')", name="facility_type"),
    )


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(40))  # e.g. "MD", "RN"
    phone: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64))
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Set only for identities that exist inside ONE private demo hospital (app.demo.sandbox). Such users have no password,
    # can't use password/reset/invitation sign-in, are reachable only through that hospital's demo lease, and are deleted
    # with the hospital (ON DELETE CASCADE).
    sandbox_org_id: Mapped[uuid.UUID | None] = fk("organizations.id", nullable=True)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def display_name(self) -> str:
        return f"{self.full_name}, {self.title}" if self.title else self.full_name


class Membership(UUIDPk, Timestamps, OrgScoped, Base):
    """A user's employment/enrollment in an organization, with one or more roles."""

    __tablename__ = "memberships"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    all_clinics: Mapped[bool] = mapped_column(Boolean, default=True)
    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(lazy="joined")
    roles: Mapped[list["MembershipRole"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    clinics: Mapped[list["MembershipClinic"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    departments: Mapped[list["MembershipDepartment"]] = relationship(cascade="all, delete-orphan", lazy="selectin")  # noqa: F821

    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)

    @property
    def role_names(self) -> list[str]:
        return sorted(r.role for r in self.roles)


class MembershipRole(UUIDPk, Base):
    __tablename__ = "membership_roles"
    membership_id: Mapped[uuid.UUID] = fk("memberships.id")
    role: Mapped[str] = mapped_column(String(30))

    __table_args__ = (
        UniqueConstraint("membership_id", "role"),
        CheckConstraint("role in (" + ",".join(f"'{r}'" for r in ROLE_VALUES) + ")", name="role"),
    )


class MembershipClinic(UUIDPk, Base):
    __tablename__ = "membership_clinics"
    membership_id: Mapped[uuid.UUID] = fk("memberships.id")
    clinic_id: Mapped[uuid.UUID] = fk("clinics.id")
    __table_args__ = (UniqueConstraint("membership_id", "clinic_id"),)


class ProviderProfile(UUIDPk, Timestamps, OrgScoped, Base):
    """Clinician-specific data for users who see patients."""

    __tablename__ = "provider_profiles"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    npi: Mapped[str | None] = mapped_column(String(10))
    specialty: Mapped[str | None] = mapped_column(String(100))
    credentials: Mapped[str | None] = mapped_column(String(40))
    color: Mapped[str] = mapped_column(String(20), default="blue")
    accepts_new_patients: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    user: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)


class UserSession(UUIDPk, Base):
    __tablename__ = "user_sessions"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip_address: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Demo hospital lease this session belongs to (None for ordinary sessions). Checked on every request.
    sandbox_lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)


class Invitation(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "invitations"
    email: Mapped[str] = mapped_column(String(320), index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(30)))
    clinic_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String(36)))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordResetToken(UUIDPk, Base):
    __tablename__ = "password_reset_tokens"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutboundMessage(UUIDPk, Base):
    """Email/SMS outbox. In development nothing is sent externally; messages are viewable in Admin › Outbox."""

    __tablename__ = "outbound_messages"
    organization_id: Mapped[uuid.UUID | None] = fk("organizations.id", nullable=True)
    channel: Mapped[str] = mapped_column(String(10), default="email")
    to_address: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="simulated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEvent(UUIDPk, Base):
    """Append-only (enforced by DB trigger in migration 0001)."""

    __tablename__ = "audit_events"
    organization_id: Mapped[uuid.UUID | None] = fk("organizations.id", nullable=True, ondelete=None)
    actor_user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete=None)
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(60))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    patient_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    outcome: Mapped[str] = mapped_column(String(20), default="success")
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(400))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Notification(UUIDPk, OrgScoped, Base):
    __tablename__ = "notifications"
    user_id: Mapped[uuid.UUID] = fk("users.id")
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(String(500))
    link: Mapped[str | None] = mapped_column(String(300))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
