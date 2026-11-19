"""Emergency department API (Milestone B3): quick registration, tracking board, triage (nurse-recorded ESI),
rooming, provider assignment, disposition (incl. admission → boarding), identity reconciliation."""

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import TenantContext, require
from app.api.routers.adt import _facility
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import Department, EdVisit, Location, Patient, ProviderProfile, TriageAssessment, User
from app.models.ed import ED_ACTIVE
from app.services import ed as E
from app.services.patients import get_patient

router = APIRouter(tags=["emergency"])


def _visit(ctx: TenantContext, vid: uuid.UUID) -> EdVisit:
    v = ctx.db.get(EdVisit, vid)
    if not v or v.organization_id != ctx.org_id:
        raise not_found("ED visit")
    ctx.require_facility(v.facility_id)
    get_patient(ctx, v.patient_id)
    return v


def _err(ctx: TenantContext, fn):
    try:
        return fn()
    except E.EdError as e:
        ctx.db.rollback()
        raise bad_request(str(e)) from None


def _mins(a, b=None):
    return int(((b or now()) - a).total_seconds() // 60) if a else None


def visit_out(ctx: TenantContext, v: EdVisit, names: dict | None = None) -> dict:
    p = v.patient
    bay = ctx.db.get(Location, v.bed_id) if v.bed_id else None
    prov = ctx.db.get(ProviderProfile, v.provider_id) if v.provider_id else None
    nurse = (names or {}).get(v.nurse_user_id) if names is not None else (ctx.db.get(User, v.nurse_user_id).display_name if v.nurse_user_id else None)
    end = v.departed_at
    return {"id": v.id, "status": v.status, "patient": {"id": p.id, "name": "Restricted patient" if p.is_restricted else p.full_name,
                                                         "mrn": p.mrn, "sex": p.sex_at_birth, "dob": p.date_of_birth, "temporary": p.is_temporary,
                                                         "merged_into_id": p.merged_into_id},
            "arrival_at": v.arrival_at, "arrival_mode": v.arrival_mode, "chief_complaint": v.chief_complaint, "esi_level": v.esi_level,
            "bay": {"id": bay.id, "name": bay.name} if bay else None, "provider": prov.user.display_name if prov else None,
            "provider_id": v.provider_id, "nurse": nurse, "encounter_id": v.encounter_id, "stay_id": v.stay_id,
            "disposition": v.disposition, "departed_at": v.departed_at,
            "minutes_in_department": _mins(v.arrival_at, end), "door_to_triage": _mins(v.arrival_at, v.triaged_at) if v.triaged_at else None,
            "door_to_provider": _mins(v.arrival_at, v.provider_seen_at) if v.provider_seen_at else None,
            "boarding_minutes": _mins(v.disposition_at) if v.status == "boarding" else None}


@router.get("/ed/board")
def ed_board(facility_id: uuid.UUID | None = None, ctx: TenantContext = Depends(require(P.ADT_READ))):
    f = _facility(ctx, facility_id)
    visits = ctx.db.scalars(select(EdVisit).where(EdVisit.facility_id == f.id, EdVisit.status.in_(ED_ACTIVE))
                            .order_by(func.coalesce(EdVisit.esi_level, 9), EdVisit.arrival_at)).all()
    ids = {v.nurse_user_id for v in visits if v.nurse_user_id}
    names = {u.id: u.display_name for u in ctx.db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    ed_dept = ctx.db.scalar(select(Department.id).where(Department.facility_id == f.id, Department.kind == "emergency"))
    bays = ctx.db.scalars(select(Location).where(Location.facility_id == f.id, Location.kind == "bed", Location.department_id == ed_dept)
                          .order_by(Location.sort_order)).all() if ed_dept else []
    since = now() - timedelta(hours=24)
    done = ctx.db.scalars(select(EdVisit).where(EdVisit.facility_id == f.id, EdVisit.arrival_at > since)).all()
    d2p = [_mins(v.arrival_at, v.provider_seen_at) for v in done if v.provider_seen_at]
    los = [_mins(v.arrival_at, v.departed_at) for v in done if v.departed_at]
    out = [visit_out(ctx, v, names) for v in visits]
    return {"facility": {"id": f.id, "name": f.name}, "visits": out,
            "bays": [{"id": b.id, "name": b.name, "status": b.bed_status} for b in bays],
            "metrics": {"in_department": len(visits), "waiting": sum(1 for v in visits if v.status in ("waiting", "triaged")),
                        "boarding": sum(1 for v in visits if v.status == "boarding"),
                        "arrivals_24h": len(done), "lwbs_24h": sum(1 for v in done if v.disposition == "lwbs"),
                        "median_door_to_provider_min": sorted(d2p)[len(d2p) // 2] if d2p else None,
                        "median_los_min": sorted(los)[len(los) // 2] if los else None}}


class ArrivalIn(BaseModel):
    facility_id: uuid.UUID | None = None
    patient_id: uuid.UUID | None = None
    unidentified: bool = False
    sex: Literal["male", "female", "unknown"] = "unknown"
    approx_age: int | None = Field(default=None, ge=0, le=120)
    chief_complaint: str = Field(min_length=2, max_length=300)
    arrival_mode: Literal["walk_in", "ambulance", "police", "transfer", "other"] = "walk_in"


@router.post("/ed/arrivals", status_code=201)
def arrival(body: ArrivalIn, ctx: TenantContext = Depends(require(P.ED_WRITE))):
    """Quick registration. Unidentified patients get a temporary identity reconciled later (never guessed)."""
    f = _facility(ctx, body.facility_id)
    if body.unidentified:
        if not ctx.can(P.PATIENTS_WRITE):
            raise forbidden()
        p = E.make_temporary_patient(ctx.db, ctx, sex=body.sex, approx_age=body.approx_age)
    elif body.patient_id:
        p = get_patient(ctx, body.patient_id)
    else:
        raise bad_request("Choose a patient or register as unidentified")
    v = _err(ctx, lambda: E.arrive(ctx.db, org_id=ctx.org_id, facility_id=f.id, patient=p, complaint=body.chief_complaint,
                                   mode=body.arrival_mode, actor_id=ctx.user.id))
    ctx.db.commit()
    return visit_out(ctx, v)


@router.get("/ed/visits/{vid}")
def get_visit(vid: uuid.UUID, ctx: TenantContext = Depends(require(P.ADT_READ))):
    v = _visit(ctx, vid)
    tri = ctx.db.scalars(select(TriageAssessment).where(TriageAssessment.ed_visit_id == v.id).order_by(TriageAssessment.at)).all()
    return {**visit_out(ctx, v), "triage": [{"esi": t.esi_level, "complaint": t.complaint, "notes": t.notes, "at": t.at} for t in tri]}


class VitalsMini(BaseModel):
    systolic: int | None = Field(default=None, ge=40, le=300)
    diastolic: int | None = Field(default=None, ge=20, le=200)
    heart_rate: int | None = Field(default=None, ge=20, le=250)
    respiratory_rate: int | None = Field(default=None, ge=4, le=80)
    spo2: int | None = Field(default=None, ge=50, le=100)
    pain_score: int | None = Field(default=None, ge=0, le=10)


class TriageIn(BaseModel):
    esi_level: int = Field(ge=1, le=5)
    chief_complaint: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=2000)
    vitals: VitalsMini | None = None


@router.post("/ed/visits/{vid}/triage")
def record_triage(vid: uuid.UUID, body: TriageIn, ctx: TenantContext = Depends(require(P.ED_WRITE))):
    """ESI acuity is assessed and recorded by a nurse (or physician). The software never assigns it."""
    if not (ctx.can(P.NURSING_WRITE) or ctx.can(P.CLINICAL_SIGN)):
        raise forbidden("Triage is recorded by nursing or physician staff")
    v = _visit(ctx, vid)
    vit = {k: x for k, x in (body.vitals.model_dump() if body.vitals else {}).items() if x is not None}
    _err(ctx, lambda: E.triage(ctx.db, v, esi=body.esi_level, actor_id=ctx.user.id, complaint=body.chief_complaint, notes=body.notes,
                               vitals=vit or None))
    ctx.db.commit()
    return visit_out(ctx, v)


class RoomIn(BaseModel):
    bed_id: uuid.UUID


@router.post("/ed/visits/{vid}/room")
def room(vid: uuid.UUID, body: RoomIn, ctx: TenantContext = Depends(require(P.ED_WRITE))):
    v = _visit(ctx, vid)
    bay = ctx.db.get(Location, body.bed_id)
    if not bay or bay.organization_id != ctx.org_id:
        raise not_found("Bay")
    _err(ctx, lambda: E.room(ctx.db, v, bay, actor_id=ctx.user.id))
    ctx.db.commit()
    return visit_out(ctx, v)


class AssignIn(BaseModel):
    provider_id: uuid.UUID | None = None
    nurse_user_id: uuid.UUID | None = None
    me: bool = False


@router.post("/ed/visits/{vid}/assign")
def assign(vid: uuid.UUID, body: AssignIn, ctx: TenantContext = Depends(require(P.ED_WRITE))):
    v = _visit(ctx, vid)
    if body.me:
        if ctx.provider:
            body.provider_id = ctx.provider.id
        elif ctx.can(P.NURSING_WRITE):
            body.nurse_user_id = ctx.user.id
    if body.provider_id:
        pr = ctx.db.get(ProviderProfile, body.provider_id)
        if not pr or pr.organization_id != ctx.org_id:
            raise bad_request("Unknown provider")
        E.assign_provider(ctx.db, v, provider_id=pr.id, actor_id=ctx.user.id)
    if body.nurse_user_id:
        v.nurse_user_id = body.nurse_user_id
    ctx.db.commit()
    return visit_out(ctx, v)


class DispositionIn(BaseModel):
    disposition: Literal["discharged", "admit", "transferred", "lwbs", "ama", "expired"]
    note: str | None = Field(default=None, max_length=1000)
    admit_reason: str | None = Field(default=None, max_length=300)
    department_id: uuid.UUID | None = None
    level_of_care: Literal["med_surg", "telemetry", "icu", "observation"] = "med_surg"


@router.post("/ed/visits/{vid}/disposition")
def disposition(vid: uuid.UUID, body: DispositionIn, ctx: TenantContext = Depends(require(P.ED_WRITE))):
    v = _visit(ctx, vid)
    clinical = body.disposition in ("discharged", "admit", "transferred", "expired")
    if clinical and not ctx.can(P.ORDERS_SIGN):
        raise forbidden("A physician decides discharge, admission, transfer or death disposition")
    if body.disposition == "admit":
        _err(ctx, lambda: E.request_admit(ctx.db, v, actor_id=ctx.user.id, attending_provider_id=ctx.provider.id if ctx.provider else None,
                                          reason=body.admit_reason or v.chief_complaint, department_id=body.department_id,
                                          level_of_care=body.level_of_care))
    else:
        _err(ctx, lambda: E.depart(ctx.db, v, disposition=body.disposition, actor_id=ctx.user.id, note=body.note))
    ctx.db.commit()
    return visit_out(ctx, v)


class ReconcileIn(BaseModel):
    patient_id: uuid.UUID
    attest_identity_verified: bool = False
    method: str = Field(min_length=3, max_length=200)  # e.g. "Driver's license verified at bedside"


@router.post("/ed/visits/{vid}/reconcile")
def reconcile(vid: uuid.UUID, body: ReconcileIn, ctx: TenantContext = Depends(require(P.PATIENTS_WRITE))):
    """Identity reconciliation: move a temporary identity's records into the confirmed real chart."""
    v = _visit(ctx, vid)
    if not body.attest_identity_verified:
        raise bad_request("Confirm the patient's identity was verified before merging")
    src = ctx.db.get(Patient, v.patient_id)
    dst = get_patient(ctx, body.patient_id, P.PATIENTS_WRITE)
    moved = _err(ctx, lambda: E.merge_patients(ctx.db, source=src, target=dst, actor_id=ctx.user.id, org_id=ctx.org_id))
    ctx.audit("patient.identity_reconciled", resource_type="ed_visit", resource_id=v.id, patient_id=dst.id, details={"method": body.method})
    ctx.db.commit()
    return {"message": f"Records merged into {dst.full_name} ({dst.mrn})", "moved": moved, "visit": visit_out(ctx, ctx.db.get(EdVisit, vid))}
