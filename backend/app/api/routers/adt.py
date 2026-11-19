"""Inpatient ADT + bed board API (Milestone B1/B2)."""

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import TenantContext, require
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import (
    AdtEvent,
    BedAssignment,
    Clinic,
    Department,
    InpatientStay,
    Location,
    Patient,
    ProviderProfile,
)
from app.models.inpatient import DISPOSITIONS, STAY_ACTIVE
from app.services import adt as A
from app.services.patients import get_patient

router = APIRouter(tags=["inpatient"])


def _facility(ctx: TenantContext, facility_id: uuid.UUID | None) -> Clinic:
    if facility_id is None:
        q = select(Clinic).where(Clinic.organization_id == ctx.org_id, Clinic.facility_type == "hospital", Clinic.is_active.is_(True))
        if ctx.facility_ids is not None:
            q = q.where(Clinic.id.in_(ctx.facility_ids))
        f = ctx.db.scalars(q.order_by(Clinic.name)).first()
        if not f:
            raise not_found("Hospital facility")
        return f
    f = ctx.db.get(Clinic, facility_id)
    if not f or f.organization_id != ctx.org_id:
        raise not_found("Facility")
    ctx.require_facility(f.id)
    return f


def _stay(ctx: TenantContext, sid: uuid.UUID) -> InpatientStay:
    s = ctx.db.get(InpatientStay, sid)
    if not s or s.organization_id != ctx.org_id:
        raise not_found("Hospital stay")
    ctx.require_facility(s.facility_id)
    get_patient(ctx, s.patient_id)  # restricted-chart rules apply to inpatient views too
    return s


def _bed(ctx: TenantContext, bid: uuid.UUID) -> Location:
    b = ctx.db.get(Location, bid)
    if not b or b.organization_id != ctx.org_id or b.kind != "bed":
        raise not_found("Bed")
    ctx.require_facility(b.facility_id)
    return b


def _err(ctx: TenantContext, fn):
    try:
        fn()
    except A.AdtError as e:
        ctx.db.rollback()
        raise bad_request(str(e)) from None


def _hours(a: datetime | None) -> float | None:
    return round((now() - a).total_seconds() / 3600, 1) if a else None


def stay_out(ctx: TenantContext, s: InpatientStay, bed: Location | None = None) -> dict:
    p = s.patient
    bed = bed if bed is not None else (lambda a: ctx.db.get(Location, a.bed_id) if a else None)(A.current_assignment(ctx.db, s.id))
    dept = ctx.db.get(Department, s.department_id or s.requested_department_id) if (s.department_id or s.requested_department_id) else None
    return {"id": s.id, "status": s.status, "patient": {"id": p.id, "name": p.full_name, "mrn": p.mrn, "dob": p.date_of_birth, "sex": p.sex_at_birth,
                                                         "restricted": p.is_restricted},
            "facility_id": s.facility_id, "department": {"id": dept.id, "name": dept.name} if dept else None,
            "bed": {"id": bed.id, "code": bed.code, "name": bed.name} if bed else None,
            "attending": s.attending.user.display_name if s.attending else None, "attending_provider_id": s.attending_provider_id,
            "reason": s.reason, "admit_source": s.admit_source, "level_of_care": s.level_of_care, "isolation": s.isolation,
            "requested_at": s.requested_at, "admitted_at": s.admitted_at, "waiting_hours": _hours(s.requested_at) if s.status == "pending" else None,
            "los_hours": _hours(s.admitted_at) if s.admitted_at and not s.discharged_at else None,
            "expected_discharge_date": s.expected_discharge_date, "discharge_ordered_at": s.discharge_ordered_at,
            "discharge_disposition": s.discharge_disposition, "discharged_at": s.discharged_at, "ed_visit_id": s.ed_visit_id,
            "encounter_id": s.encounter_id}


# ---------- Bed board & census ----------

