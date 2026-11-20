"""Demo mode: one-click role sign-in for a synthetic-data demonstration deployment (e.g. a product pitch).

Off unless DEMO_MODE=true, and refused in production (see hardening.production_problems). When on:
* POST /auth/demo-login signs in ONLY the server-side allowlisted accounts below, and only if every one of the
  account's organizations is flagged `synthetic_data`. The platform super administrator is never on the list — the
  "Super Admin" button uses a dedicated demo account with the super_admin role inside the demo organization.
* Demo accounts can browse everything their role allows and run normal hospital workflows on synthetic data, but
  administrative configuration, credential/MFA changes and AI-key management are blocked for them (DEMO_BLOCKED),
  and the message outbox (which can contain password-reset links) is hidden from them.
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
    (_WRITES, "/auth/password/change"), (_WRITES, "/auth/mfa/"), (_WRITES, "/auth/me"),
    (_WRITES, "/admin/"),                       # AI settings & key, other admin endpoints
    (_WRITES, "/organizations"), (_WRITES, "/organization"), (_WRITES, "/clinics"), (_WRITES, "/staff"),
    (_WRITES, "/invitations"), (_WRITES, "/facilities"), (_WRITES, "/departments"), (_WRITES, "/locations"),
    (_WRITES, "/appointment-types"), (_WRITES, "/fee-schedule"), (_WRITES, "/automation/workflows"),
    ({"PUT", "PATCH"}, "/providers/"), ({"PUT", "PATCH"}, "/monitors/"),
    ({"GET", "POST", "PUT", "PATCH", "DELETE"}, "/outbox"),
]


def enabled() -> bool:
    return bool(settings.demo_mode) and not settings.is_production


def is_demo_user(user) -> bool:
    return enabled() and user is not None and user.email in DEMO_EMAILS and not user.is_superadmin


def blocked(method: str, path: str) -> bool:
    for prefix in ("/api/v1", "/api"):
        if path.startswith(prefix + "/"):
            path = path[len(prefix):]
            break
    if path.startswith("/admin/ai-settings"):  # demo accounts edit their own session-scoped AI settings
        return False
    return any(method in methods and path.startswith(p) for methods, p in DEMO_BLOCKED)


def account(key: str) -> tuple[str, str, str, str] | None:
    return next((a for a in DEMO_ACCOUNTS if a[0] == key), None)


# ---------------------------------------------------------------------------------------------- AI scope per demo session

_ids_cache: dict = {"at": 0.0, "ids": frozenset()}


def demo_user_ids() -> frozenset:
    import time

    if time.monotonic() - _ids_cache["at"] > 300:
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
    if not data or data.get("sub") not in demo_user_ids():
        return None
    from app.ai import demo_scope

    token = f"sess:{data['sid']}"
    return token, demo_scope.resolve(token)
