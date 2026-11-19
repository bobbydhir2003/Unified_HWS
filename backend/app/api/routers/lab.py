"""Laboratory API (B7): collection list, accessioning, bench worklist, results entry, verification, corrections,
critical-result acknowledgment. Analyzer interfaces are not connected; results are entered by technologists."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import TenantContext, require
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.data.catalogs import LABS
from app.models import CriticalResultAlert, InpatientStay, LabResult, Location, Order, Patient, Specimen, User
from app.services import lab as L
from app.services.patients import get_patient

router = APIRouter(tags=["laboratory"])


def _err(ctx, fn):
    try:
        return fn()
    except L.LabError as e:
        ctx.db.rollback()
        raise bad_request(str(e)) from None


def _spec(ctx, sid) -> Specimen:
    s = ctx.db.get(Specimen, sid)
    if not s or s.organization_id != ctx.org_id:
        raise not_found("Specimen")
    get_patient(ctx, s.patient_id)
    return s


def _where(ctx, patient_id) -> str | None:
    """Patient location for the collection list (inpatient bed or 'Outpatient')."""
    from app.services.adt import current_assignment

    stay = ctx.db.scalar(select(InpatientStay).where(InpatientStay.patient_id == patient_id, InpatientStay.status.in_(("admitted", "discharge_ordered"))))
    if stay:
        a = current_assignment(ctx.db, stay.id)
        bed = ctx.db.get(Location, a.bed_id) if a else None
        return f"Inpatient · {bed.code}" if bed else "Inpatient"
    return "Outpatient"


def _template(order: Order) -> list[dict]:
    """Expected components for the order's test code (from the lab catalog), to prefill results entry."""
    entry = next((x for x in LABS if x[0] == order.code), None) if order.code else None
    return [{"name": n, "unit": u, "reference_range": f"{lo}-{hi}"} for n, u, lo, hi, *_ in (entry[3] if entry else [])]


def spec_out(ctx, s: Specimen, names: dict | None = None) -> dict:
    o = s.order
    results = ctx.db.scalars(select(LabResult).where(LabResult.specimen_id == s.id).order_by(LabResult.name, LabResult.resulted_at)).all()
    names = names or {}
    return {"id": s.id, "accession_number": s.accession_number, "status": s.status, "specimen_type": s.specimen_type, "container": s.container,
            "order": {"id": o.id, "title": o.title, "code": o.code, "priority": o.priority},
            "patient": {"id": s.patient_id, "name": s.patient.full_name, "mrn": s.patient.mrn},
            "collected_at": s.collected_at, "received_at": s.received_at, "rejected_reason": s.rejected_reason,
            "template": _template(o),
            "results": [{"id": r.id, "name": r.name, "value": r.value, "unit": r.unit, "reference_range": r.reference_range, "flag": r.flag, "status": r.status,
                         "entered_by_id": r.entered_by_id, "entered_by": names.get(r.entered_by_id), "verified_by": names.get(r.verified_by_id),
                         "verified_at": r.verified_at, "supersedes_id": r.supersedes_id, "correction_reason": r.correction_reason} for r in results]}