@router.get("/adt/board")
def bed_board(facility_id: uuid.UUID | None = None, ctx: TenantContext = Depends(require(P.ADT_READ))):
    f = _facility(ctx, facility_id)
    locs = ctx.db.scalars(select(Location).where(Location.facility_id == f.id, Location.is_active.is_(True))
                          .order_by(Location.sort_order, Location.code)).all()
    by_id = {x.id: x for x in locs}
    occ = ctx.db.execute(select(BedAssignment.bed_id, InpatientStay).join(InpatientStay, InpatientStay.id == BedAssignment.stay_id)
                         .where(BedAssignment.end_at.is_(None), InpatientStay.facility_id == f.id)).all()
    occ_map = {b: s for b, s in occ}

    def unit_of(loc: Location) -> Location:
        while loc.parent_id and by_id.get(loc.parent_id) and by_id[loc.parent_id].kind != "unit":
            loc = by_id[loc.parent_id]
        return by_id.get(loc.parent_id, loc) if loc.parent_id else loc

    units: dict[uuid.UUID, dict] = {}
    for b in (x for x in locs if x.kind == "bed"):
        u = unit_of(b)
        d = units.setdefault(u.id, {"id": u.id, "code": u.code, "name": u.name, "department_id": u.department_id, "beds": [],
                                    "counts": {"available": 0, "occupied": 0, "reserved": 0, "cleaning": 0, "blocked": 0}})
        d["counts"][b.bed_status] += 1
        s = occ_map.get(b.id)
        room = by_id.get(b.parent_id)
        restricted = s is not None and s.patient.is_restricted
        d["beds"].append({"id": b.id, "code": b.code, "name": b.name, "room": room.name if room and room.kind == "room" else None,
                          "status": b.bed_status, "status_reason": b.bed_status_reason, "since": b.bed_status_changed_at,
                          "attributes": b.attributes,
                          "stay": None if s is None else {
                              "id": s.id, "status": s.status, "patient_name": "Restricted patient" if restricted else s.patient.full_name,
                              "patient_id": None if restricted else s.patient_id, "mrn": None if restricted else s.patient.mrn,
                              "los_hours": _hours(s.admitted_at), "isolation": s.isolation,
                              "discharge_ordered": s.status == "discharge_ordered", "attending": s.attending.user.display_name if s.attending else None,
                              "expected_discharge_date": s.expected_discharge_date}})
    pending = ctx.db.scalars(select(InpatientStay).where(InpatientStay.facility_id == f.id, InpatientStay.status == "pending")
                             .order_by(InpatientStay.requested_at)).all()
    unit_list = sorted(units.values(), key=lambda u: u["code"])
    totals = {k: sum(u["counts"][k] for u in unit_list) for k in ("available", "occupied", "reserved", "cleaning", "blocked")}
    staffed = sum(totals.values()) - totals["blocked"]
    return {"facility": {"id": f.id, "name": f.name}, "generated_at": now(), "units": unit_list, "totals": totals,
            "occupancy_pct": round(100 * totals["occupied"] / staffed, 1) if staffed else None,
            "pending_admissions": [stay_out(ctx, s, bed=None) for s in pending],
            "discharges_ordered": sum(1 for s in occ_map.values() if s.status == "discharge_ordered")}


@router.get("/adt/census")
def census(facility_id: uuid.UUID | None = None, ctx: TenantContext = Depends(require(P.ADT_READ))):
    f = _facility(ctx, facility_id)
    rows = ctx.db.execute(select(Department.name, func.count()).select_from(InpatientStay).join(Department, Department.id == InpatientStay.department_id)
                          .where(InpatientStay.facility_id == f.id, InpatientStay.status.in_(("admitted", "discharge_ordered")))
                          .group_by(Department.name)).all()
    today = now().date()
    admits = ctx.db.scalar(select(func.count()).select_from(InpatientStay).where(InpatientStay.facility_id == f.id,
                                                                                 func.date(InpatientStay.admitted_at) == today))
    discharges = ctx.db.scalar(select(func.count()).select_from(InpatientStay).where(InpatientStay.facility_id == f.id,
                                                                                     func.date(InpatientStay.discharged_at) == today))
    return {"facility": f.name, "by_department": [{"department": d, "patients": n} for d, n in rows], "total": sum(n for _, n in rows),
            "admissions_today": admits, "discharges_today": discharges}


# ---------- Stays ----------

