"""Role → permission mapping. Permissions are the only thing endpoints check; roles are a grouping.

Scope is separate from permission: a membership is limited to facilities (`membership_clinics`) and optionally to
departments (`membership_departments`). `TenantContext` enforces both.
"""

from enum import StrEnum


class Role(StrEnum):
    SUPER_ADMIN = "super_admin"
    HOSPITAL_ADMIN = "hospital_admin"
    CLINIC_ADMIN = "clinic_admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    RECEPTIONIST = "receptionist"
    BILLING = "billing"
    INSURANCE_SPECIALIST = "insurance_specialist"
    PHARMACIST = "pharmacist"
    LAB_TECH = "lab_tech"
    RADIOLOGY_TECH = "radiology_tech"
    RADIOLOGIST = "radiologist"
    BED_MANAGER = "bed_manager"
    PATIENT = "patient"


ROLE_LABELS = {
    Role.SUPER_ADMIN: "Super Admin",
    Role.HOSPITAL_ADMIN: "Hospital Administrator",
    Role.CLINIC_ADMIN: "Facility Admin",
    Role.DOCTOR: "Doctor",
    Role.NURSE: "Nurse / MA",
    Role.RECEPTIONIST: "Receptionist",
    Role.BILLING: "Billing Specialist",
    Role.INSURANCE_SPECIALIST: "Insurance Specialist",
    Role.PHARMACIST: "Pharmacist",
    Role.LAB_TECH: "Laboratory Technologist",
    Role.RADIOLOGY_TECH: "Radiology Technologist",
    Role.RADIOLOGIST: "Radiologist",
    Role.BED_MANAGER: "Bed Manager",
    Role.PATIENT: "Patient",
}


class P(StrEnum):
    ORG_MANAGE = "org:manage"  # create organizations (platform level)
    CLINIC_MANAGE = "clinic:manage"  # facilities, departments, locations, settings
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
    INSURANCE_WRITE = "insurance:write"  # eligibility, coverage verification, prior auth
    AI_USE = "ai:use"
    AI_MANAGE = "ai:manage"  # agent studio, providers, governance
    AUTOMATION_MANAGE = "automation:manage"
    ANALYTICS_READ = "analytics:read"
    MESSAGES = "messages:use"
    PORTAL_SELF = "portal:self"
    # Operations / automation engine
    CASES_READ = "cases:read"
    CASES_WORK = "cases:work"  # claim, assign, snooze, resolve cases & tasks
    COMMAND_CENTER = "command:view"
    # Hospital
    ADT_READ = "adt:read"  # admissions, census, bed board
    ADT_WRITE = "adt:write"  # admit / transfer / discharge
    BEDS_MANAGE = "beds:manage"  # bed status, housekeeping
    ED_WRITE = "ed:write"
    NURSING_WRITE = "nursing:write"
    PHARMACY_READ = "pharmacy:read"
    PHARMACY_VERIFY = "pharmacy:verify"
    INVENTORY_READ = "inventory:read"
    INVENTORY_WRITE = "inventory:write"
    PROCUREMENT_APPROVE = "procurement:approve"
    LAB_WORK = "lab:work"  # collect, accession, enter results
    LAB_VERIFY = "lab:verify"
    RADIOLOGY_WORK = "radiology:work"
    RADIOLOGY_SIGN = "radiology:sign"
    OR_MANAGE = "or:manage"
    ROSTER_MANAGE = "roster:manage"
    ROSTER_SELF = "roster:self"


_STAFF_BASE = {P.PATIENTS_READ, P.SCHEDULE_READ, P.MESSAGES, P.CASES_READ, P.CASES_WORK, P.ROSTER_SELF}
_ADMIN = {
    P.CLINIC_MANAGE, P.USERS_MANAGE, P.AUDIT_READ, P.PATIENTS_WRITE, P.SCHEDULE_WRITE, P.DOCUMENTS_READ, P.DOCUMENTS_WRITE,
    P.BILLING_READ, P.AUTOMATION_MANAGE, P.ANALYTICS_READ, P.AI_USE, P.COMMAND_CENTER, P.ADT_READ, P.INVENTORY_READ,
    P.PHARMACY_READ, P.ROSTER_MANAGE,
}