@router.get("/lab/worklist")
def worklist(ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    if not (ctx.can(P.LAB_WORK) or ctx.can(P.LAB_VERIFY)):
        raise forbidden()
    to_collect = ctx.db.execute(select(Order, Patient).join(Patient, Patient.id == Order.patient_id).outerjoin(
        Specimen, (Specimen.order_id == Order.id) & (Specimen.status != "rejected")).where(
        Order.organization_id == ctx.org_id, Order.order_type == "lab", Order.status.in_(("signed", "transmitted")), Specimen.id.is_(None),
        Patient.is_restricted.is_(False)).order_by(Order.priority.desc(), Order.signed_at)).all()
    specs = ctx.db.scalars(select(Specimen).where(Specimen.organization_id == ctx.org_id, Specimen.status.in_(("collected", "received", "in_process")))
                           .order_by(Specimen.collected_at)).all()
    ids = {r for s in specs for r in ctx.db.scalars(select(LabResult.entered_by_id).where(LabResult.specimen_id == s.id))}
    names = {u.id: u.display_name for u in ctx.db.scalars(select(User).where(User.id.in_({i for i in ids if i})))} if ids else {}
    alerts = ctx.db.scalars(select(CriticalResultAlert).where(CriticalResultAlert.organization_id == ctx.org_id, CriticalResultAlert.acknowledged_at.is_(None))).all()
    return {"to_collect": [{"order_id": o.id, "title": o.title, "priority": o.priority, "signed_at": o.signed_at, "patient": {"id": p.id, "name": p.full_name, "mrn": p.mrn},
                            "location": _where(ctx, p.id)} for o, p in to_collect],
            "specimens": [spec_out(ctx, s, names) for s in specs],
            "critical_unacknowledged": [{"id": a.id, "summary": a.summary, "patient_id": a.patient_id, "created_at": a.created_at,
                                         "minutes": int((now() - a.created_at).total_seconds() // 60)} for a in alerts]}


class CollectIn(BaseModel):
    order_id: uuid.UUID
    specimen_type: Literal["blood", "urine", "swab", "csf", "stool", "sputum", "other"] = "blood"
    container: str | None = Field(default=None, max_length=40)


@router.post("/lab/collect", status_code=201)
def collect(body: CollectIn, ctx: TenantContext = Depends(require(P.LAB_WORK))):
    o = ctx.db.get(Order, body.order_id)
    if not o or o.organization_id != ctx.org_id:
        raise not_found("Order")
    get_patient(ctx, o.patient_id)
    s = _err(ctx, lambda: L.collect(ctx.db, o, specimen_type=body.specimen_type, container=body.container, actor_id=ctx.user.id))
    ctx.db.commit()
    return spec_out(ctx, s)


@router.post("/lab/specimens/{sid}/receive")
def receive(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.LAB_WORK))):
    s = _spec(ctx, sid)
    _err(ctx, lambda: L.receive(ctx.db, s, actor_id=ctx.user.id))
    ctx.db.commit()
    return spec_out(ctx, s)


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


@router.post("/lab/specimens/{sid}/reject")
def reject(sid: uuid.UUID, body: RejectIn, ctx: TenantContext = Depends(require(P.LAB_WORK))):
    s = _spec(ctx, sid)
    _err(ctx, lambda: L.reject(ctx.db, s, reason=body.reason, actor_id=ctx.user.id))
    ctx.db.commit()
    return spec_out(ctx, s)


class ResultRow(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=60)
    unit: str | None = Field(default=None, max_length=30)
    reference_range: str | None = Field(default=None, max_length=60)
    flag: Literal["normal", "high", "low", "abnormal", "critical_high", "critical_low"] = "normal"


@router.post("/lab/specimens/{sid}/results")
def enter(sid: uuid.UUID, body: list[ResultRow], ctx: TenantContext = Depends(require(P.LAB_WORK))):
    s = _spec(ctx, sid)
    _err(ctx, lambda: L.enter_results(ctx.db, s, [r.model_dump() for r in body], actor_id=ctx.user.id))
    ctx.db.commit()
    return spec_out(ctx, s)


@router.post("/lab/specimens/{sid}/verify")
def verify(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.LAB_VERIFY))):
    s = _spec(ctx, sid)
    alerts = _err(ctx, lambda: L.verify(ctx.db, s, actor_id=ctx.user.id))
    ctx.db.commit()
    return {**spec_out(ctx, s), "critical_alerts": len(alerts)}


class CorrectIn(BaseModel):
    value: str = Field(min_length=1, max_length=60)
    flag: Literal["normal", "high", "low", "abnormal", "critical_high", "critical_low"]
    reason: str = Field(min_length=5, max_length=300)


@router.post("/lab/results/{rid}/correct")
def correct(rid: uuid.UUID, body: CorrectIn, ctx: TenantContext = Depends(require(P.LAB_WORK))):
    r = ctx.db.get(LabResult, rid)
    if not r or r.organization_id != ctx.org_id:
        raise not_found("Result")
    get_patient(ctx, r.patient_id)
    _err(ctx, lambda: L.correct(ctx.db, r, value=body.value, flag=body.flag, reason=body.reason, actor_id=ctx.user.id))
    ctx.db.commit()
    return spec_out(ctx, ctx.db.get(Specimen, r.specimen_id))


@router.get("/lab/critical")
def critical_list(mine: bool = False, ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    q = select(CriticalResultAlert).where(CriticalResultAlert.organization_id == ctx.org_id, CriticalResultAlert.acknowledged_at.is_(None))
    if mine:
        q = q.where(CriticalResultAlert.clinician_user_id == ctx.user.id)
    out = []
    for a in ctx.db.scalars(q.order_by(CriticalResultAlert.created_at)):
        p = ctx.db.get(Patient, a.patient_id)
        out.append({"id": a.id, "summary": a.summary, "order_id": a.order_id, "patient": {"id": p.id, "name": p.full_name, "mrn": p.mrn},
                    "created_at": a.created_at, "mine": a.clinician_user_id == ctx.user.id})
    return out


class AckIn(BaseModel):
    read_back: str = Field(min_length=3, max_length=500)


@router.post("/lab/critical/{aid}/acknowledge")
def acknowledge(aid: uuid.UUID, body: AckIn, ctx: TenantContext = Depends(require(P.CLINICAL_WRITE))):
    """The responsible clinician (or a covering prescriber) acknowledges with read-back. Lab staff cannot self-acknowledge."""
    a = ctx.db.get(CriticalResultAlert, aid)
    if not a or a.organization_id != ctx.org_id:
        raise not_found("Alert")
    get_patient(ctx, a.patient_id)
    if a.clinician_user_id != ctx.user.id and not ctx.can(P.ORDERS_SIGN):
        raise forbidden("Only the ordering or covering clinician can acknowledge a critical result")
    _err(ctx, lambda: L.acknowledge(ctx.db, a, actor_id=ctx.user.id, read_back=body.read_back))
    ctx.db.commit()
    return {"acknowledged_at": a.acknowledged_at}
