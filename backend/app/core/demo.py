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
    ("hospital_admin", "Hospital Admin", "hospitaladmin@harborview.dev", "hospital_admin"),
    ("pharmacist", "Pharmacist", "pharmacist@harborview.dev", "pharmacist"),
    ("lab", "Laboratory", "lab@harborview.dev", "lab_tech"),
    ("radiology", "Radiology", "radiology@harborview.dev", "radiologist"),
    ("bed_manager", "Bed Manager", "bedmanager@harborview.dev", "bed_manager"),
    ("insurance", "Insurance", "insurance@harborview.dev", "insurance_specialist"),
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
    ({"PUT", "PATCH"}, "/providers/"), ({"PUT", "PATCH"}, "/agents/"), ({"PUT", "PATCH"}, "/monitors/"),
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
    return any(method in methods and path.startswith(p) for methods, p in DEMO_BLOCKED)


def account(key: str) -> tuple[str, str, str, str] | None:
    return next((a for a in DEMO_ACCOUNTS if a[0] == key), None)
