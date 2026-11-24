"""Inpatient medication lifecycle + electronic Medication Administration Record (eMAR).

Business rules live in app/services/medication.py; this router adds permissions, patient-access checks, audit events
and notifications. Barcode scanning is SIMULATED (wristband `PT-<MRN>`, pharmacy dose label `RXD-<dispense id>`) but every
scan is validated on the server.
"""

import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, select

from app.api.deps import TenantContext, require
from app.core.errors import not_found
from app.core.permissions import P
from app.core.security import now
from app.models import (
    InventoryItem,
    InventoryLot,
    MedicationAdministration,
    MedicationAdministrationWitness,
    MedicationVerification,
    Order,
    Patient,
    StockMovement,
    User,
)
from app.services import medication as MED
from app.services.notify import notify
from app.services.patients import get_patient

router = APIRouter(tags=["medications"])


def _conflict(e: MED.MedicationError):
    raise HTTPException(e.status, {"code": e.code, "message": str(e)})


def _med_order(ctx: TenantContext, oid: uuid.UUID, perm: str = P.CLINICAL_READ) -> Order:
    o = ctx.db.get(Order, oid)
    if not o or o.organization_id != ctx.org_id or o.order_type != "medication":
        raise not_found("Medication order")
    get_patient(ctx, o.patient_id, perm)
    return o


def _name(ctx: TenantContext, uid) -> str | None:
    u = ctx.db.get(User, uid) if uid else None
    return u.display_name if u else None


def med_order_out(ctx: TenantContext, o: Order) -> dict:
    d = o.details or {}
    v = MED.latest_decision(ctx.db, o.id)
    return {
        "id": o.id, "patient_id": o.patient_id, "title": o.title, "status": o.status, "priority": o.priority, "setting": d.get("setting"),
        "name": d.get("name"), "dose": MED.ordered_dose(o), "route": d.get("route"), "frequency": d.get("frequency"),
        "frequency_label": MED.FREQUENCIES.get(d.get("frequency"), {}).get("label") if d.get("frequency") else None,
        "prn_interval_hours": d.get("prn_interval_hours"), "prn_reason": d.get("prn_reason"), "sig": d.get("sig"),
        "high_alert": MED.is_high_alert(d), "drug_class": d.get("drug_class"),
        "signed_at": o.signed_at, "prescriber": o.signed_by.display_name if o.signed_by else None,
        "safety_warnings": o.safety_warnings or [], "override_reason": o.safety_override_reason, "notes": o.notes,
        "status_reason": o.cancelled_reason,
        "verification": {"status": v.status, "note": v.note, "at": v.at, "pharmacist": _name(ctx, v.pharmacist_id),
                         "manual_interaction_review": v.manual_interaction_review} if v else None,
    }


# ---------------------------------------------------------------------------------------------- lifecycle actions

class DecisionIn(BaseModel):
    decision: Literal["verified", "rejected", "clarify"]
    note: str | None = Field(default=None, max_length=1000)
    manual_interaction_review: bool = False


@router.post("/orders/{oid}/pharmacy-decision")
def pharmacy_decision(oid: uuid.UUID, body: DecisionIn, ctx: TenantContext = Depends(require(P.PHARMACY_VERIFY))):
    o = _med_order(ctx, oid)
    try:
        MED.decide(ctx.db, o, pharmacist_id=ctx.user.id, decision=body.decision, note=body.note,
                   manual_interaction_review=body.manual_interaction_review)
    except MED.MedicationError as e:
        _conflict(e)
    if body.decision != "verified" and o.signed_by_id:
        notify(ctx.db, ctx.org_id, o.signed_by_id, "pharmacy", f"Pharmacist {'rejected' if body.decision == 'rejected' else 'needs clarification'}: {o.title}",
               body.note, f"/patients/{o.patient_id}/mar")
    ctx.audit(f"medication.{body.decision}", resource_type="order", resource_id=o.id, patient_id=o.patient_id,
              details={"manual_interaction_review": body.manual_interaction_review, "status": o.status})
    ctx.db.commit()
    return med_order_out(ctx, o)


class NoteIn(BaseModel):
    note: str = Field(min_length=3, max_length=1000)