@router.get("/adt/stays")
def list_stays(status: Literal["active", "pending", "admitted", "discharge_ordered", "discharged", "all"] = "active",
               facility_id: uuid.UUID | None = None, department_id: uuid.UUID | None = None, mine: bool = False,
               ctx: TenantContext = Depends(require(P.ADT_READ))):
    q = select(InpatientStay).join(Patient).where(InpatientStay.organization_id == ctx.org_id, Patient.is_restricted.is_(False))
    if status == "active":
        q = q.where(InpatientStay.status.in_(STAY_ACTIVE))
    elif status != "all":
        q = q.where(InpatientStay.status == status)
    if facility_id:
        ctx.require_facility(facility_id)
        q = q.where(InpatientStay.facility_id == facility_id)
    elif ctx.facility_ids is not None:
        q = q.where(InpatientStay.facility_id.in_(ctx.facility_ids))
    if department_id:
        q = q.where(InpatientStay.department_id == department_id)
    elif ctx.department_ids is not None:
        q = q.where(InpatientStay.department_id.in_(ctx.department_ids) | InpatientStay.requested_department_id.in_(ctx.department_ids))
    if mine and ctx.provider:
        q = q.where(InpatientStay.attending_provider_id == ctx.provider.id)
    return [stay_out(ctx, s) for s in ctx.db.scalars(q.order_by(InpatientStay.requested_at.desc()).limit(300)).all()]


@router.get("/adt/stays/{sid}")
def get_stay(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.ADT_READ))):
    s = _stay(ctx, sid)
    moves = ctx.db.execute(select(BedAssignment, Location.code).join(Location, Location.id == BedAssignment.bed_id)
                           .where(BedAssignment.stay_id == s.id).order_by(BedAssignment.start_at)).all()
    events = ctx.db.scalars(select(AdtEvent).where(AdtEvent.stay_id == s.id).order_by(AdtEvent.at)).all()
    ctx.audit("inpatient_stay.viewed", resource_type="inpatient_stay", resource_id=s.id, patient_id=s.patient_id)
    ctx.db.commit()
    return {**stay_out(ctx, s), "movements": [{"bed": code, "start_at": a.start_at, "end_at": a.end_at, "reason": a.reason} for a, code in moves],
            "events": [{"kind": e.kind, "at": e.at, "note": e.note} for e in events]}


@router.get("/patients/{patient_id}/stays")
def patient_stays(patient_id: uuid.UUID, ctx: TenantContext = Depends(require(P.ADT_READ))):
    p = get_patient(ctx, patient_id)
    rows = ctx.db.scalars(select(InpatientStay).where(InpatientStay.patient_id == p.id).order_by(InpatientStay.requested_at.desc())).all()
    return [stay_out(ctx, s) for s in rows]


class AdmitIn(BaseModel):
    patient_id: uuid.UUID
    facility_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    attending_provider_id: uuid.UUID | None = None
    reason: str = Field(min_length=3, max_length=300)
    admit_source: Literal["ed", "direct", "elective", "transfer_in"] = "direct"
    level_of_care: Literal["med_surg", "telemetry", "icu", "observation"] = "med_surg"
    expected_discharge_date: date | None = None
    isolation: Literal["contact", "droplet", "airborne"] | None = None
    bed_id: uuid.UUID | None = None  # admit straight into a bed


@router.post("/adt/stays", status_code=201)
def request_admission(body: AdmitIn, ctx: TenantContext = Depends(require(P.ADT_WRITE))):
    p = get_patient(ctx, body.patient_id)
    f = _facility(ctx, body.facility_id)
    if body.department_id:
        d = ctx.db.get(Department, body.department_id)
        if not d or d.facility_id != f.id:
            raise bad_request("Department belongs to a different facility")
    if body.attending_provider_id:
        pr = ctx.db.get(ProviderProfile, body.attending_provider_id)
        if not pr or pr.organization_id != ctx.org_id:
            raise bad_request("Unknown attending")
    holder: dict = {}

    def go():
        s = A.request_admission(ctx.db, org_id=ctx.org_id, facility_id=f.id, patient_id=p.id, department_id=body.department_id,
                                attending_provider_id=body.attending_provider_id or (ctx.provider.id if ctx.provider else None), reason=body.reason,
                                source=body.admit_source, level_of_care=body.level_of_care, expected_discharge_date=body.expected_discharge_date,
                                isolation=body.isolation, actor_id=ctx.user.id)
        if body.bed_id:
            A.admit(ctx.db, s, _bed(ctx, body.bed_id), actor_id=ctx.user.id)
        holder["s"] = s
    _err(ctx, go)
    ctx.db.commit()
    return stay_out(ctx, holder["s"])


class BedIn(BaseModel):
    bed_id: uuid.UUID
    note: str | None = Field(default=None, max_length=300)