ROLE_PERMISSIONS: dict[str, set[P]] = {
    Role.SUPER_ADMIN: set(P) - {P.PORTAL_SELF},
    Role.HOSPITAL_ADMIN: _STAFF_BASE | _ADMIN | {P.AI_MANAGE, P.PROCUREMENT_APPROVE, P.OR_MANAGE, P.BEDS_MANAGE, P.INVENTORY_WRITE},
    Role.CLINIC_ADMIN: _STAFF_BASE | _ADMIN,
    Role.DOCTOR: _STAFF_BASE | {
        P.PATIENTS_WRITE, P.SCHEDULE_WRITE, P.CLINICAL_READ, P.CLINICAL_WRITE, P.CLINICAL_SIGN, P.ORDERS_WRITE, P.ORDERS_SIGN,
        P.DOCUMENTS_READ, P.DOCUMENTS_WRITE, P.DOCUMENTS_REVIEW, P.AI_USE, P.ANALYTICS_READ, P.ADT_READ, P.ADT_WRITE, P.ED_WRITE,
    },
    Role.NURSE: _STAFF_BASE | {
        P.PATIENTS_WRITE, P.SCHEDULE_WRITE, P.CLINICAL_READ, P.CLINICAL_WRITE, P.ORDERS_WRITE, P.DOCUMENTS_READ, P.DOCUMENTS_WRITE,
        P.DOCUMENTS_REVIEW, P.AI_USE, P.ADT_READ, P.ADT_WRITE, P.ED_WRITE, P.NURSING_WRITE, P.BEDS_MANAGE, P.LAB_WORK, P.INVENTORY_READ,
    },
    Role.RECEPTIONIST: _STAFF_BASE | {
        P.PATIENTS_WRITE, P.SCHEDULE_WRITE, P.DOCUMENTS_READ, P.DOCUMENTS_WRITE, P.BILLING_READ, P.AI_USE, P.INSURANCE_WRITE, P.ADT_READ,
    },
    Role.BILLING: _STAFF_BASE | {
        P.CLINICAL_READ, P.BILLING_READ, P.BILLING_WRITE, P.DOCUMENTS_READ, P.ANALYTICS_READ, P.AI_USE, P.INSURANCE_WRITE,
    },
    Role.INSURANCE_SPECIALIST: _STAFF_BASE | {
        P.PATIENTS_WRITE, P.CLINICAL_READ, P.BILLING_READ, P.DOCUMENTS_READ, P.DOCUMENTS_WRITE, P.DOCUMENTS_REVIEW, P.AI_USE,
        P.INSURANCE_WRITE, P.ANALYTICS_READ,
    },
    Role.PHARMACIST: _STAFF_BASE | {
        P.CLINICAL_READ, P.PHARMACY_READ, P.PHARMACY_VERIFY, P.INVENTORY_READ, P.INVENTORY_WRITE, P.AI_USE, P.ADT_READ,
    },
    Role.LAB_TECH: _STAFF_BASE | {P.CLINICAL_READ, P.LAB_WORK, P.LAB_VERIFY, P.INVENTORY_READ, P.AI_USE},
    Role.RADIOLOGY_TECH: _STAFF_BASE | {P.CLINICAL_READ, P.RADIOLOGY_WORK, P.AI_USE},
    Role.RADIOLOGIST: _STAFF_BASE | {P.CLINICAL_READ, P.RADIOLOGY_WORK, P.RADIOLOGY_SIGN, P.AI_USE},
    Role.BED_MANAGER: _STAFF_BASE | {P.ADT_READ, P.ADT_WRITE, P.BEDS_MANAGE, P.COMMAND_CENTER, P.AI_USE},
    Role.PATIENT: {P.PORTAL_SELF},
}


def permissions_for(roles: list[str]) -> set[str]:
    out: set[str] = set()
    for r in roles:
        out |= {p.value for p in ROLE_PERMISSIONS.get(r, set())}
    return out
