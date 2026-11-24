"""Clinical orders: medications, labs, imaging, referrals.

External transmission (e-prescribing, lab/imaging interfaces, referral delivery) is SIMULATED: every transmission
record carries `simulated: true` and the UI labels it. Results arrive only via the explicit simulate endpoint
(synthetic organizations) or a future interface adapter.
"""

import random
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select

from app.api.deps import TenantContext, get_ctx, require
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.data import catalogs
from app.integrations import adapters
from app.models import Allergy, Encounter, LabResult, Order, Organization, Patient, PatientMedication
from app.schemas.common import Page
from app.services import medication as MED
from app.services.notify import notify
from app.services.patients import get_patient

router = APIRouter(tags=["orders"])


# ---------- Type-specific details ----------

class MedicationDetails(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    strength: str = Field(min_length=1, max_length=60)
    form: str | None = None
    route: str | None = None
    sig: str = Field(min_length=3, max_length=500)
    quantity: int = Field(ge=1, le=1000)
    refills: int = Field(ge=0, le=11)
    days_supply: int | None = Field(default=None, ge=1, le=365)
    dispense_as_written: bool = False
    pharmacy: str | None = Field(default=None, max_length=200)
    # Inpatient (eMAR) fields. `setting` defaults from the patient's current admission when the order is signed.
    setting: Literal["inpatient", "outpatient"] | None = None
    dose: str | None = Field(default=None, max_length=60)          # per-administration dose; defaults to strength
    frequency: Literal["once", "daily", "bid", "tid", "qid", "q4h", "q6h", "q8h", "q12h", "prn"] | None = None
    prn_interval_hours: float | None = Field(default=None, ge=0.5, le=72)
    prn_reason: str | None = Field(default=None, max_length=200)


class LabDetails(BaseModel):
    code: str
    fasting: bool = False
    specimen: str | None = None


class ImagingDetails(BaseModel):
    code: str
    laterality: Literal["left", "right", "bilateral", "n/a"] = "n/a"
    contrast: bool = False
    clinical_question: str = Field(min_length=3, max_length=500)


class ReferralDetails(BaseModel):
    specialty: str = Field(min_length=2, max_length=80)
    specialist_name: str | None = None
    specialist_org: str | None = None
    specialist_phone: str | None = None
    reason: str = Field(min_length=5, max_length=1000)


DETAIL_MODELS = {"medication": MedicationDetails, "lab": LabDetails, "imaging": ImagingDetails, "referral": ReferralDetails}


class OrderIn(BaseModel):
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None = None
    order_type: Literal["medication", "lab", "imaging", "referral"]
    priority: Literal["routine", "urgent", "stat"] = "routine"
    details: dict
    indication_codes: list[str] = Field(default_factory=list, max_length=8)
    notes: str | None = Field(default=None, max_length=2000)


class OrderUpdate(BaseModel):
    priority: Literal["routine", "urgent", "stat"] | None = None
    details: dict | None = None
    indication_codes: list[str] | None = None
    notes: str | None = None


class SignIn(BaseModel):
    override_reason: str | None = Field(default=None, max_length=500)


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class ReferralStatusIn(BaseModel):
    status: Literal["in_progress", "completed"]
    note: str | None = Field(default=None, max_length=1000)


class ResultOut(BaseModel):
    id: uuid.UUID
    name: str
    value: str
    unit: str | None
    reference_range: str | None
    flag: str
    status: str
    resulted_at: datetime
    source: str


class OrderOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    patient: dict
    encounter_id: uuid.UUID | None
    order_type: str
    status: str
    priority: str
    title: str
    code: str | None
    details: dict
    indication_codes: list[str]
    notes: str | None
    ordered_by: str
    signed_by: str | None
    signed_at: datetime | None
    safety_warnings: list | None
    safety_override_reason: str | None
    transmitted_at: datetime | None
    transmission: dict | None
    resulted_at: datetime | None
    result_text: str | None
    results: list[ResultOut]
    results_reviewed_at: datetime | None
    released_to_patient_at: datetime | None
    cancelled_reason: str | None
    created_at: datetime


def order_out(o: Order, p: Patient | None = None) -> OrderOut:
    p = p or o.__dict__.get("_patient")
    return OrderOut(
        id=o.id, patient_id=o.patient_id,
        patient={"id": str(p.id), "name": p.full_name, "mrn": p.mrn, "date_of_birth": p.date_of_birth.isoformat()} if p else {},
        encounter_id=o.encounter_id, order_type=o.order_type, status=o.status, priority=o.priority, title=o.title, code=o.code,
        details=o.details, indication_codes=o.indication_codes or [], notes=o.notes, ordered_by=o.ordered_by.display_name,
        signed_by=o.signed_by.display_name if o.signed_by else None, signed_at=o.signed_at, safety_warnings=o.safety_warnings,
        safety_override_reason=o.safety_override_reason, transmitted_at=o.transmitted_at, transmission=o.transmission,
        resulted_at=o.resulted_at, result_text=o.result_text, results=[ResultOut.model_validate(r, from_attributes=True) for r in o.results],
        results_reviewed_at=o.results_reviewed_at, released_to_patient_at=o.released_to_patient_at,
        cancelled_reason=o.cancelled_reason, created_at=o.created_at,
    )


def _with_patients(ctx: TenantContext, orders: list[Order]) -> list[OrderOut]:
    pats = {p.id: p for p in ctx.db.scalars(select(Patient).where(Patient.id.in_({o.patient_id for o in orders}))).all()}
    return [order_out(o, pats.get(o.patient_id)) for o in orders]


def _normalize(order_type: str, raw: dict) -> tuple[dict, str, str | None]:
    try:
        d = DETAIL_MODELS[order_type](**raw)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from None
    if order_type == "medication":
        cat = catalogs.medication(d.name)
        return d.model_dump() | {"drug_class": cat["drug_class"] if cat else None}, f"{d.name} {d.strength}", None
    if order_type == "lab":
        lab = catalogs.lab(d.code)
        if not lab:
            raise bad_request("Unknown lab test")
        return d.model_dump() | {"specimen": d.specimen or lab[2]}, lab[1], lab[0]
    if order_type == "imaging":
        img = catalogs.imaging(d.code)
        if not img:
            raise bad_request("Unknown imaging study")
        lat = f" ({d.laterality})" if d.laterality != "n/a" else ""
        return d.model_dump(), f"{img['name']}{lat}", img["code"]
    return d.model_dump(), f"Referral to {d.specialty}", None


def safety_checks(ctx: TenantContext, o: Order) -> list[dict]:
    """Basic, explainable checks only — not a comprehensive clinical decision support system."""
    if o.order_type != "medication":
        return []
    warnings: list[dict] = []
    drug_class = (o.details or {}).get("drug_class")
    name = (o.details or {}).get("name", "").lower()
    allergies = ctx.db.scalars(select(Allergy).where(Allergy.patient_id == o.patient_id, Allergy.status == "active")).all()
    for a in allergies:
        sub = a.substance.lower()
        implied = set().union(*[v for k, v in catalogs.ALLERGY_CLASSES.items() if k in sub]) if any(k in sub for k in catalogs.ALLERGY_CLASSES) else set()
        if sub in name or (drug_class and drug_class in implied):
            warnings.append({"type": "allergy", "severity": "high" if a.severity in ("severe", "life_threatening") else "moderate",
                             "message": f"Patient has a recorded {a.severity.replace('_', '-')} allergy to {a.substance}"
                                        f"{f' ({a.reaction})' if a.reaction else ''}; {o.details.get('name')} is in a related class."})
    active = ctx.db.scalars(select(PatientMedication).where(PatientMedication.patient_id == o.patient_id,
                                                            PatientMedication.status == "active")).all()
    for m in active:
        if m.name.lower().split()[0] == name.split()[0] if name else False:
            warnings.append({"type": "duplicate", "severity": "moderate",
                             "message": f"Patient already has {m.name} {m.dose or ''} on their active medication list."})
        elif drug_class and (cat := catalogs.medication(m.name)) and cat["drug_class"] == drug_class:
            warnings.append({"type": "duplicate_class", "severity": "low",
                             "message": f"Same therapeutic class as active medication {m.name}."})
    notice = MED.screening_warning(o.details or {}, [m.name for m in active])
    if notice:
        warnings.append(notice)
    return warnings


def _order(ctx: TenantContext, oid: uuid.UUID, perm: str = P.CLINICAL_READ) -> Order:
    o = ctx.db.get(Order, oid)
    if not o or o.organization_id != ctx.org_id:
        raise not_found("Order")
    get_patient(ctx, o.patient_id, perm)
    return o


# ---------- Catalog ----------

@router.get("/catalog/medications")
def cat_meds(q: str = Query(min_length=1), ctx: TenantContext = Depends(require(P.ORDERS_WRITE))):
    return catalogs.search_medications(q)


@router.get("/catalog/labs")
def cat_labs(q: str = "", ctx: TenantContext = Depends(require(P.ORDERS_WRITE))):
    return catalogs.search_labs(q)


@router.get("/catalog/imaging")
def cat_imaging(q: str = "", ctx: TenantContext = Depends(require(P.ORDERS_WRITE))):
    return catalogs.search_imaging(q)


@router.get("/catalog/specialists")
def cat_specialists(specialty: str | None = None, ctx: TenantContext = Depends(require(P.ORDERS_WRITE))):
    return {"specialties": sorted({s[0] for s in catalogs.SPECIALISTS}), "specialists": catalogs.specialists(specialty)}


# ---------- Orders ----------

@router.post("/orders", response_model=OrderOut, status_code=201)
def create_order(body: OrderIn, ctx: TenantContext = Depends(require(P.ORDERS_WRITE))):
    p = get_patient(ctx, body.patient_id, P.CLINICAL_WRITE)
    if body.encounter_id:
        e = ctx.db.get(Encounter, body.encounter_id)
        if not e or e.organization_id != ctx.org_id or e.patient_id != p.id:
            raise bad_request("Encounter doesn't belong to this patient")
    details, title, code = _normalize(body.order_type, body.details)
    o = Order(organization_id=ctx.org_id, patient_id=p.id, encounter_id=body.encounter_id, order_type=body.order_type,
              priority=body.priority, title=title, code=code, details=details, indication_codes=[c.upper() for c in body.indication_codes],
              notes=body.notes, ordered_by_id=ctx.user.id)
    ctx.db.add(o)
    ctx.db.flush()
    o.safety_warnings = safety_checks(ctx, o)
    ctx.audit("order.drafted", resource_type="order", resource_id=o.id, patient_id=p.id, details={"type": body.order_type})
    ctx.db.commit()
    ctx.db.refresh(o)
    return order_out(o, p)


@router.patch("/orders/{oid}", response_model=OrderOut)
def update_order(oid: uuid.UUID, body: OrderUpdate, ctx: TenantContext = Depends(require(P.ORDERS_WRITE))):
    o = _order(ctx, oid, P.CLINICAL_WRITE)
    if o.status != "draft":
        raise bad_request("Only draft orders can be edited")
    if body.details is not None:
        o.details, o.title, o.code = _normalize(o.order_type, body.details)
    for k in ("priority", "notes"):
        if getattr(body, k) is not None:
            setattr(o, k, getattr(body, k))
    if body.indication_codes is not None:
        o.indication_codes = [c.upper() for c in body.indication_codes]
    o.safety_warnings = safety_checks(ctx, o)
    ctx.db.commit()
    return order_out(o, ctx.db.get(Patient, o.patient_id))


@router.post("/orders/{oid}/sign", response_model=OrderOut)
def sign_order(oid: uuid.UUID, body: SignIn, ctx: TenantContext = Depends(require(P.ORDERS_SIGN))):
    o = _order(ctx, oid, P.CLINICAL_WRITE)
    if o.status != "draft":
        raise bad_request("Order is not a draft")
    if ctx.provider is None:
        raise forbidden("Only clinicians with a provider profile can sign orders")
    warnings = safety_checks(ctx, o)
    o.safety_warnings = warnings
    blocking = [w for w in warnings if w.get("severity") != "info"]
    if blocking and not (body.override_reason and body.override_reason.strip()):
        ctx.db.commit()
        raise HTTPException(409, {"code": "safety_warnings", "message": "Review the safety warnings and give an override reason to sign.",
                                  "warnings": warnings})
    ts = now()
    o.status, o.signed_by_id, o.signed_at = "signed", ctx.user.id, ts
    o.safety_override_reason = body.override_reason if blocking else None
    if o.order_type == "medication":
        # Inpatient → pharmacist verification queue (never "completed" by signing); outpatient → simulated e-prescribing.
        try:
            MED.on_sign(ctx.db, o, actor_id=ctx.user.id, org_id=ctx.org_id)
        except MED.MedicationError as e:
            ctx.db.rollback()
            raise HTTPException(409, {"code": e.code, "message": str(e)}) from None
        if o.details.get("setting") == "outpatient":
            o.transmission = adapters.order_transmitter().transmit(o.order_type, o.details, o.id)
    else:
        o.transmission = adapters.order_transmitter().transmit(o.order_type, o.details, o.id)
        o.status = "transmitted"
    o.transmitted_at = ts
    ctx.audit("order.signed", resource_type="order", resource_id=o.id, patient_id=o.patient_id,
              details={"type": o.order_type, "override": bool(o.safety_override_reason), "warnings": len(warnings),
                       "simulated_transmission": bool((o.transmission or {}).get("simulated")), "status": o.status})
    ctx.db.commit()
    ctx.db.refresh(o)
    return order_out(o, ctx.db.get(Patient, o.patient_id))


@router.post("/orders/{oid}/cancel", response_model=OrderOut)
def cancel_order(oid: uuid.UUID, body: CancelIn, ctx: TenantContext = Depends(require(P.ORDERS_WRITE))):
    o = _order(ctx, oid, P.CLINICAL_WRITE)
    if o.status in ("resulted", "completed", "cancelled", "rejected", "discontinued"):
        raise bad_request(f"Can't cancel an order that is {o.status}")
    if MED.is_inpatient(o) and o.status != "draft":
        raise bad_request("Signed inpatient medication orders are discontinued, not cancelled, so the administration history is kept")
    if o.status != "draft" and not ctx.can(P.ORDERS_SIGN):
        raise forbidden("Only a signing clinician can cancel a transmitted order")
    o.status, o.cancelled_reason = "cancelled", body.reason
    ctx.audit("order.cancelled", resource_type="order", resource_id=o.id, patient_id=o.patient_id)
    ctx.db.commit()
    return order_out(o, ctx.db.get(Patient, o.patient_id))


def _flag(val: float, lo, hi) -> str:
    if lo is None:
        return "normal"
    if val < lo * 0.7:
        return "critical_low"
    if val > hi * 1.6 and hi > 0:
        return "critical_high"
    return "low" if val < lo else "high" if val > hi else "normal"


@router.post("/orders/{oid}/simulate-result", response_model=OrderOut)
def simulate_result(oid: uuid.UUID, ctx: TenantContext = Depends(require(P.ORDERS_WRITE))):
    """Synthetic organizations only: produce plausible results so the review workflow can be exercised."""
    o = _order(ctx, oid)
    org = ctx.db.get(Organization, ctx.org_id)
    if not (org.settings or {}).get("synthetic_data"):
        raise forbidden("Simulated results are only available in synthetic test organizations.")
    if o.order_type not in ("lab", "imaging") or o.status not in ("transmitted", "in_progress"):
        raise bad_request("Only transmitted lab or imaging orders can receive results")
    rng = random.Random(str(o.id))
    ts = now()
    if o.order_type == "lab":
        _, _, _, comps = catalogs.lab(o.code)
        for name, unit, lo, hi, tlo, thi in comps:
            if lo is None:
                v, rr, flag = rng.choice(["Not detected", "Not detected", "Detected"]), "Not detected", "normal"
                if v == "Detected":
                    flag = "abnormal"
            else:
                digits = 3 if hi < 2 else 1 if hi < 20 else 0
                val = round(rng.uniform(tlo, thi), digits)
                v, rr, flag = (f"{val:.{digits}f}" if digits else str(int(val))), f"{lo}-{hi}", _flag(val, lo, hi)
            ctx.db.add(LabResult(organization_id=ctx.org_id, order_id=o.id, patient_id=o.patient_id, name=name, value=v,
                                 unit=unit or None, reference_range=rr, flag=flag, resulted_at=ts, source="simulated"))
    else:
        o.result_text = rng.choice([
            "FINDINGS: No acute abnormality. IMPRESSION: Normal study. (SIMULATED REPORT)",
            "FINDINGS: Mild degenerative changes. No fracture or dislocation. IMPRESSION: Mild degenerative change. (SIMULATED REPORT)",
        ])
    o.status, o.resulted_at = "resulted", ts
    ctx.db.flush()
    ctx.db.refresh(o)
    critical = any(r.flag.startswith("critical") for r in o.results)
    abnormal = sum(r.flag != "normal" for r in o.results)
    signer = o.signed_by_id or o.ordered_by_id
    p = ctx.db.get(Patient, o.patient_id)
    notify(ctx.db, ctx.org_id, signer, "critical_result" if critical else "result",
           f"{'CRITICAL ' if critical else ''}Result: {o.title} — {p.full_name}",
           f"{abnormal} abnormal value(s)" if o.order_type == "lab" else "Imaging report available", f"/patients/{p.id}/results")
    from app.services.automation import emit

    emit(ctx.db, ctx.org_id, "order.resulted", {
        "subject_type": "order", "subject_id": o.id, "patient_id": o.patient_id, "patient_name": p.full_name, "title": o.title,
        "abnormal": abnormal > 0, "critical": critical, "ordering_user_id": str(signer)})
    ctx.audit("order.resulted", resource_type="order", resource_id=o.id, patient_id=o.patient_id, details={"simulated": True, "critical": critical})
    ctx.db.commit()
    return order_out(o, p)


def _notify_patient_release(ctx: TenantContext, o: Order) -> None:
    p = ctx.db.get(Patient, o.patient_id)
    if p and p.portal_user_id:
        notify(ctx.db, ctx.org_id, p.portal_user_id, "result_released", "New test results are available", o.title, "/portal/results")


@router.post("/orders/{oid}/review", response_model=OrderOut)
def review_results(oid: uuid.UUID, release_to_patient: bool = False, ctx: TenantContext = Depends(require(P.ORDERS_SIGN))):
    o = _order(ctx, oid)
    if o.status != "resulted":
        raise bad_request("No results awaiting review")
    o.results_reviewed_by_id, o.results_reviewed_at, o.status = ctx.user.id, now(), "completed"
    if release_to_patient:
        o.released_to_patient_at = now()
        _notify_patient_release(ctx, o)
    ctx.audit("order.results_reviewed", resource_type="order", resource_id=o.id, patient_id=o.patient_id,
              details={"released": release_to_patient})
    ctx.db.commit()
    return order_out(o, ctx.db.get(Patient, o.patient_id))


@router.post("/orders/{oid}/release", response_model=OrderOut)
def release_results(oid: uuid.UUID, ctx: TenantContext = Depends(require(P.ORDERS_SIGN))):
    o = _order(ctx, oid)
    if not o.results_reviewed_at:
        raise bad_request("Results must be reviewed before release")
    from app.models import LabResult

    if ctx.db.scalar(select(LabResult.id).where(LabResult.order_id == o.id, LabResult.status == "preliminary").limit(1)):
        raise bad_request("Unverified (preliminary) results can't be released to the patient")
    if not o.released_to_patient_at:
        o.released_to_patient_at = now()
        _notify_patient_release(ctx, o)
    ctx.audit("order.results_released", resource_type="order", resource_id=o.id, patient_id=o.patient_id)
    ctx.db.commit()
    return order_out(o, ctx.db.get(Patient, o.patient_id))


@router.post("/orders/{oid}/referral-status", response_model=OrderOut)
def referral_status(oid: uuid.UUID, body: ReferralStatusIn, ctx: TenantContext = Depends(require(P.ORDERS_WRITE))):
    o = _order(ctx, oid, P.CLINICAL_WRITE)
    if o.order_type != "referral" or o.status not in ("transmitted", "in_progress"):
        raise bad_request("Only sent referrals can be updated")
    o.status = body.status
    if body.note:
        o.result_text = ((o.result_text or "") + f"\n[{now():%Y-%m-%d}] {body.note}").strip()
    if body.status == "completed":
        o.resulted_at = now()
    ctx.audit("order.referral_updated", resource_type="order", resource_id=o.id, patient_id=o.patient_id, details={"status": body.status})
    ctx.db.commit()
    return order_out(o, ctx.db.get(Patient, o.patient_id))


@router.get("/orders/{oid}", response_model=OrderOut)
def get_order(oid: uuid.UUID, ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    o = _order(ctx, oid)
    return order_out(o, ctx.db.get(Patient, o.patient_id))


@router.get("/patients/{patient_id}/orders", response_model=list[OrderOut])
def patient_orders(patient_id: uuid.UUID, encounter_id: uuid.UUID | None = None, order_type: str | None = None,
                   ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id, P.CLINICAL_READ)
    q = select(Order).where(Order.patient_id == p.id)
    if ctx.is_patient_only:  # portal: released results only
        q = q.where(Order.released_to_patient_at.is_not(None))
    if encounter_id:
        q = q.where(Order.encounter_id == encounter_id)
    if order_type:
        q = q.where(Order.order_type == order_type)
    out = [order_out(o, p) for o in ctx.db.scalars(q.order_by(Order.created_at.desc()).limit(300)).all()]
    if ctx.is_patient_only:
        for o in out:
            o.results = [r for r in o.results if r.status == "final"]
    return out


@router.get("/patients/{patient_id}/results")
def patient_results(patient_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id, P.CLINICAL_READ)
    q = select(LabResult, Order.title, Order.released_to_patient_at, Order.results_reviewed_at).join(Order, Order.id == LabResult.order_id).where(LabResult.patient_id == p.id)
    if ctx.is_patient_only:  # patients see released, verified (final) values only
        q = q.where(Order.released_to_patient_at.is_not(None), LabResult.status == "final")
    rows = ctx.db.execute(q.order_by(LabResult.resulted_at.desc())).all()
    return [{**ResultOut.model_validate(r, from_attributes=True).model_dump(), "order_id": r.order_id, "panel": title,
             "reviewed": reviewed is not None, "released": released is not None} for r, title, released, reviewed in rows]


@router.get("/orders", response_model=Page[OrderOut])
def worklist(
    queue: Literal["to_sign", "results", "pending", "referrals", "all"] = "all", mine: bool = False,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), ctx: TenantContext = Depends(require(P.CLINICAL_READ)),
):
    q = select(Order).join(Patient, Patient.id == Order.patient_id).where(Order.organization_id == ctx.org_id, Patient.is_restricted.is_(False))
    q = {
        "to_sign": q.where(Order.status == "draft"),
        "results": q.where(Order.status == "resulted"),
        "pending": q.where(Order.status.in_(("transmitted", "in_progress")), Order.order_type.in_(("lab", "imaging"))),
        "referrals": q.where(Order.order_type == "referral", Order.status.in_(("transmitted", "in_progress", "draft"))),
        "all": q,
    }[queue]
    if mine:
        q = q.where((Order.signed_by_id == ctx.user.id) | (Order.ordered_by_id == ctx.user.id))
    total = ctx.db.scalar(select(func.count()).select_from(q.subquery()))
    rows = ctx.db.scalars(q.order_by(Order.priority.desc(), Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=_with_patients(ctx, rows), total=total, page=page, page_size=page_size)


@router.get("/orders-counts")
def worklist_counts(ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    base = select(func.count()).select_from(Order).join(Patient, Patient.id == Order.patient_id).where(
        Order.organization_id == ctx.org_id, Patient.is_restricted.is_(False))
    return {
        "to_sign": ctx.db.scalar(base.where(Order.status == "draft")),
        "results": ctx.db.scalar(base.where(Order.status == "resulted")),
        "pending": ctx.db.scalar(base.where(Order.status.in_(("transmitted", "in_progress")), Order.order_type.in_(("lab", "imaging")))),
        "referrals": ctx.db.scalar(base.where(Order.order_type == "referral", Order.status.in_(("transmitted", "in_progress", "draft")))),
    }
