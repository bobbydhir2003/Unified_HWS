import uuid
from datetime import timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import permissions_for
from app.core.security import create_token, hash_token, new_opaque_token, now
from app.models import Clinic, Patient, ProviderProfile, User, UserSession
from app.schemas.auth import ClinicBrief, MembershipOut, MeOut, TokenOut, UserOut
from app.services.audit import client_ip

REFRESH_COOKIE = "ud_refresh"


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
        out.append(
            MembershipOut(
                organization_id=m.organization_id,
                organization_name=m.organization.name,
                roles=roles,
                permissions=sorted(permissions_for(roles)),
                clinics=[ClinicBrief.model_validate(c) for c in clinics],
                provider_id=provider_id,
                patient_id=patient_id,
            )
        )
    return MeOut(user=UserOut.model_validate(user), memberships=out,
                 mfa_enrollment_required=mfa_enrollment_required(user), demo_hospital=user.sandbox_org_id is not None)


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE, token, httponly=True, secure=settings.cookie_secure, samesite="strict",
        path="/api", max_age=settings.refresh_token_days * 86400,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api")


def access_token_for(user: User, session_id: uuid.UUID, *, sandbox_lease_id: uuid.UUID | None = None,
                     ai_root: uuid.UUID | None = None) -> str:
    extra = {"sid": str(session_id)}
    if sandbox_lease_id:  # demo hospital session: lease (checked server-side every request) + the key of its demo AI scope
        extra.update(sbx=str(sandbox_lease_id), air=str(ai_root or session_id))
    return create_token(str(user.id), "access", settings.access_token_minutes, extra)


def session_token(db: Session, user: User, sess: UserSession) -> str:
    """Access token for an existing session (refresh), carrying the same demo-lease claims it was issued with."""
    if sess.sandbox_lease_id:
        from app.models import DemoSandbox

        root = db.scalar(select(DemoSandbox.root_session_id).where(DemoSandbox.lease_id == sess.sandbox_lease_id))
        return access_token_for(user, sess.id, sandbox_lease_id=sess.sandbox_lease_id, ai_root=root)
    return access_token_for(user, sess.id)


def issue_session(db: Session, user: User, request: Request, response: Response, *, sandbox_lease_id: uuid.UUID | None = None,
                  ai_root: uuid.UUID | None = None) -> TokenOut:
    refresh = new_opaque_token()
    ts = now()
    lifetime = timedelta(days=settings.refresh_token_days)
    if sandbox_lease_id:  # a demo hospital session never outlives the demo's maximum lifetime
        lifetime = min(lifetime, timedelta(hours=settings.demo_sandbox_max_hours))
    sess = UserSession(
        user_id=user.id, refresh_token_hash=hash_token(refresh),
        user_agent=request.headers.get("user-agent", "")[:400], ip_address=client_ip(request),
        created_at=ts, last_used_at=ts, expires_at=ts + lifetime, sandbox_lease_id=sandbox_lease_id,
    )
    db.add(sess)
    user.last_login_at = ts
    user.failed_login_count = 0
    user.locked_until = None
    db.flush()
    set_refresh_cookie(response, refresh)
    return TokenOut(access_token=access_token_for(user, sess.id, sandbox_lease_id=sandbox_lease_id, ai_root=ai_root),
                    expires_in=settings.access_token_minutes * 60, me=build_me(db, user))


def send_email(db: Session, to: str, subject: str, body: str, org_id: uuid.UUID | None = None) -> None:
    """Delivered through the configured message gateway (default: development outbox — stored, never sent)."""
    from app.integrations.adapters import message_gateway

    message_gateway().send(db, channel="email", to=to, subject=subject, body=body, org_id=org_id)
