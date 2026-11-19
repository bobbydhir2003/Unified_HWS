"""Request authentication and tenant context.

Every tenant-scoped endpoint depends on `TenantContext`; it resolves the active organization from the
`X-Organization-Id` header, verifies the caller's membership, and exposes permission + clinic checks.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import bind_tenant, get_db
from app.core.errors import forbidden
from app.core.permissions import Role, permissions_for
from app.core.security import decode_token, now
from app.models import Membership, ProviderProfile, User, UserSession
from app.services import audit
from app.services.identity import mfa_enrollment_required

bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthUser:
    user: User
    session_id: uuid.UUID


def get_auth_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> AuthUser:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )
    if not creds:
        raise unauthorized
    data = decode_token(creds.credentials, "access")
    if not data:
        raise unauthorized
    sess = db.get(UserSession, uuid.UUID(data["sid"]))
    if not sess or sess.revoked_at or sess.expires_at < now():
        raise unauthorized
    user = db.get(User, uuid.UUID(data["sub"]))
    if not user or not user.is_active:
        raise unauthorized
    return AuthUser(user=user, session_id=sess.id)


@dataclass
class TenantContext:
    db: Session
    request: Request
    user: User
    session_id: uuid.UUID
    org_id: uuid.UUID
    roles: list[str]
    permissions: set[str]
    clinic_ids: list[uuid.UUID] | None  # None = all facilities in the org ("clinic" = facility)
    membership: Membership | None = None
    department_ids: list[uuid.UUID] | None = None  # None = every department of the allowed facilities
    _provider: Any = field(default=None, repr=False)

    def can(self, perm: str) -> bool:
        return perm in self.permissions

    def require(self, *perms: str) -> None:
        missing = [p for p in perms if p not in self.permissions]
        if missing:
            audit.record(
                self.db, "access.denied", org_id=self.org_id, actor_id=self.user.id, outcome="denied",
                request=self.request, details={"missing": missing, "path": self.request.url.path},
            )
            self.db.commit()
            raise forbidden()

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @property
    def is_patient_only(self) -> bool:
        return self.roles == [Role.PATIENT]

    def clinic_allowed(self, clinic_id: uuid.UUID | None) -> bool:
        return clinic_id is None or self.clinic_ids is None or clinic_id in self.clinic_ids

    def require_clinic(self, clinic_id: uuid.UUID | None) -> None:
        if not self.clinic_allowed(clinic_id):
            raise forbidden("You do not have access to this clinic")

    # Facility vocabulary for hospital modules (same scope as clinics).
    @property
    def facility_ids(self) -> list[uuid.UUID] | None:
        return self.clinic_ids

    def facility_allowed(self, facility_id: uuid.UUID | None) -> bool:
        return self.clinic_allowed(facility_id)

    def require_facility(self, facility_id: uuid.UUID | None) -> None:
        if not self.clinic_allowed(facility_id):
            raise forbidden("You do not have access to this facility")

    def department_allowed(self, department_id: uuid.UUID | None) -> bool:
        return department_id is None or self.department_ids is None or department_id in self.department_ids

    def require_department(self, department_id: uuid.UUID | None) -> None:
        if not self.department_allowed(department_id):
            raise forbidden("You do not have access to this department")

    @property
    def provider(self) -> ProviderProfile | None:
        if self._provider is None:
            self._provider = self.db.scalar(
                select(ProviderProfile).where(
                    ProviderProfile.organization_id == self.org_id, ProviderProfile.user_id == self.user.id
                )
            ) or False
        return self._provider or None

    def audit(self, action: str, **kw) -> None:
        audit.record(self.db, action, org_id=self.org_id, actor_id=self.user.id, request=self.request, **kw)


def get_ctx(
    request: Request,
    auth: AuthUser = Depends(get_auth_user),
    db: Session = Depends(get_db),
    x_organization_id: str | None = Header(default=None),
) -> TenantContext:
    user = auth.user
    if mfa_enrollment_required(user):
        raise HTTPException(403, {"code": "mfa_enrollment_required",
                                  "message": "Set up two-factor authentication to continue."})
    memberships = [m for m in user.memberships if m.is_active]
    org_id: uuid.UUID | None = None
    if x_organization_id:
        try:
            org_id = uuid.UUID(x_organization_id)
        except ValueError:
            raise HTTPException(400, "Invalid X-Organization-Id") from None
    elif len(memberships) == 1:
        org_id = memberships[0].organization_id
    if org_id is None:
        raise HTTPException(400, "X-Organization-Id header required")

    membership = next((m for m in memberships if m.organization_id == org_id), None)
    if membership:
        roles = membership.role_names
        clinic_ids = None if membership.all_clinics else [c.clinic_id for c in membership.clinics]
        department_ids = [d.department_id for d in membership.departments] or None
    elif user.is_superadmin:
        roles, clinic_ids, department_ids = [Role.SUPER_ADMIN.value], None, None
    else:
        raise forbidden("You are not a member of this organization")
    if user.is_superadmin and Role.SUPER_ADMIN.value not in roles:
        roles = sorted([*roles, Role.SUPER_ADMIN.value])

    bind_tenant(db, org_id)  # PostgreSQL RLS: every statement from here on is limited to this organization
    return TenantContext(
        db=db, request=request, user=user, session_id=auth.session_id, org_id=org_id, roles=roles,
        permissions=permissions_for(roles), clinic_ids=clinic_ids, membership=membership,
        department_ids=department_ids,
    )


def require(*perms: str):
    def dep(ctx: TenantContext = Depends(get_ctx)) -> TenantContext:
        ctx.require(*perms)
        return ctx

    return dep
