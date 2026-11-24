"""Demo mode: one-click sign-in for a synthetic-data demonstration deployment (e.g. a product pitch).

Off unless DEMO_MODE=true, and refused in production (see hardening.production_problems). When on:
* POST /auth/demo-login gives each visitor a PRIVATE demo hospital (app/demo/sandbox.py): its own synthetic
  organization with an identity for each of the 14 application roles, switchable in the app. Inside their hospital a
  visitor can do everything the chosen role may do — including the Super Admin's configuration of facilities, staff,
  scheduling, fee schedule, monitors and workflows — because nothing they change is visible to anyone else.
  What stays blocked for hospital identities is platform-level only (SANDBOX_BLOCKED): creating organizations, the
  platform owner's AI controls, and credential/email/MFA changes.
* The seven legacy shared accounts (DEMO_ACCOUNTS, all in the Harborview organization) are no longer used by the demo
  buttons. If someone signs into them with a password while demo mode is on, the original restrictions still apply
  (DEMO_BLOCKED): administrative configuration, credential/MFA changes and the outbox stay blocked for them.
"""

from __future__ import annotations

from app.core.config import settings

# key, button label, email, role shown to visitors
DEMO_ACCOUNTS: list[tuple[str, str, str, str]] = [
    ("doctor", "Doctor", "dr.chen@harborview.dev", "doctor"),
    ("nurse", "Nurse", "nurse.kim@harborview.dev", "nurse"),
    ("front_desk", "Front Desk", "frontdesk@harborview.dev", "receptionist"),
    ("clinic_admin", "Clinic Admin", "clinicadmin@harborview.dev", "clinic_admin"),
    ("billing", "Billing", "billing@harborview.dev", "billing"),
    ("patient", "Patient", "patient@harborview.dev", "patient"),
    ("super_admin", "Super Admin", "superadmin.demo@harborview.dev", "super_admin"),
]
DEMO_EMAILS = {e for _, _, e, _ in DEMO_ACCOUNTS}
DEMO_SUPERADMIN_EMAIL = "superadmin.demo@harborview.dev"

# (methods, path prefix) blocked for demo accounts. Paths are relative to /api or /api/v1.
_WRITES = {"POST", "PUT", "PATCH", "DELETE"}
DEMO_BLOCKED: list[tuple[set[str], str]] = [
    (_WRITES, "/auth/password/change"), (_WRITES, "/auth/email/"), (_WRITES, "/auth/mfa/"), (_WRITES, "/auth/me"),
    (_WRITES, "/admin/"),                       # AI settings & key, other admin endpoints
    (_WRITES, "/organizations"), (_WRITES, "/organization"), (_WRITES, "/clinics"), (_WRITES, "/staff"),
    (_WRITES, "/invitations"), (_WRITES, "/facilities"), (_WRITES, "/departments"), (_WRITES, "/locations"),
    (_WRITES, "/appointment-types"), (_WRITES, "/fee-schedule"), (_WRITES, "/automation/workflows"),
    ({"PUT", "PATCH"}, "/providers/"), ({"PUT", "PATCH"}, "/monitors/"),
    ({"GET", "POST", "PUT", "PATCH", "DELETE"}, "/outbox"),
]


# Identities of a private demo hospital: only platform-level actions are blocked (everything else is governed by the
# identity's ordinary role permissions inside its own organization). Matched on whole path segments.
SANDBOX_BLOCKED: list[tuple[set[str], str]] = [
    (_WRITES, "/auth/password"), (_WRITES, "/auth/email"), (_WRITES, "/auth/mfa"),
    (_WRITES, "/organizations"),                 # creating organizations is a platform operation
    ({"GET", "POST", "PUT", "PATCH", "DELETE"}, "/admin/ai-owner"),  # the platform owner's AI controls
]


def enabled() -> bool:
    return bool(settings.demo_mode) and not settings.is_production


def is_sandbox_user(user) -> bool:
    """An identity that exists only inside one private demo hospital."""
    return user is not None and getattr(user, "sandbox_org_id", None) is not None


def is_demo_user(user) -> bool:
    """Any demo identity (private hospital or legacy shared account): gets demo-scoped AI, never the platform key."""
    if user is None or user.is_superadmin:
        return False
    if is_sandbox_user(user):
        return True  # even if demo mode were switched off: these identities must never see platform AI settings
    return enabled() and user.email in DEMO_EMAILS


def _strip(path: str) -> str:
    for prefix in ("/api/v1", "/api"):
        if path.startswith(prefix + "/"):
            return path[len(prefix):]
    return path


def _match(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def blocked(method: str, path: str, user=None) -> bool:
    path = _strip(path)
    if user is not None and is_sandbox_user(user):
        return any(method in methods and _match(path, p) for methods, p in SANDBOX_BLOCKED)
    if path.startswith("/admin/ai-settings"):  # demo accounts edit their own session-scoped AI settings
        return False
    return any(method in methods and path.startswith(p) for methods, p in DEMO_BLOCKED)


def account(key: str) -> tuple[str, str, str, str] | None:
    return next((a for a in DEMO_ACCOUNTS if a[0] == key), None)


# ---------------------------------------------------------------------------------------------- AI scope per demo session

_ids_cache: dict = {"at": None, "ids": frozenset()}


def demo_user_ids() -> frozenset:
    import time

    # Never trust an empty or cold cache: a demo account missing from it would fall through to the platform AI settings.
    if not _ids_cache["ids"] or _ids_cache["at"] is None or time.monotonic() - _ids_cache["at"] > 300:
        from sqlalchemy import select

        from app.core.db import SessionLocal
        from app.models import User

        db = SessionLocal()
        try:
            ids = db.scalars(select(User.id).where(User.email.in_(DEMO_EMAILS), User.is_superadmin.is_(False))).all()
        finally:
            db.close()
        _ids_cache.update(at=time.monotonic(), ids=frozenset(str(i) for i in ids))
    return _ids_cache["ids"]


def request_ai_scope(authorization: str | None):
    """For a bearer token of a demo account: ('sess:<sid>', EffectiveAI). None otherwise. Runs in a worker thread."""
    if not enabled() or not authorization or not authorization.lower().startswith("bearer "):
        return None
    from app.core.security import decode_token

    data = decode_token(authorization[7:].strip(), "access")
    if not data:
        return None
    from app.ai import demo_scope

    if data.get("sbx"):  # demo hospital: one AI scope per visitor lease (stable across role switches)
        token = f"sess:{data.get('air') or data['sid']}"
        return token, demo_scope.resolve(token)
    if data.get("sub") not in demo_user_ids():
        return None
    token = f"sess:{data['sid']}"
    return token, demo_scope.resolve(token)
