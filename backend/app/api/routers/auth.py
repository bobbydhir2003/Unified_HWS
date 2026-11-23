import uuid
from datetime import timedelta

import pyotp
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import AuthUser, get_auth_user
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import bad_request, not_found
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    hash_token,
    new_opaque_token,
    now,
    validate_password_strength,
    verify_password,
)
from app.models import (
    Invitation,
    Membership,
    MembershipClinic,
    MembershipRole,
    Organization,
    PasswordResetToken,
    User,
    UserSession,
)
from app.schemas.auth import (
    AcceptInviteIn,
    ChangePasswordIn,
    ForgotIn,
    InvitationPreview,
    LoginIn,
    MeOut,
    MfaChallengeOut,
    MfaCodeIn,
    MfaDisableIn,
    MfaSetupOut,
    MfaVerifyIn,
    ProfileUpdate,
    ResetIn,
    SessionOut,
    TokenOut,
)
from app.schemas.common import Message
from app.services import audit
from app.services.identity import (
    REFRESH_COOKIE,
    access_token_for,
    build_me,
    clear_refresh_cookie,
    issue_session,
    send_email,
    set_refresh_cookie,
)

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID = "Invalid email or password"


@router.post("/login", response_model=TokenOut | MfaChallengeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not user.is_active:
        verify_password(body.password, None)  # constant-ish time
        audit.record(db, "auth.login", outcome="failure", request=request, details={"reason": "unknown_user"})
        db.commit()
        raise HTTPException(401, INVALID)
    if user.locked_until and user.locked_until > now():
        audit.record(db, "auth.login", actor_id=user.id, outcome="failure", request=request, details={"reason": "locked"})
        db.commit()
        raise HTTPException(423, "Account temporarily locked after repeated failed attempts. Try again later.")
    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.max_failed_logins:
            user.locked_until = now() + timedelta(minutes=settings.lockout_minutes)
            user.failed_login_count = 0
        audit.record(db, "auth.login", actor_id=user.id, outcome="failure", request=request, details={"reason": "bad_password"})
        db.commit()
        raise HTTPException(401, INVALID)

    if user.mfa_enabled:
        token = create_token(str(user.id), "mfa", settings.mfa_token_minutes)
        audit.record(db, "auth.mfa_challenge", actor_id=user.id, request=request)
        db.commit()
        return MfaChallengeOut(mfa_token=token)

    out = issue_session(db, user, request, response)
    audit.record(db, "auth.login", actor_id=user.id, request=request)
    db.commit()
    return out


@router.post("/mfa/verify", response_model=TokenOut)
def mfa_verify(body: MfaVerifyIn, request: Request, response: Response, db: Session = Depends(get_db)):
    data = decode_token(body.mfa_token, "mfa")
    if not data:
        raise HTTPException(401, "MFA session expired. Sign in again.")
    user = db.get(User, uuid.UUID(data["sub"]))
    if not user or not user.mfa_secret or not user.is_active:
        raise HTTPException(401, "MFA session invalid")
    if not pyotp.TOTP(user.mfa_secret).verify(body.code.strip(), valid_window=1):
        audit.record(db, "auth.mfa_verify", actor_id=user.id, outcome="failure", request=request)
        db.commit()
        raise HTTPException(401, "Invalid verification code")
    out = issue_session(db, user, request, response)
    audit.record(db, "auth.login", actor_id=user.id, request=request, details={"mfa": True})
    db.commit()
    return out


@router.post("/refresh", response_model=TokenOut)
def refresh(
    request: Request, response: Response, db: Session = Depends(get_db),
    ud_refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
):
    if not ud_refresh:
        raise HTTPException(401, "No session")
    sess = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == hash_token(ud_refresh)))
    if not sess or sess.revoked_at or sess.expires_at < now():
        clear_refresh_cookie(response)
        raise HTTPException(401, "Session expired")
    user = db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Session expired")
    # Rotate refresh token on every use.
    new_refresh = new_opaque_token()
    sess.refresh_token_hash = hash_token(new_refresh)
    sess.last_used_at = now()
    db.commit()
    set_refresh_cookie(response, new_refresh)
    return TokenOut(access_token=access_token_for(user, sess.id), expires_in=settings.access_token_minutes * 60,
                    me=build_me(db, user))


@router.post("/logout", response_model=Message)
def logout(
    request: Request, response: Response, db: Session = Depends(get_db),
    ud_refresh: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
):
    if ud_refresh:
        sess = db.scalar(select(UserSession).where(UserSession.refresh_token_hash == hash_token(ud_refresh)))
        if sess and not sess.revoked_at:
            sess.revoked_at = now()
            audit.record(db, "auth.logout", actor_id=sess.user_id, request=request)
            db.commit()
    clear_refresh_cookie(response)
    return Message(message="Signed out")


@router.get("/me", response_model=MeOut)
def me(auth: AuthUser = Depends(get_auth_user), db: Session = Depends(get_db)):
    return build_me(db, auth.user)