@router.post("/orders/{oid}/resubmit")
def resubmit(oid: uuid.UUID, body: NoteIn, ctx: TenantContext = Depends(require(P.ORDERS_SIGN))):
    o = _med_order(ctx, oid, P.CLINICAL_WRITE)
    try:
        MED.resubmit(o, body.note)
    except MED.MedicationError as e:
        _conflict(e)
    ctx.audit("medication.resubmitted", resource_type="order", resource_id=o.id, patient_id=o.patient_id)
    ctx.db.commit()
    return med_order_out(ctx, o)


class HoldIn(BaseModel):
    hold: bool
    reason: str | None = Field(default=None, max_length=300)


@router.post("/orders/{oid}/hold")
def hold(oid: uuid.UUID, body: HoldIn, ctx: TenantContext = Depends(require(P.ORDERS_SIGN))):
    o = _med_order(ctx, oid, P.CLINICAL_WRITE)
    try:
        MED.set_hold(o, body.hold, body.reason)
    except MED.MedicationError as e:
        _conflict(e)
    ctx.audit("medication.held" if body.hold else "medication.resumed", resource_type="order", resource_id=o.id, patient_id=o.patient_id,
              details={"reason": body.reason})
    ctx.db.commit()
    return med_order_out(ctx, o)


@router.post("/orders/{oid}/discontinue")
def discontinue(oid: uuid.UUID, body: NoteIn, ctx: TenantContext = Depends(require(P.ORDERS_SIGN))):
    o = _med_order(ctx, oid, P.CLINICAL_WRITE)
    try:
        MED.discontinue(ctx.db, o, actor_id=ctx.user.id, reason=body.note)
    except MED.MedicationError as e:
        _conflict(e)
    ctx.audit("medication.discontinued", resource_type="order", resource_id=o.id, patient_id=o.patient_id, details={"reason": body.note})
    ctx.db.commit()
    return med_order_out(ctx, o)


# ---------------------------------------------------------------------------------------------- eMAR

def _admin_out(ctx: TenantContext, m: MedicationAdministration, witnesses: dict) -> dict:
    w = witnesses.get(m.id)
    return {"id": m.id, "order_id": m.order_id, "scheduled_for": m.scheduled_for, "status": m.status, "dose": m.dose, "route": m.route,
            "site": m.site, "reason": m.reason, "late": m.late, "administered_at": m.administered_at,
            "administered_by": _name(ctx, m.administered_by_id), "scan": m.scan, "requires_witness": m.requires_witness,
            "witness": {"name": _name(ctx, w.witness_id), "at": w.at} if w else None}


