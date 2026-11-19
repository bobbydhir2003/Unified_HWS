import re
import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.api.deps import TenantContext
from app.core.errors import not_found
from app.core.permissions import P
from app.core.security import now
from app.models import Organization, Patient, PatientAccessGrant


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def has_restricted_access(ctx: TenantContext, p: Patient) -> bool:
    if ctx.provider and p.primary_provider_id == ctx.provider.id:
        return True
    grant = ctx.db.scalar(select(PatientAccessGrant.id).where(
        PatientAccessGrant.patient_id == p.id, PatientAccessGrant.user_id == ctx.user.id,
        or_(PatientAccessGrant.expires_at.is_(None), PatientAccessGrant.expires_at > now()),
    ))
    return grant is not None


def get_patient(ctx: TenantContext, patient_id: uuid.UUID, perm: str = P.PATIENTS_READ) -> Patient:
    """Load a patient the caller may access, or raise. Cross-tenant ids are indistinguishable from missing ones."""
    p = ctx.db.get(Patient, patient_id)
    if not p or p.organization_id != ctx.org_id:
        raise not_found("Patient")
    if ctx.is_patient_only:
        if p.portal_user_id != ctx.user.id or perm not in (P.PATIENTS_READ, P.CLINICAL_READ, P.PORTAL_SELF):
            raise not_found("Patient")
        return p
    ctx.require(perm)
    if p.is_restricted and not has_restricted_access(ctx, p):
        ctx.audit("patient.restricted_blocked", resource_type="patient", resource_id=p.id, patient_id=p.id, outcome="denied")
        ctx.db.commit()
        raise HTTPException(403, {"code": "restricted_chart",
                                  "message": "This chart is restricted. Break-the-glass access requires a documented reason."})
    return p


def next_mrn(ctx: TenantContext) -> str:
    org = ctx.db.scalar(select(Organization).where(Organization.id == ctx.org_id).with_for_update())
    seq = int((org.settings or {}).get("mrn_seq", 100000)) + 1
    org.settings = {**(org.settings or {}), "mrn_seq": seq}
    return f"UD{seq}"


def find_duplicates(ctx: TenantContext, first: str, last: str, dob: date, phone: str | None, email: str | None,
                    exclude_id: uuid.UUID | None = None) -> list[dict]:
    full = f"{first} {last}".lower()
    name_expr = func.lower(Patient.first_name + " " + Patient.last_name)
    sim = func.similarity(name_expr, full)
    conds = [Patient.date_of_birth == dob, sim > 0.55]
    ph = digits(phone)
    if len(ph) >= 7:
        conds.append(func.regexp_replace(Patient.phone, r"\D", "", "g") == ph)
    if email:
        conds.append(func.lower(Patient.email) == email.lower())
    q = (select(Patient, sim.label("sim")).where(Patient.organization_id == ctx.org_id, or_(*conds))
         .order_by(sim.desc()).limit(25))
    if exclude_id:
        q = q.where(Patient.id != exclude_id)
    out = []
    for p, s in ctx.db.execute(q).all():
        reasons, score = [], 0.0
        same_dob = p.date_of_birth == dob
        if same_dob:
            reasons.append("same date of birth")
            score += 0.35
        if s and s > 0.55:
            reasons.append("similar name")
            score += 0.4 * float(s)
        if len(ph) >= 7 and digits(p.phone) == ph:
            reasons.append("same phone")
            score += 0.25
        if email and p.email and p.email.lower() == email.lower():
            reasons.append("same email")
            score += 0.25
        # Same DOB alone (without any other signal) is too common to flag.
        if score >= 0.45:
            out.append({"id": p.id, "mrn": p.mrn, "name": p.full_name, "date_of_birth": p.date_of_birth,
                        "phone": p.phone, "reasons": reasons, "score": round(min(score, 1.0), 2)})
    return sorted(out, key=lambda d: -d["score"])[:5]