@router.patch("/me", response_model=MeOut)
def update_me(body: ProfileUpdate, auth: AuthUser = Depends(get_auth_user), db: Session = Depends(get_db)):
    user = auth.user
    data = body.model_dump(exclude_unset=True)
    if "preferences" in data:
        user.preferences = {**(user.preferences or {}), **(data.pop("preferences") or {})}
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    return build_me(db, user)


# ---------- Password ----------

@router.post("/password/forgot", response_model=Message)
def forgot_password(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    from app.core import demo

    if user and user.is_active and not demo.is_demo_user(user):  # demo accounts sign in with one click; no resets
        token = new_opaque_token()
        db.add(PasswordResetToken(user_id=user.id, token_hash=hash_token(token), created_at=now(),
                                  expires_at=now() + timedelta(hours=1)))
        link = f"{settings.frontend_url}/reset-password?token={token}"
        send_email(db, user.email, "Reset your HMS Workflows password",
                   f"Use this link within 1 hour to reset your password:\n{link}\n\nIf you didn't request this, ignore it.")
        audit.record(db, "auth.password_reset_requested", actor_id=user.id, request=request)
        db.commit()
    # Same response either way, so the endpoint can't be used to enumerate accounts.
    return Message(message="If an account exists for that email, a reset link has been sent.")


@router.post("/password/reset", response_model=Message)
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    rec = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(body.token)))
    if not rec or rec.used_at or rec.expires_at < now():
        raise bad_request("This reset link is invalid or has expired.")
    if err := validate_password_strength(body.password):
        raise bad_request(err)
    user = db.get(User, rec.user_id)
    user.password_hash = hash_password(body.password)
    user.failed_login_count = 0
    user.locked_until = None
    rec.used_at = now()
    # Revoke all sessions after a reset.
    db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
               .values(revoked_at=now()))
    audit.record(db, "auth.password_reset", actor_id=user.id, request=request)
    db.commit()
    return Message(message="Password updated. You can now sign in.")


@router.post("/password/change", response_model=Message)
def change_password(body: ChangePasswordIn, request: Request, auth: AuthUser = Depends(get_auth_user),
                    db: Session = Depends(get_db)):
    user = auth.user
    if not verify_password(body.current_password, user.password_hash):
        raise bad_request("Current password is incorrect")
    if err := validate_password_strength(body.new_password):
        raise bad_request(err)
    user.password_hash = hash_password(body.new_password)
    db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.id != auth.session_id,
                                         UserSession.revoked_at.is_(None)).values(revoked_at=now()))
    audit.record(db, "auth.password_changed", actor_id=user.id, request=request)
    db.commit()
    return Message(message="Password changed. Other sessions were signed out.")


class ChangeEmailIn(BaseModel):
    new_email: str = Field(min_length=5, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    current_password: str = Field(min_length=1, max_length=200)


@router.post("/email/change", response_model=MeOut)
def change_email(body: ChangeEmailIn, request: Request, auth: AuthUser = Depends(get_auth_user), db: Session = Depends(get_db)):
    """Change your sign-in email. Requires your current password; other sessions are signed out."""
    user = auth.user
    if not verify_password(body.current_password, user.password_hash):
        raise bad_request("Current password is incorrect")
    new = body.new_email.strip().lower()
    if new == user.email:
        raise bad_request("That is already your email address.")
    if db.scalar(select(User.id).where(User.email == new)):
        raise bad_request("That email address can't be used.")
    old_domain = user.email.split("@")[-1]
    user.email = new
    db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.id != auth.session_id,
                                         UserSession.revoked_at.is_(None)).values(revoked_at=now()))
    audit.record(db, "auth.email_changed", actor_id=user.id, request=request,
                 details={"old_domain": old_domain, "new_domain": new.split("@")[-1]})
    db.commit()
    return build_me(db, user)


# ---------- MFA ----------

@router.post("/mfa/setup", response_model=MfaSetupOut)
def mfa_setup(auth: AuthUser = Depends(get_auth_user), db: Session = Depends(get_db)):
    user = auth.user
    if user.mfa_enabled:
        raise bad_request("MFA is already enabled")
    secret = pyotp.random_base32()
    user.mfa_secret = secret
    db.commit()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="HMS Workflows")
    return MfaSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/enable", response_model=MeOut)
def mfa_enable(body: MfaCodeIn, request: Request, auth: AuthUser = Depends(get_auth_user), db: Session = Depends(get_db)):
    user = auth.user
    if not user.mfa_secret or not pyotp.TOTP(user.mfa_secret).verify(body.code.strip(), valid_window=1):
        raise bad_request("Invalid code. Check your authenticator app's time and try again.")
    user.mfa_enabled = True
    audit.record(db, "auth.mfa_enabled", actor_id=user.id, request=request)
    db.commit()
    return build_me(db, user)


@router.post("/mfa/disable", response_model=MeOut)
def mfa_disable(body: MfaDisableIn, request: Request, auth: AuthUser = Depends(get_auth_user), db: Session = Depends(get_db)):
    user = auth.user
    if not user.mfa_enabled:
        raise bad_request("MFA is not enabled")
    if not verify_password(body.password, user.password_hash) or not pyotp.TOTP(user.mfa_secret).verify(body.code, valid_window=1):
        raise bad_request("Password or code is incorrect")
    user.mfa_enabled = False
    user.mfa_secret = None
    audit.record(db, "auth.mfa_disabled", actor_id=user.id, request=request)
    db.commit()
    return build_me(db, user)


