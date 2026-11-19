import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select

from app.api.deps import TenantContext, get_ctx, require
from app.core.errors import not_found
from app.core.permissions import P
from app.core.security import now
from app.models import (
    Appointment,
    Encounter,
    Patient,
    PatientAccessGrant,
    PatientInsurance,
    PatientNote,
    ProviderProfile,
    User,
)
from app.schemas.common import Message, Page
from app.schemas.patients import (
    BreakGlassIn,
    DuplicateCandidate,
    DuplicateCheckIn,
    InsuranceIn,
    InsuranceOut,
    PatientCreate,
    PatientListItem,
    PatientNoteIn,
    PatientNoteOut,
    PatientOut,
    PatientUpdate,
)
from app.services.patients import digits, find_duplicates, get_patient, next_mrn

router = APIRouter(prefix="/patients", tags=["patients"])


def _validate_refs(ctx: TenantContext, clinic_id: uuid.UUID | None, provider_id: uuid.UUID | None) -> None:
    from app.models import Clinic

    if clinic_id:
        c = ctx.db.get(Clinic, clinic_id)
        if not c or c.organization_id != ctx.org_id:
            raise HTTPException(422, "Unknown clinic")
    if provider_id:
        pr = ctx.db.get(ProviderProfile, provider_id)
        if not pr or pr.organization_id != ctx.org_id:
            raise HTTPException(422, "Unknown provider")


def _out(p: Patient) -> PatientOut:
    out = PatientOut.model_validate(p)
    out.has_portal_access = p.portal_user_id is not None
    return out


