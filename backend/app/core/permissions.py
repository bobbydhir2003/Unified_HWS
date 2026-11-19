"""Role → permission mapping. Permissions are the only thing endpoints check; roles are a grouping."""

from enum import StrEnum


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    CLINIC_ADMIN = "clinic_admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    RECEPTIONIST = "receptionist"
    BILLING = "billing"
    PATIENT = "patient"


ROLE_LABELS = {
    Role.SUPER_ADMIN: "Super Admin",
    Role.CLINIC_ADMIN: "Clinic Admin",
    Role.DOCTOR: "Doctor",
    Role.NURSE: "Nurse / MA",
    Role.RECEPTIONIST: "Receptionist",
    Role.BILLING: "Billing Specialist",
    Role.PATIENT: "Patient",
}


class P(StrEnum):
    ORG_MANAGE = "org:manage"  # create organizations (platform level)
    CLINIC_MANAGE = "clinic:manage"
    USERS_MANAGE = "users:manage"
    AUDIT_READ = "audit:read"
    PATIENTS_READ = "patients:read"
    PATIENTS_WRITE = "patients:write"
    SCHEDULE_READ = "schedule:read"
    SCHEDULE_WRITE = "schedule:write"
    CLINICAL_READ = "clinical:read"
    CLINICAL_WRITE = "clinical:write"
    CLINICAL_SIGN = "clinical:sign"
    ORDERS_WRITE = "orders:write"
    ORDERS_SIGN = "orders:sign"
    DOCUMENTS_READ = "documents:read"
    DOCUMENTS_WRITE = "documents:write"
    DOCUMENTS_REVIEW = "documents:review"
    BILLING_READ = "billing:read"
    BILLING_WRITE = "billing:write"
    AI_USE = "ai:use"
    AUTOMATION_MANAGE = "automation:manage"
    ANALYTICS_READ = "analytics:read"
    MESSAGES = "messages:use"
    PORTAL_SELF = "portal:self"


_STAFF_BASE = {P.PATIENTS_READ, P.SCHEDULE_READ, P.MESSAGES}

ROLE_PERMISSIONS: dict[str, set[P]] = {
    Role.SUPER_ADMIN: set(P) - {P.PORTAL_SELF},
    Role.CLINIC_ADMIN: _STAFF_BASE
    | {
        P.CLINIC_MANAGE,
        P.USERS_MANAGE,
        P.AUDIT_READ,
        P.PATIENTS_WRITE,
        P.SCHEDULE_WRITE,
        P.DOCUMENTS_READ,
        P.DOCUMENTS_WRITE,
        P.BILLING_READ,
        P.AUTOMATION_MANAGE,
        P.ANALYTICS_READ,
        P.AI_USE,
    },
    Role.DOCTOR: _STAFF_BASE
    | {
        P.PATIENTS_WRITE,
        P.SCHEDULE_WRITE,
        P.CLINICAL_READ,
        P.CLINICAL_WRITE,
        P.CLINICAL_SIGN,
        P.ORDERS_WRITE,
        P.ORDERS_SIGN,
        P.DOCUMENTS_READ,
        P.DOCUMENTS_WRITE,
        P.DOCUMENTS_REVIEW,
        P.AI_USE,
        P.ANALYTICS_READ,
    },
    Role.NURSE: _STAFF_BASE
    | {
        P.PATIENTS_WRITE,
        P.SCHEDULE_WRITE,
        P.CLINICAL_READ,
        P.CLINICAL_WRITE,
        P.ORDERS_WRITE,
        P.DOCUMENTS_READ,
        P.DOCUMENTS_WRITE,
        P.DOCUMENTS_REVIEW,
        P.AI_USE,
    },
    Role.RECEPTIONIST: _STAFF_BASE
    | {P.PATIENTS_WRITE, P.SCHEDULE_WRITE, P.DOCUMENTS_READ, P.DOCUMENTS_WRITE, P.BILLING_READ, P.AI_USE},
    Role.BILLING: _STAFF_BASE
    | {P.CLINICAL_READ, P.BILLING_READ, P.BILLING_WRITE, P.DOCUMENTS_READ, P.ANALYTICS_READ, P.AI_USE},
    Role.PATIENT: {P.PORTAL_SELF},
}


def permissions_for(roles: list[str]) -> set[str]:
    out: set[str] = set()
    for r in roles:
        out |= {p.value for p in ROLE_PERMISSIONS.get(r, set())}
    return out