# ---------- Sessions ----------

@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(auth: AuthUser = Depends(get_auth_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(UserSession).where(
        UserSession.user_id == auth.user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > now()
    ).order_by(UserSession.last_used_at.desc())).all()
    out = []
    for s in rows:
        item = SessionOut.model_validate(s)
        item.ip_address = str(s.ip_address) if s.ip_address else None
        item.current = s.id == auth.session_id
        out.append(item)
    return out


@router.delete("/sessions/{session_id}", response_model=Message)
def revoke_session(session_id: uuid.UUID, request: Request, auth: AuthUser = Depends(get_auth_user),
                   db: Session = Depends(get_db)):
    sess = db.get(UserSession, session_id)
    if not sess or sess.user_id != auth.user.id:
        raise not_found("Session")
    sess.revoked_at = now()
    audit.record(db, "auth.session_revoked", actor_id=auth.user.id, resource_type="session", resource_id=sess.id, request=request)
    db.commit()
    return Message(message="Session revoked")


# ---------- Invitations ----------

def _load_invite(db: Session, token: str) -> Invitation:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    if not inv or inv.accepted_at or inv.revoked_at or inv.expires_at < now():
        raise bad_request("This invitation is invalid or has expired.")
    return inv


@router.get("/invitations/{token}", response_model=InvitationPreview)
def preview_invitation(token: str, db: Session = Depends(get_db)):
    inv = _load_invite(db, token)
    org = db.get(Organization, inv.organization_id)
    exists = db.scalar(select(User.id).where(User.email == inv.email)) is not None
    return InvitationPreview(email=inv.email, first_name=inv.first_name, last_name=inv.last_name,
                             organization_name=org.name, roles=inv.roles, existing_account=exists)


@router.post("/invitations/accept", response_model=TokenOut)
def accept_invitation(body: AcceptInviteIn, request: Request, response: Response, db: Session = Depends(get_db)):
    inv = _load_invite(db, body.token)
    user = db.scalar(select(User).where(User.email == inv.email))
    if user is None:
        if not body.password:
            raise bad_request("Choose a password to create your account")
        if err := validate_password_strength(body.password):
            raise bad_request(err)
        user = User(email=inv.email, first_name=inv.first_name, last_name=inv.last_name,
                    password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
    elif not body.password or not verify_password(body.password, user.password_hash):
        raise bad_request("Enter your existing account password to accept this invitation")

    membership = db.scalar(select(Membership).where(Membership.user_id == user.id,
                                                    Membership.organization_id == inv.organization_id))
    if membership is None:
        membership = Membership(user_id=user.id, organization_id=inv.organization_id,
                                all_clinics=not inv.clinic_ids)
        db.add(membership)
        db.flush()
    existing = set(membership.role_names)
    for r in inv.roles:
        if r not in existing:
            membership.roles.append(MembershipRole(role=r))
    for cid in inv.clinic_ids or []:
        membership.clinics.append(MembershipClinic(clinic_id=uuid.UUID(cid)))
    membership.is_active = True
    inv.accepted_at = now()
    audit.record(db, "user.invitation_accepted", org_id=inv.organization_id, actor_id=user.id,
                 resource_type="invitation", resource_id=inv.id, request=request)
    db.flush()
    db.refresh(user)
    out = issue_session(db, user, request, response)
    db.commit()
    return out


# ---------- Demo mode (synthetic demonstration deployments only; see app/core/demo.py) ----------


class DemoLoginIn(BaseModel):
    key: str = Field(min_length=1, max_length=40)


@router.get("/demo")
def demo_accounts():
    """Public: which one-click demo roles exist. Empty unless DEMO_MODE is on (never in production)."""
    from app.core import demo

    if not demo.enabled():
        return {"enabled": False, "accounts": []}
    return {"enabled": True, "accounts": [{"key": k, "label": label, "role": role} for k, label, _, role in demo.DEMO_ACCOUNTS]}


@router.post("/demo-login", response_model=TokenOut)
def demo_login(body: DemoLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    from app.core import demo
    from app.models import Organization

    acct = demo.account(body.key)
    if not demo.enabled() or not acct:
        raise HTTPException(404, "Not found")
    user = db.scalar(select(User).where(User.email == acct[2]))
    memberships = [m for m in user.memberships if m.is_active] if user else []
    orgs = [db.get(Organization, m.organization_id) for m in memberships]
    # Only synthetic organizations, never the platform administrator, never bypass MFA.
    if (not user or not user.is_active or user.is_superadmin or user.mfa_enabled or not memberships
            or not all(o and (o.settings or {}).get("synthetic_data") for o in orgs)):
        audit.record(db, "auth.demo_login", outcome="failure", request=request, details={"role": body.key})
        db.commit()
        raise HTTPException(403, "This demo account is not available.")
    out = issue_session(db, user, request, response)
    audit.record(db, "auth.demo_login", actor_id=user.id, request=request, details={"role": body.key})
    db.commit()
    return out