@router.get("/mar/patients/{patient_id}")
def patient_mar(patient_id: uuid.UUID, hours_back: int = Query(12, ge=1, le=96), hours_ahead: int = Query(24, ge=1, le=72),
                ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    p = get_patient(ctx, patient_id)
    t = now()
    start, end = t - timedelta(hours=hours_back), t + timedelta(hours=hours_ahead)
    orders = ctx.db.scalars(select(Order).where(Order.organization_id == ctx.org_id, Order.patient_id == p.id, Order.order_type == "medication",
                                                Order.status.notin_(("draft", "cancelled")))
                            .order_by(Order.signed_at.desc())).all()
    orders = [o for o in orders if MED.is_inpatient(o) and (o.status not in ("discontinued", "completed", "rejected")
                                                            or (o.updated_at and o.updated_at > start))]
    admins = ctx.db.scalars(select(MedicationAdministration).where(MedicationAdministration.order_id.in_([o.id for o in orders]))
                            .order_by(MedicationAdministration.administered_at)).all() if orders else []
    wit = {w.administration_id: w for w in ctx.db.scalars(select(MedicationAdministrationWitness).where(
        MedicationAdministrationWitness.administration_id.in_([m.id for m in admins])))} if admins else {}
    rows = []
    for o in orders:
        mine = [m for m in admins if m.order_id == o.id]
        verified_at = MED._verified_at(ctx.db, o)
        documented = {m.scheduled_for: m for m in mine if m.scheduled_for}
        sched = []
        for s in MED.slots(ctx.db, o, start, end, verified_at) if o.status in ("active", "on_hold", "completed", "discontinued") else []:
            m = documented.get(s)
            state = m.status if m else ("due" if abs((t - s).total_seconds()) <= MED.LATE_MINUTES * 60
                                        else "overdue" if t > s else "scheduled")
            sched.append({"at": s, "state": state, "administration_id": m.id if m else None})
        rows.append({**med_order_out(ctx, o), "slots": sched, "verified_at": verified_at,
                     "administrations": [_admin_out(ctx, m, wit) for m in mine],
                     "awaiting_witness": [m.id for m in mine if m.requires_witness and m.id not in wit]})
    return {"patient": {"id": p.id, "name": p.full_name, "mrn": p.mrn, "wristband": MED.patient_barcode(p)},
            "window": {"start": start, "end": end, "now": t}, "orders": rows,
            "scanning": "simulated", "screening": "unavailable"}


class AdministerIn(BaseModel):
    order_id: uuid.UUID
    status: Literal["given", "held", "refused", "omitted"]
    scheduled_for: datetime | None = None
    dose: str | None = Field(default=None, max_length=60)
    route: str | None = Field(default=None, max_length=40)
    site: str | None = Field(default=None, max_length=60)
    reason: str | None = Field(default=None, max_length=1000)
    patient_barcode: str | None = Field(default=None, max_length=80)
    medication_barcode: str | None = Field(default=None, max_length=80)


@router.post("/mar/administrations", status_code=201)
def administer(body: AdministerIn, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    o = _med_order(ctx, body.order_id, P.CLINICAL_WRITE)
    try:
        m = MED.administer(ctx.db, o, MED.AdministrationInput(**body.model_dump()), actor_id=ctx.user.id)
        ctx.db.flush()
    except MED.MedicationError as e:
        ctx.db.rollback()
        ctx.audit("medication.administration_blocked", resource_type="order", resource_id=o.id, patient_id=o.patient_id,
                  details={"code": e.code, "status": body.status})
        ctx.db.commit()
        _conflict(e)
    ctx.audit(f"medication.{m.status}", resource_type="medication_administration", resource_id=m.id, patient_id=o.patient_id,
              details={"order_id": str(o.id), "late": m.late, "requires_witness": m.requires_witness, "scan": m.scan})
    ctx.db.commit()
    return _admin_out(ctx, m, {})


@router.post("/mar/administrations/{aid}/witness", status_code=201)
def witness(aid: uuid.UUID, body: NoteIn | None = None, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    m = ctx.db.get(MedicationAdministration, aid)
    if not m or m.organization_id != ctx.org_id:
        raise not_found("Administration")
    get_patient(ctx, m.patient_id)
    try:
        MED.witness(ctx.db, m, witness_id=ctx.user.id, note=body.note if body else None)
    except MED.MedicationError as e:
        _conflict(e)
    ctx.audit("medication.witnessed", resource_type="medication_administration", resource_id=m.id, patient_id=m.patient_id)
    ctx.db.commit()
    return {"message": "Witnessed"}


@router.get("/mar/orders/{oid}/dose-labels")
def dose_labels(oid: uuid.UUID, ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    """Pharmacy dispensing labels for this order (used by the simulated scanner)."""
    o = _med_order(ctx, oid)
    rows = ctx.db.execute(select(StockMovement, InventoryLot, InventoryItem).join(InventoryLot, InventoryLot.id == StockMovement.lot_id)
                          .join(InventoryItem, InventoryItem.id == StockMovement.item_id)
                          .where(StockMovement.organization_id == ctx.org_id, StockMovement.kind == "dispense",
                                 StockMovement.reference_type == "order", StockMovement.reference_id == str(o.id))
                          .order_by(StockMovement.created_at.desc())).all()
    return [{"barcode": MED.dose_label_barcode(m.id), "item": i.name, "strength": i.strength, "lot": lot.lot_number,
             "quantity": m.quantity, "dispensed_at": m.created_at} for m, lot, i in rows]


# ---------------------------------------------------------------------------------------------- pharmacy queue

@router.get("/pharmacy/medication-queue")
def medication_queue(status: Literal["pending_verification", "clarification_needed", "active"] = "pending_verification",
                     ctx: TenantContext = Depends(require(P.PHARMACY_READ))):
    rows = ctx.db.execute(select(Order, Patient).join(Patient, Patient.id == Order.patient_id)
                          .where(Order.organization_id == ctx.org_id, Order.order_type == "medication", Order.status == status,
                                 Patient.is_restricted.is_(False))
                          .order_by(case((Order.priority == "stat", 0), (Order.priority == "urgent", 1), else_=2), Order.signed_at)).all()
    t = now()
    return [{**med_order_out(ctx, o), "patient": {"id": p.id, "name": p.full_name, "mrn": p.mrn},
             "waiting_minutes": int((t - o.signed_at).total_seconds() // 60) if o.signed_at else None} for o, p in rows]


__all__ = ["router", "MedicationVerification"]