@router.post("/adt/stays/{sid}/assign-bed")
def assign_bed(sid: uuid.UUID, body: BedIn, ctx: TenantContext = Depends(require(P.ADT_WRITE))):
    s = _stay(ctx, sid)
    _err(ctx, lambda: A.admit(ctx.db, s, _bed(ctx, body.bed_id), actor_id=ctx.user.id))
    ctx.db.commit()
    return stay_out(ctx, s)


@router.post("/adt/stays/{sid}/transfer")
def transfer(sid: uuid.UUID, body: BedIn, ctx: TenantContext = Depends(require(P.ADT_WRITE))):
    s = _stay(ctx, sid)
    _err(ctx, lambda: A.transfer(ctx.db, s, _bed(ctx, body.bed_id), actor_id=ctx.user.id, note=body.note))
    ctx.db.commit()
    return stay_out(ctx, s)


class DischargeOrderIn(BaseModel):
    disposition: Literal[DISPOSITIONS] = "home"  # type: ignore[valid-type]
    expected_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)


@router.post("/adt/stays/{sid}/discharge-order")
def discharge_order(sid: uuid.UUID, body: DischargeOrderIn, ctx: TenantContext = Depends(require(P.ORDERS_SIGN))):
    """A discharge order is a physician order (orders:sign)."""
    s = _stay(ctx, sid)
    _err(ctx, lambda: A.order_discharge(ctx.db, s, actor_id=ctx.user.id, disposition=body.disposition, expected_at=body.expected_at,
                                         note=body.note))
    ctx.db.commit()
    return stay_out(ctx, s)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/adt/stays/{sid}/discharge-order/cancel")
def cancel_discharge_order(sid: uuid.UUID, body: ReasonIn, ctx: TenantContext = Depends(require(P.ORDERS_SIGN))):
    s = _stay(ctx, sid)
    _err(ctx, lambda: A.cancel_discharge_order(ctx.db, s, actor_id=ctx.user.id, reason=body.reason))
    ctx.db.commit()
    return stay_out(ctx, s)


class DischargeIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)
    override_readiness: bool = False
    override_reason: str | None = Field(default=None, max_length=300)


@router.post("/adt/stays/{sid}/discharge")
def complete_discharge(sid: uuid.UUID, body: DischargeIn, ctx: TenantContext = Depends(require(P.ADT_WRITE))):
    s = _stay(ctx, sid)
    from app.services.discharge import readiness

    r = readiness(ctx.db, s)
    if r and not r["ready"]:
        if not body.override_readiness:
            raise bad_request(f"Discharge checklist incomplete: {', '.join(r['blocking'])}")
        if not ctx.can(P.ORDERS_SIGN):
            raise bad_request("Only a physician can discharge with open checklist items")
        if not body.override_reason:
            raise bad_request("A reason is required to discharge with open checklist items")
        ctx.audit("discharge.readiness_override", resource_type="inpatient_stay", resource_id=s.id, patient_id=s.patient_id,
                  details={"blocking": r["blocking"]})
    _err(ctx, lambda: A.discharge(ctx.db, s, actor_id=ctx.user.id, note=body.note or body.override_reason))
    ctx.db.commit()
    return stay_out(ctx, s)


@router.post("/adt/stays/{sid}/cancel")
def cancel_admission(sid: uuid.UUID, body: ReasonIn, ctx: TenantContext = Depends(require(P.ADT_WRITE))):
    s = _stay(ctx, sid)
    _err(ctx, lambda: A.cancel(ctx.db, s, actor_id=ctx.user.id, reason=body.reason))
    ctx.db.commit()
    return stay_out(ctx, s)


class BedStatusIn(BaseModel):
    to: Literal["available", "reserved", "cleaning", "blocked"]
    reason: str | None = Field(default=None, max_length=200)


@router.post("/beds/{bed_id}/status")
def bed_status(bed_id: uuid.UUID, body: BedStatusIn, ctx: TenantContext = Depends(require(P.BEDS_MANAGE))):
    b = _bed(ctx, bed_id)
    _err(ctx, lambda: A.set_bed_status(ctx.db, b, body.to, actor_id=ctx.user.id, reason=body.reason))
    ctx.audit("bed.status_changed", resource_type="bed", resource_id=b.id, details={"to": body.to, "reason": body.reason})
    ctx.db.commit()
    return {"id": b.id, "code": b.code, "status": b.bed_status}