def search_patients_query(ctx: TenantContext, q: str | None):
    stmt = select(Patient).where(Patient.organization_id == ctx.org_id)
    if q and (q := q.strip()):
        conds = [Patient.mrn == q.upper()]
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
            try:
                conds.append(Patient.date_of_birth == datetime.strptime(q, fmt).date())
                break
            except ValueError:
                pass
        d = digits(q)
        if len(d) >= 4 and len(d) == len(q.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")):
            conds.append(func.regexp_replace(Patient.phone, r"\D", "", "g").like(f"%{d}%"))
        name = func.lower(Patient.first_name + " " + Patient.last_name)
        tokens = [t for t in q.lower().replace(",", " ").split() if t]
        if tokens:
            per_token = [or_(func.lower(Patient.first_name).startswith(t), func.lower(Patient.last_name).startswith(t),
                             func.lower(func.coalesce(Patient.preferred_name, "")).startswith(t)) for t in tokens]
            from sqlalchemy import and_

            conds.append(and_(*per_token))
            if len(q) >= 4:
                conds.append(func.similarity(name, q.lower()) > 0.45)
        stmt = stmt.where(or_(*conds)).order_by(func.similarity(name, q.lower()).desc(), Patient.last_name)
    else:
        stmt = stmt.order_by(Patient.updated_at.desc())
    return stmt


@router.get("", response_model=Page[PatientListItem])
def list_patients(
    q: str | None = None, status: str | None = None, provider_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    ctx: TenantContext = Depends(require(P.PATIENTS_READ)),
):
    stmt = search_patients_query(ctx, q)
    if status:
        stmt = stmt.where(Patient.status == status)
    if provider_id:
        stmt = stmt.where(Patient.primary_provider_id == provider_id)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = ctx.db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    ids = [r.id for r in rows]
    last_visits = dict(ctx.db.execute(select(Encounter.patient_id, func.max(Encounter.started_at))
                                      .where(Encounter.patient_id.in_(ids)).group_by(Encounter.patient_id)).all())
    prov_ids = {r.primary_provider_id for r in rows if r.primary_provider_id}
    prov_names = dict(ctx.db.execute(select(ProviderProfile.id, User.first_name + " " + User.last_name)
                                     .join(User, User.id == ProviderProfile.user_id)
                                     .where(ProviderProfile.id.in_(prov_ids))).all())
    items = []
    for r in rows:
        it = PatientListItem.model_validate(r)
        it.last_visit_at = last_visits.get(r.id)
        it.primary_provider_name = prov_names.get(r.primary_provider_id)
        items.append(it)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("/duplicates", response_model=list[DuplicateCandidate])
def check_duplicates(body: DuplicateCheckIn, ctx: TenantContext = Depends(require(P.PATIENTS_WRITE))):
    return find_duplicates(ctx, body.first_name, body.last_name, body.date_of_birth, body.phone, body.email,
                           body.exclude_id)


@router.post("", response_model=PatientOut, status_code=201)
def create_patient(body: PatientCreate, ctx: TenantContext = Depends(require(P.PATIENTS_WRITE))):
    _validate_refs(ctx, body.primary_clinic_id, body.primary_provider_id)
    if not body.confirm_not_duplicate:
        dups = find_duplicates(ctx, body.first_name, body.last_name, body.date_of_birth, body.phone, body.email)
        if dups:
            raise HTTPException(409, {"code": "possible_duplicate",
                                      "message": "Possible duplicate patient(s) found",
                                      "candidates": [DuplicateCandidate(**d).model_dump(mode="json") for d in dups]})
    data = body.model_dump(exclude={"insurance", "confirm_not_duplicate"})
    p = Patient(organization_id=ctx.org_id, mrn=next_mrn(ctx), **data)
    ctx.db.add(p)
    ctx.db.flush()
    if body.insurance:
        ctx.db.add(PatientInsurance(organization_id=ctx.org_id, patient_id=p.id, **body.insurance.model_dump()))
    ctx.audit("patient.created", resource_type="patient", resource_id=p.id, patient_id=p.id,
              details={"duplicate_override": body.confirm_not_duplicate})
    ctx.db.commit()
    ctx.db.refresh(p)
    return _out(p)


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient_detail(patient_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id)
    ctx.audit("patient.chart_viewed", resource_type="patient", resource_id=p.id, patient_id=p.id)
    ctx.db.commit()
    return _out(p)


@router.put("/{patient_id}", response_model=PatientOut)
def update_patient(patient_id: uuid.UUID, body: PatientUpdate, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id, P.PATIENTS_WRITE)
    _validate_refs(ctx, body.primary_clinic_id, body.primary_provider_id)
    changed = []
    for k, v in body.model_dump().items():
        if getattr(p, k) != v:
            changed.append(k)
            setattr(p, k, v)
    ctx.audit("patient.updated", resource_type="patient", resource_id=p.id, patient_id=p.id, details={"fields": changed})
    ctx.db.commit()
    ctx.db.refresh(p)
    return _out(p)


@router.post("/{patient_id}/restriction", response_model=PatientOut)
def set_restriction(patient_id: uuid.UUID, restricted: bool, ctx: TenantContext = Depends(require(P.USERS_MANAGE))):
    p = ctx.db.get(Patient, patient_id)
    if not p or p.organization_id != ctx.org_id:
        raise not_found("Patient")
    p.is_restricted = restricted
    ctx.audit("patient.restriction_changed", resource_type="patient", resource_id=p.id, patient_id=p.id,
              details={"restricted": restricted})
    ctx.db.commit()
    return _out(p)


@router.post("/{patient_id}/break-glass", response_model=Message)
def break_glass(patient_id: uuid.UUID, body: BreakGlassIn, ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    p = ctx.db.get(Patient, patient_id)
    if not p or p.organization_id != ctx.org_id:
        raise not_found("Patient")
    ctx.db.add(PatientAccessGrant(organization_id=ctx.org_id, patient_id=p.id, user_id=ctx.user.id, reason=body.reason,
                                  is_break_glass=True, granted_by_id=ctx.user.id, expires_at=now() + timedelta(hours=4)))
    # Reason text is stored in the grant row; audit holds the pointer + flag for compliance review.
    ctx.audit("patient.break_glass", resource_type="patient", resource_id=p.id, patient_id=p.id,
              details={"expires_hours": 4})
    ctx.db.commit()
    return Message(message="Emergency access granted for 4 hours. This access is logged for compliance review.")


# ---------- Insurance ----------

@router.post("/{patient_id}/insurances", response_model=InsuranceOut, status_code=201)
def add_insurance(patient_id: uuid.UUID, body: InsuranceIn, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id, P.PATIENTS_WRITE)
    ins = PatientInsurance(organization_id=ctx.org_id, patient_id=p.id, **body.model_dump())
    ctx.db.add(ins)
    ctx.audit("patient.insurance_added", resource_type="insurance", resource_id=None, patient_id=p.id)
    ctx.db.commit()
    return ins


@router.put("/{patient_id}/insurances/{ins_id}", response_model=InsuranceOut)
def update_insurance(patient_id: uuid.UUID, ins_id: uuid.UUID, body: InsuranceIn, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id, P.PATIENTS_WRITE)
    ins = ctx.db.get(PatientInsurance, ins_id)
    if not ins or ins.patient_id != p.id:
        raise not_found("Insurance")
    for k, v in body.model_dump().items():
        setattr(ins, k, v)
    ins.eligibility_status = "unverified"
    ctx.audit("patient.insurance_updated", resource_type="insurance", resource_id=ins.id, patient_id=p.id)
    ctx.db.commit()
    return ins


@router.post("/{patient_id}/insurances/{ins_id}/eligibility", response_model=InsuranceOut)
def check_eligibility(patient_id: uuid.UUID, ins_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    """Eligibility check via the configured gateway (SIMULATED by default: see SimulatedEligibility)."""
    p = get_patient(ctx, patient_id, P.PATIENTS_WRITE)
    ins = ctx.db.get(PatientInsurance, ins_id)
    if not ins or ins.patient_id != p.id:
        raise not_found("Insurance")
    from app.services.insurance import run_check

    run_check(ctx.db, ins, dos=date.today(), trigger="staff", actor_id=ctx.user.id)  # recorded in eligibility_checks history
    ctx.db.commit()
    return ins


# ---------- Admin notes ----------

@router.get("/{patient_id}/notes", response_model=list[PatientNoteOut])
def list_notes(patient_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id)
    if ctx.is_patient_only:
        raise not_found("Patient")
    rows = ctx.db.execute(select(PatientNote, User.first_name + " " + User.last_name)
                          .outerjoin(User, User.id == PatientNote.author_id).where(PatientNote.patient_id == p.id)
                          .order_by(PatientNote.is_pinned.desc(), PatientNote.created_at.desc())).all()
    out = []
    for n, name in rows:
        item = PatientNoteOut.model_validate(n)
        item.author_name = name
        out.append(item)
    return out


@router.post("/{patient_id}/notes", response_model=PatientNoteOut, status_code=201)
def add_note(patient_id: uuid.UUID, body: PatientNoteIn, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id, P.PATIENTS_WRITE)
    n = PatientNote(organization_id=ctx.org_id, patient_id=p.id, author_id=ctx.user.id, **body.model_dump())
    ctx.db.add(n)
    ctx.db.commit()
    out = PatientNoteOut.model_validate(n)
    out.author_name = ctx.user.full_name
    return out


@router.delete("/{patient_id}/notes/{note_id}", response_model=Message)
def delete_note(patient_id: uuid.UUID, note_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id, P.PATIENTS_WRITE)
    n = ctx.db.get(PatientNote, note_id)
    if not n or n.patient_id != p.id:
        raise not_found("Note")
    ctx.db.delete(n)
    ctx.db.commit()
    return Message(message="Note deleted")


@router.get("/{patient_id}/appointments")
def patient_appointments(patient_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    from app.api.routers.scheduling import appointment_out

    p = get_patient(ctx, patient_id)
    if not ctx.is_patient_only:
        ctx.require(P.SCHEDULE_READ)
    rows = ctx.db.scalars(select(Appointment).where(Appointment.patient_id == p.id)
                          .order_by(Appointment.start_at.desc()).limit(200)).all()
    return [appointment_out(a) for a in rows]
