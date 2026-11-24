import uuid
from datetime import timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import ROLE_LABELS, Role, permissions_for
from app.core.security import create_token, hash_token, new_opaque_token, now
from app.models import Clinic, Patient, ProviderProfile, User, UserSession
from app.schemas.auth import ClinicBrief, MembershipOut, MeOut, TokenOut, UserOut, WorkspaceOut
from app.services.audit import client_ip

REFRESH_COOKIE = "ud_refresh"


def workspace_roles(user: User, member_roles: list[str]) -> list[str]:
    """Roles selectable in the header switcher (single definition, also enforced in app.api.deps.get_ctx): every role for
    a platform Super Admin; otherwise only the roles the membership grants."""
    if user.is_superadmin:
        return [r.value for r in Role]
    return list(member_roles)


def mfa_enrollment_required(user: User) -> bool:
    if not settings.enforce_mfa or user.mfa_enabled:
        return False
    roles = {r for m in user.memberships for r in m.role_names}
    if user.is_superadmin:
        roles.add("super_admin")
    return bool(roles & set(settings.mfa_required_roles))


def build_me(db: Session, user: User) -> MeOut:
    out: list[MembershipOut] = []
    for m in user.memberships:
        if not m.is_active or m.organization is None:
            continue
        q = select(Clinic).where(Clinic.organization_id == m.organization_id, Clinic.is_active.is_(True))
        if not m.all_clinics:
            q = q.where(Clinic.id.in_([c.clinic_id for c in m.clinics]))
        clinics = db.scalars(q.order_by(Clinic.name)).all()
        roles = m.role_names
        if user.is_superadmin and "super_admin" not in roles:
            roles = sorted([*roles, "super_admin"])
        provider_id = db.scalar(
            select(ProviderProfile.id).where(
                ProviderProfile.organization_id == m.organization_id, ProviderProfile.user_id == user.id
            )
        )
        patient_id = db.scalar(
            select(Patient.id).where(Patient.organization_id == m.organization_id, Patient.portal_user_id == user.id)
        )
        allowed = workspace_roles(user, roles)
        out.append(
            MembershipOut(
                organization_id=m.organization_id,
                organization_name=m.organization.name,
                roles=roles,
                permissions=sorted(permissions_for(roles)),
                clinics=[ClinicBrief.model_validate(c) for c in clinics],
                provider_id=provider_id,
                patient_id=patient_id,
                workspaces=[WorkspaceOut(role=r, label=ROLE_LABELS[Role(r)], permissions=sorted(permissions_for([r])))
                            for r in allowed] if len(allowed) > 1 else [],
            )
        )
    return MeOut(user=UserOut.model_validate(user), memberships=out,
                 mfa_enrollment_required=mfa_enrollment_required(user))


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE, token, httponly=True, secure=settings.cookie_secure, samesite="strict",
        path="/api", max_age=settings.refresh_token_days * 86400,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api")


def access_token_for(user: User, session_id: uuid.UUID) -> str:
    return create_token(str(user.id), "access", settings.access_token_minutes, {"sid": str(session_id)})


def issue_session(db: Session, user: User, request: Request, response: Response) -> TokenOut:
    refresh = new_opaque_token()
    ts = now()
    sess = UserSession(
        user_id=user.id, refresh_token_hash=hash_token(refresh),
        user_agent=request.headers.get("user-agent", "")[:400], ip_address=client_ip(request),
        created_at=ts, last_used_at=ts, expires_at=ts + timedelta(days=settings.refresh_token_days),
    )
    db.add(sess)
    user.last_login_at = ts
    user.failed_login_count = 0
    user.locked_until = None
    db.flush()
    set_refresh_cookie(response, refresh)
    return TokenOut(access_token=access_token_for(user, sess.id), expires_in=settings.access_token_minutes * 60,
                    me=build_me(db, user))


def send_email(db: Session, to: str, subject: str, body: str, org_id: uuid.UUID | None = None) -> None:
    """Delivered through the configured message gateway (default: development outbox — stored, never sent)."""
    from app.integrations.adapters import message_gateway

    message_gateway().send(db, channel="email", to=to, subject=subject, body=body, org_id=org_id)
