"""Billing & revenue cycle. All amounts are integer cents.

Clearinghouse, payer adjudication and card processing are SIMULATED (deterministic, labeled). Claim submission and
payments require an `Idempotency-Key` header; replays return the original result instead of acting twice.
"""

import hashlib
import uuid
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, literal_column, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import TenantContext, require
from app.api.routers.portal import portal_patient
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.data.cpt_common import EM_ESTABLISHED, EM_NEW
from app.models import (
    Charge,
    Claim,
    ClaimEvent,
    ClaimSubmission,
    Encounter,
    FeeScheduleItem,
    Invoice,
    Order,
    Organization,
    Patient,
    PatientInsurance,
    Payment,
    ProviderProfile,
)
from app.schemas.common import Page
from app.services.notify import notify
from app.services.patients import get_patient

router = APIRouter(tags=["billing"])

DENIALS = {
    "CO-27": "Expenses incurred after coverage terminated",
    "CO-16": "Claim lacks information needed for adjudication",
    "CO-50": "Not deemed a medical necessity by the payer",
}


# ---------- helpers ----------

def _next_number(ctx: TenantContext, key: str, prefix: str) -> str:
    org = ctx.db.scalar(select(Organization).where(Organization.id == ctx.org_id).with_for_update())
    seq = int((org.settings or {}).get(key, 1000)) + 1
    org.settings = {**(org.settings or {}), key: seq}
    return f"{prefix}-{date.today():%y}-{seq}"


def _event(ctx: TenantContext, c: Claim, event: str, **details) -> None:
    ctx.db.add(ClaimEvent(organization_id=ctx.org_id, claim_id=c.id, event=event, details=details, actor_id=ctx.user.id))


def _require_key(key: str | None) -> str:
    if not key or not (8 <= len(key) <= 100):
        raise HTTPException(400, "An Idempotency-Key header (8-100 chars) is required for this operation")
    return key


def _synthetic(ctx: TenantContext) -> None:
    org = ctx.db.get(Organization, ctx.org_id)
    if not (org.settings or {}).get("synthetic_data"):
        raise forbidden("Simulated payer actions are only available in synthetic test organizations.")


def _encounter(ctx: TenantContext, eid: uuid.UUID) -> Encounter:
    e = ctx.db.get(Encounter, eid)
    if not e or e.organization_id != ctx.org_id:
        raise not_found("Encounter")
    get_patient(ctx, e.patient_id)
    return e


def _claim(ctx: TenantContext, cid: uuid.UUID) -> Claim:
    c = ctx.db.get(Claim, cid)
    if not c or c.organization_id != ctx.org_id:
        raise not_found("Claim")
    get_patient(ctx, c.patient_id)
    return c


def _primary_insurance(ctx: TenantContext, patient_id: uuid.UUID) -> PatientInsurance | None:
    return ctx.db.scalar(select(PatientInsurance).where(PatientInsurance.patient_id == patient_id, PatientInsurance.is_active.is_(True),
                                                        PatientInsurance.priority == "primary"))


# ---------- schemas ----------

class FeeIn(BaseModel):
    description: str = Field(min_length=2, max_length=200)
    price_cents: int = Field(ge=0, le=10_000_000)
    is_active: bool = True


class ChargeIn(BaseModel):
    code: str = Field(min_length=4, max_length=10)
    units: int = Field(1, ge=1, le=99)
    modifiers: list[str] = Field(default_factory=list, max_length=4)
    diagnosis_codes: list[str] = Field(default_factory=list, max_length=4)


class ClaimIn(BaseModel):
    encounter_id: uuid.UUID


class AppealIn(BaseModel):
    text: str = Field(min_length=20, max_length=5000)


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class PaymentIn(BaseModel):
    amount_cents: int = Field(gt=0, le=100_000_000)
    method: Literal["cash", "check", "card_simulated"]
    reference: str | None = Field(default=None, max_length=100)


class PortalPayIn(BaseModel):
    amount_cents: int = Field(gt=0, le=100_000_000)


def charge_out(ch: Charge) -> dict:
    return {"id": ch.id, "code": ch.code, "description": ch.description, "modifiers": ch.modifiers, "units": ch.units,
            "unit_price_cents": ch.unit_price_cents, "amount_cents": ch.amount_cents, "diagnosis_codes": ch.diagnosis_codes, "status": ch.status}


def claim_out(c: Claim, p: Patient | None = None) -> dict:
    return {
        "id": c.id, "claim_number": c.claim_number, "patient_id": c.patient_id,
        "patient": {"name": p.full_name, "mrn": p.mrn, "date_of_birth": p.date_of_birth} if p else None,
        "encounter_id": c.encounter_id, "payer_name": c.payer_name, "member_id": c.member_id, "service_date": c.service_date,
        "status": c.status, "total_charge_cents": c.total_charge_cents, "allowed_cents": c.allowed_cents, "paid_cents": c.paid_cents,
        "patient_responsibility_cents": c.patient_responsibility_cents, "adjustment_cents": c.adjustment_cents,
        "scrub_errors": c.scrub_errors, "clearinghouse_ref": c.clearinghouse_ref, "submitted_at": c.submitted_at,
        "adjudicated_at": c.adjudicated_at, "denial_code": c.denial_code, "denial_reason": c.denial_reason, "appeal_text": c.appeal_text,
        "appeal_submitted_at": c.appeal_submitted_at, "submission_count": c.submission_count, "created_at": c.created_at,
        "charges": [charge_out(ch) for ch in c.charges if ch.status != "void"],
        "events": [{"event": e.event, "details": e.details, "created_at": e.created_at} for e in c.events],
        "simulated": True,
    }


def invoice_out(i: Invoice, p: Patient | None = None) -> dict:
    return {"id": i.id, "number": i.number, "patient_id": i.patient_id, "patient": {"name": p.full_name, "mrn": p.mrn} if p else None,
            "claim_id": i.claim_id, "encounter_id": i.encounter_id, "description": i.description, "status": i.status,
            "total_cents": i.total_cents, "balance_cents": i.balance_cents, "issued_at": i.issued_at, "due_date": i.due_date}


def payment_out(pm: Payment) -> dict:
    return {"id": pm.id, "source": pm.source, "method": pm.method, "amount_cents": pm.amount_cents, "reference": pm.reference,
            "invoice_id": pm.invoice_id, "claim_id": pm.claim_id, "status": pm.status, "created_at": pm.created_at}


# ---------- fee schedule ----------

@router.get("/fee-schedule")
def fee_schedule(ctx: TenantContext = Depends(require(P.BILLING_READ))):
    rows = ctx.db.scalars(select(FeeScheduleItem).where(FeeScheduleItem.organization_id == ctx.org_id).order_by(FeeScheduleItem.code)).all()
    return [{"code": r.code, "description": r.description, "price_cents": r.price_cents, "is_active": r.is_active} for r in rows]


@router.put("/fee-schedule/{code}")
def set_fee(code: str, body: FeeIn, ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    item = ctx.db.scalar(select(FeeScheduleItem).where(FeeScheduleItem.organization_id == ctx.org_id, FeeScheduleItem.code == code.upper()))
    if not item:
        item = FeeScheduleItem(organization_id=ctx.org_id, code=code.upper())
        ctx.db.add(item)
    item.description, item.price_cents, item.is_active = body.description, body.price_cents, body.is_active
    ctx.audit("billing.fee_updated", resource_type="fee_schedule", resource_id=code.upper(), details={"price_cents": body.price_cents})
    ctx.db.commit()
    return {"code": item.code, "description": item.description, "price_cents": item.price_cents, "is_active": item.is_active}


# ---------- charge capture ----------

@router.get("/billing/charge-queue")
def charge_queue(days: int = Query(90, le=365), ctx: TenantContext = Depends(require(P.BILLING_READ))):
    """Completed encounters with no claim/invoice yet."""
    billed = select(Claim.encounter_id).where(Claim.status != "void")
    invoiced = select(Invoice.encounter_id).where(Invoice.encounter_id.is_not(None), Invoice.status != "void")
    encs = ctx.db.scalars(select(Encounter).join(Patient, Patient.id == Encounter.patient_id).where(
        Encounter.organization_id == ctx.org_id, Encounter.status == "completed", Encounter.completed_at >= now() - timedelta(days=days),
        Encounter.id.not_in(billed), Encounter.id.not_in(invoiced), Patient.is_restricted.is_(False))
        .order_by(Encounter.completed_at.desc()).limit(200)).all()
    pending = dict(ctx.db.execute(select(Charge.encounter_id, func.sum(Charge.amount_cents)).where(
        Charge.encounter_id.in_([e.id for e in encs]), Charge.status == "pending").group_by(Charge.encounter_id)).all())
    out = []
    for e in encs:
        ins = _primary_insurance(ctx, e.patient_id)
        out.append({"encounter_id": e.id, "patient": {"id": e.patient_id, "name": e.patient.full_name, "mrn": e.patient.mrn},
                    "provider": e.provider.user.display_name, "service_date": e.started_at, "chief_complaint": e.chief_complaint,
                    "diagnoses": [{"code": d.code, "description": d.description} for d in e.diagnoses],
                    "payer": ins.payer_name if ins else None, "charges_cents": pending.get(e.id)})
    return out


def _suggest(ctx: TenantContext, e: Encounter) -> list[dict]:
    """Transparent heuristic: new vs established by prior completed visits (3 y); level by number/chronicity of diagnoses."""
    prior = ctx.db.scalar(select(func.count()).select_from(Encounter).where(
        Encounter.patient_id == e.patient_id, Encounter.status == "completed", Encounter.id != e.id,
        Encounter.started_at >= e.started_at - timedelta(days=3 * 365), Encounter.started_at < e.started_at))
    n = len(e.diagnoses)
    level = 1 if n <= 1 else 2 if n == 2 else 3
    codes = (EM_ESTABLISHED if prior else EM_NEW)
    em = codes[level]  # index 1..3 → low / moderate / high complexity
    out = [{"code": em, "units": 1, "reason": f"{'Established' if prior else 'New'} patient; {n} diagnosis(es) addressed. Verify documentation supports this level.",
            "diagnosis_codes": [d.code for d in e.diagnoses][:4]}]
    if ctx.db.scalar(select(Order.id).where(Order.encounter_id == e.id, Order.order_type == "lab", Order.status != "cancelled").limit(1)):
        out.append({"code": "36415", "units": 1, "reason": "Lab ordered during visit (venipuncture, if drawn in clinic).", "diagnosis_codes": [d.code for d in e.diagnoses][:1]})
    return out


@router.get("/encounters/{eid}/charges")
def encounter_charges(eid: uuid.UUID, ctx: TenantContext = Depends(require(P.BILLING_READ))):
    e = _encounter(ctx, eid)
    rows = ctx.db.scalars(select(Charge).where(Charge.encounter_id == e.id, Charge.status != "void").order_by(Charge.created_at)).all()
    fees = {f.code: f for f in ctx.db.scalars(select(FeeScheduleItem).where(FeeScheduleItem.organization_id == ctx.org_id)).all()}
    sugg = [{**s, "description": fees[s["code"]].description if s["code"] in fees else s["code"],
             "unit_price_cents": fees[s["code"]].price_cents if s["code"] in fees else 0} for s in _suggest(ctx, e)]
    ins = _primary_insurance(ctx, e.patient_id)
    return {"encounter": {"id": e.id, "status": e.status, "service_date": e.started_at, "provider": e.provider.user.display_name,
                          "patient": {"id": e.patient_id, "name": e.patient.full_name, "mrn": e.patient.mrn},
                          "diagnoses": [{"code": d.code, "description": d.description} for d in e.diagnoses]},
            "insurance": {"payer_name": ins.payer_name, "member_id": ins.member_id, "eligibility_status": ins.eligibility_status} if ins else None,
            "charges": [charge_out(c) for c in rows], "suggestions": sugg}


@router.put("/encounters/{eid}/charges")
def set_charges(eid: uuid.UUID, lines: list[ChargeIn], ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    e = _encounter(ctx, eid)
    if e.status != "completed":
        raise bad_request("Charges can be captured once the visit is completed and signed")
    if ctx.db.scalar(select(Charge.id).where(Charge.encounter_id == e.id, Charge.status == "billed").limit(1)):
        raise bad_request("Charges were already billed on a claim; void the claim to change them")
    fees = {f.code: f for f in ctx.db.scalars(select(FeeScheduleItem).where(FeeScheduleItem.organization_id == ctx.org_id, FeeScheduleItem.is_active.is_(True))).all()}
    dx = {d.code for d in e.diagnoses}
    for ln in lines:
        if ln.code.upper() not in fees:
            raise bad_request(f"{ln.code} is not on the fee schedule")
        bad = [c for c in ln.diagnosis_codes if c.upper() not in dx]
        if bad:
            raise bad_request(f"Diagnosis {', '.join(bad)} isn't on this encounter")
    for old in ctx.db.scalars(select(Charge).where(Charge.encounter_id == e.id, Charge.status == "pending")).all():
        ctx.db.delete(old)
    for ln in lines:
        f = fees[ln.code.upper()]
        ctx.db.add(Charge(organization_id=ctx.org_id, encounter_id=e.id, patient_id=e.patient_id, code=f.code, description=f.description,
                          modifiers=[m.upper() for m in ln.modifiers], units=ln.units, unit_price_cents=f.price_cents,
                          amount_cents=f.price_cents * ln.units, diagnosis_codes=[c.upper() for c in ln.diagnosis_codes], created_by_id=ctx.user.id))
    ctx.audit("billing.charges_captured", resource_type="encounter", resource_id=e.id, patient_id=e.patient_id, details={"lines": len(lines)})
    ctx.db.commit()
    return encounter_charges(eid, ctx)


# ---------- claims ----------

def _scrub(ctx: TenantContext, c: Claim, charges: list[Charge]) -> list[str]:
    errs = []
    p = ctx.db.get(Patient, c.patient_id)
    prov = ctx.db.get(ProviderProfile, c.rendering_provider_id)
    ins = ctx.db.get(PatientInsurance, c.insurance_id) if c.insurance_id else None
    if not charges:
        errs.append("No charge lines")
    if any(not ch.diagnosis_codes for ch in charges):
        errs.append("Every line needs at least one diagnosis pointer")
    if not prov or not prov.npi:
        errs.append("Rendering provider NPI missing")
    if not ins or not ins.member_id:
        errs.append("Primary insurance member ID missing")
    elif ins.termination_date and ins.termination_date < c.service_date:
        errs.append("Coverage terminated before the date of service")
    if not (p.address_line1 and p.city and p.postal_code):
        errs.append("Patient address incomplete")
    return errs


@router.post("/claims", status_code=201)
def create_claim(body: ClaimIn, ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    e = _encounter(ctx, body.encounter_id)
    if e.status != "completed":
        raise bad_request("Only completed visits can be billed")
    if ctx.db.scalar(select(Claim.id).where(Claim.encounter_id == e.id, Claim.status != "void")):
        raise bad_request("A claim already exists for this visit")
    charges = ctx.db.scalars(select(Charge).where(Charge.encounter_id == e.id, Charge.status == "pending")).all()
    if not charges:
        raise bad_request("Capture charges first")
    ins = _primary_insurance(ctx, e.patient_id)
    if not ins:
        raise HTTPException(409, {"code": "self_pay", "message": "No active primary insurance — bill the patient directly."})
    c = Claim(organization_id=ctx.org_id, claim_number=_next_number(ctx, "claim_seq", "CLM"), patient_id=e.patient_id, encounter_id=e.id,
              insurance_id=ins.id, payer_name=ins.payer_name, member_id=ins.member_id, rendering_provider_id=e.provider_id,
              service_date=e.started_at.date(), total_charge_cents=sum(ch.amount_cents for ch in charges))
    ctx.db.add(c)
    ctx.db.flush()
    for ch in charges:
        ch.claim_id, ch.status = c.id, "billed"
    c.scrub_errors = _scrub(ctx, c, charges)
    c.status = "draft" if c.scrub_errors else "ready"
    _event(ctx, c, "created", scrub_errors=c.scrub_errors)
    ctx.audit("billing.claim_created", resource_type="claim", resource_id=c.id, patient_id=c.patient_id)
    ctx.db.commit()
    ctx.db.refresh(c)
    return claim_out(c, ctx.db.get(Patient, c.patient_id))


@router.post("/encounters/{eid}/self-pay-invoice", status_code=201)
def self_pay_invoice(eid: uuid.UUID, ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    e = _encounter(ctx, eid)
    charges = ctx.db.scalars(select(Charge).where(Charge.encounter_id == e.id, Charge.status == "pending")).all()
    if not charges:
        raise bad_request("Capture charges first")
    total = sum(ch.amount_cents for ch in charges)
    inv = Invoice(organization_id=ctx.org_id, number=_next_number(ctx, "invoice_seq", "INV"), patient_id=e.patient_id, encounter_id=e.id,
                  description=f"Visit {e.started_at:%b %d, %Y} (self-pay)", total_cents=total, balance_cents=total, due_date=date.today() + timedelta(days=30))
    ctx.db.add(inv)
    for ch in charges:
        ch.status = "billed"
    _notify_bill(ctx, e.patient_id, inv)
    ctx.audit("billing.invoice_created", resource_type="invoice", resource_id=None, patient_id=e.patient_id, details={"self_pay": True})
    ctx.db.commit()
    return invoice_out(inv)


@router.get("/claims")
def list_claims(status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, le=100),
                ctx: TenantContext = Depends(require(P.BILLING_READ))):
    q = select(Claim).where(Claim.organization_id == ctx.org_id)
    if status:
        q = q.where(Claim.status.in_(status.split(",")))
    total = ctx.db.scalar(select(func.count()).select_from(q.subquery()))
    rows = ctx.db.scalars(q.order_by(Claim.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    pats = {p.id: p for p in ctx.db.scalars(select(Patient).where(Patient.id.in_({r.patient_id for r in rows}))).all()}
    return Page(items=[claim_out(r, pats.get(r.patient_id)) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/claims/{cid}")
def get_claim(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.BILLING_READ))):
    c = _claim(ctx, cid)
    return claim_out(c, ctx.db.get(Patient, c.patient_id))


@router.post("/claims/{cid}/rescrub")
def rescrub(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    c = _claim(ctx, cid)
    if c.status not in ("draft", "ready", "rejected", "denied"):
        raise bad_request("Only unsubmitted, rejected or denied claims can be re-scrubbed")
    ins = _primary_insurance(ctx, c.patient_id)
    if ins:
        c.insurance_id, c.payer_name, c.member_id = ins.id, ins.payer_name, ins.member_id
    c.scrub_errors = _scrub(ctx, c, [ch for ch in c.charges if ch.status != "void"])
    if c.status in ("draft", "ready"):
        c.status = "draft" if c.scrub_errors else "ready"
    _event(ctx, c, "scrubbed", scrub_errors=c.scrub_errors)
    ctx.db.commit()
    return claim_out(c, ctx.db.get(Patient, c.patient_id))


@router.post("/claims/{cid}/submit")
def submit_claim(cid: uuid.UUID, idempotency_key: str | None = Header(default=None), ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    key = _require_key(idempotency_key)
    prior = ctx.db.scalar(select(ClaimSubmission).where(ClaimSubmission.organization_id == ctx.org_id, ClaimSubmission.idempotency_key == key))
    if prior:
        if prior.claim_id != cid:
            raise HTTPException(409, "This Idempotency-Key was already used for a different claim")
        return {**prior.response, "idempotent_replay": True}
    c = _claim(ctx, cid)
    if c.status not in ("ready", "rejected", "denied"):
        raise bad_request(f"Claim is {c.status}; only ready (or corrected rejected/denied) claims can be submitted")
    errs = _scrub(ctx, c, [ch for ch in c.charges if ch.status != "void"])
    if errs:
        c.scrub_errors, c.status = errs, "draft"
        ctx.db.commit()
        raise HTTPException(422, {"code": "scrub_failed", "message": "Fix claim errors before submitting", "errors": errs})
    ref = f"SIM-837-{hashlib.sha1(f'{c.id}{key}'.encode()).hexdigest()[:10].upper()}"
    c.status, c.clearinghouse_ref, c.submitted_at = "accepted", ref, now()  # mock clearinghouse accepts immediately (277CA)
    c.submission_count += 1
    c.denial_code = c.denial_reason = None
    _event(ctx, c, "submitted", clearinghouse_ref=ref, simulated=True)
    _event(ctx, c, "accepted_by_clearinghouse", simulated=True)
    response = {"claim_id": str(c.id), "status": c.status, "clearinghouse_ref": ref, "simulated": True}
    ctx.db.add(ClaimSubmission(organization_id=ctx.org_id, claim_id=c.id, idempotency_key=key, clearinghouse_ref=ref, response=response))
    ctx.audit("billing.claim_submitted", resource_type="claim", resource_id=c.id, patient_id=c.patient_id, details={"simulated": True})
    try:
        ctx.db.commit()
    except IntegrityError:  # concurrent request with the same key won the race
        ctx.db.rollback()
        prior = ctx.db.scalar(select(ClaimSubmission).where(ClaimSubmission.organization_id == ctx.org_id, ClaimSubmission.idempotency_key == key))
        return {**prior.response, "idempotent_replay": True}
    return {**response, "idempotent_replay": False}


def _pay_claim(ctx: TenantContext, c: Claim) -> None:
    allowed = round(c.total_charge_cents * 0.78)
    resp = round(allowed * 0.20)
    c.allowed_cents, c.patient_responsibility_cents = allowed, resp
    c.paid_cents, c.adjustment_cents = allowed - resp, c.total_charge_cents - allowed
    c.status, c.adjudicated_at = "paid", now()
    ctx.db.add(Payment(organization_id=ctx.org_id, patient_id=c.patient_id, claim_id=c.id, source="insurance", method="eft_simulated",
                       amount_cents=c.paid_cents, reference=f"ERA-{c.clearinghouse_ref}", idempotency_key=f"era-{c.id}-{c.submission_count}"))
    _event(ctx, c, "paid", allowed_cents=allowed, paid_cents=c.paid_cents, patient_responsibility_cents=resp, simulated=True)
    if resp > 0:
        _patient_invoice(ctx, c, resp, f"Patient responsibility for visit {c.service_date:%b %d, %Y} ({c.payer_name})")


def _patient_invoice(ctx: TenantContext, c: Claim, amount: int, desc: str) -> None:
    inv = Invoice(organization_id=ctx.org_id, number=_next_number(ctx, "invoice_seq", "INV"), patient_id=c.patient_id, claim_id=c.id,
                  encounter_id=c.encounter_id, description=desc, total_cents=amount, balance_cents=amount, due_date=date.today() + timedelta(days=30))
    ctx.db.add(inv)
    _notify_bill(ctx, c.patient_id, inv)


def _notify_bill(ctx: TenantContext, patient_id: uuid.UUID, inv: Invoice) -> None:
    p = ctx.db.get(Patient, patient_id)
    if p and p.portal_user_id:
        notify(ctx.db, ctx.org_id, p.portal_user_id, "bill", "You have a new statement", f"${inv.total_cents / 100:,.2f} due", "/portal/billing")


@router.post("/claims/{cid}/simulate-adjudication")
def simulate_adjudication(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    _synthetic(ctx)
    c = _claim(ctx, cid)
    if c.status != "accepted":
        raise bad_request("Only accepted claims can be adjudicated")
    h = int(hashlib.sha1(f"{c.id}{c.submission_count}".encode()).hexdigest(), 16)
    code = "CO-27" if c.member_id.endswith("0") else ("CO-16" if h % 5 == 0 and c.submission_count == 1 else "CO-50" if h % 7 == 0 and c.submission_count == 1 else None)
    if code:
        c.status, c.denial_code, c.denial_reason, c.adjudicated_at = "denied", code, DENIALS[code], now()
        c.allowed_cents, c.paid_cents = 0, 0
        _event(ctx, c, "denied", code=code, reason=DENIALS[code], simulated=True)
    else:
        _pay_claim(ctx, c)
    ctx.audit("billing.claim_adjudicated", resource_type="claim", resource_id=c.id, patient_id=c.patient_id, details={"status": c.status, "simulated": True})
    ctx.db.commit()
    return claim_out(c, ctx.db.get(Patient, c.patient_id))


@router.post("/claims/{cid}/appeal")
def appeal(cid: uuid.UUID, body: AppealIn, ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    c = _claim(ctx, cid)
    if c.status != "denied":
        raise bad_request("Only denied claims can be appealed")
    c.status, c.appeal_text, c.appeal_submitted_at = "appealed", body.text, now()
    _event(ctx, c, "appealed", simulated=True)
    ctx.audit("billing.claim_appealed", resource_type="claim", resource_id=c.id, patient_id=c.patient_id)
    ctx.db.commit()
    return claim_out(c, ctx.db.get(Patient, c.patient_id))


@router.post("/claims/{cid}/simulate-appeal-decision")
def simulate_appeal_decision(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    _synthetic(ctx)
    c = _claim(ctx, cid)
    if c.status != "appealed":
        raise bad_request("Claim is not under appeal")
    if c.denial_code == "CO-27":
        c.status = "closed"
        c.patient_responsibility_cents = c.total_charge_cents  # full balance transferred to the patient
        _event(ctx, c, "appeal_upheld", note="Coverage terminated; balance transferred to patient", simulated=True)
        _patient_invoice(ctx, c, c.total_charge_cents, f"Visit {c.service_date:%b %d, %Y} — insurance coverage inactive")
    else:
        _event(ctx, c, "appeal_overturned", simulated=True)
        _pay_claim(ctx, c)
    ctx.db.commit()
    return claim_out(c, ctx.db.get(Patient, c.patient_id))


@router.post("/claims/{cid}/void")
def void_claim(cid: uuid.UUID, body: VoidIn, ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    c = _claim(ctx, cid)
    if c.status not in ("draft", "ready", "rejected", "denied"):
        raise bad_request(f"A {c.status} claim can't be voided")
    c.status = "void"
    for ch in c.charges:
        ch.status, ch.claim_id = "pending", None  # charges return to the capture queue
    _event(ctx, c, "voided", reason=body.reason)
    ctx.audit("billing.claim_voided", resource_type="claim", resource_id=c.id, patient_id=c.patient_id)
    ctx.db.commit()
    return claim_out(c, ctx.db.get(Patient, c.patient_id))


# ---------- invoices & payments ----------

def _apply_payment(ctx: TenantContext, inv: Invoice, amount: int, method: str, reference: str | None, key: str, source="patient") -> dict:
    prior = ctx.db.scalar(select(Payment).where(Payment.organization_id == ctx.org_id, Payment.idempotency_key == key))
    if prior:
        if prior.invoice_id != inv.id:
            raise HTTPException(409, "This Idempotency-Key was already used for a different payment")
        return {"payment": payment_out(prior), "invoice": invoice_out(inv), "idempotent_replay": True}
    if inv.status != "open":
        raise bad_request(f"Invoice is {inv.status}")
    if amount > inv.balance_cents:
        raise bad_request(f"Payment exceeds the balance (${inv.balance_cents / 100:,.2f})")
    pm = Payment(organization_id=ctx.org_id, patient_id=inv.patient_id, invoice_id=inv.id, claim_id=inv.claim_id, source=source, method=method,
                 amount_cents=amount, reference=reference or (f"SIM-CARD-{uuid.uuid4().hex[:8].upper()}" if method == "card_simulated" else None),
                 idempotency_key=key, created_by_id=ctx.user.id)
    ctx.db.add(pm)
    inv.balance_cents -= amount
    if inv.balance_cents == 0:
        inv.status = "paid"
    ctx.audit("billing.payment_recorded", resource_type="invoice", resource_id=inv.id, patient_id=inv.patient_id,
              details={"amount_cents": amount, "method": method})
    try:
        ctx.db.commit()
    except IntegrityError:
        ctx.db.rollback()
        prior = ctx.db.scalar(select(Payment).where(Payment.organization_id == ctx.org_id, Payment.idempotency_key == key))
        return {"payment": payment_out(prior), "invoice": invoice_out(ctx.db.get(Invoice, inv.id)), "idempotent_replay": True}
    return {"payment": payment_out(pm), "invoice": invoice_out(inv), "idempotent_replay": False}


@router.get("/invoices")
def list_invoices(status: str | None = "open", ctx: TenantContext = Depends(require(P.BILLING_READ))):
    q = select(Invoice).where(Invoice.organization_id == ctx.org_id)
    if status:
        q = q.where(Invoice.status == status)
    rows = ctx.db.scalars(q.order_by(Invoice.issued_at.desc()).limit(200)).all()
    pats = {p.id: p for p in ctx.db.scalars(select(Patient).where(Patient.id.in_({r.patient_id for r in rows}))).all()}
    return [invoice_out(r, pats.get(r.patient_id)) for r in rows]


@router.post("/invoices/{iid}/payments", status_code=201)
def record_payment(iid: uuid.UUID, body: PaymentIn, idempotency_key: str | None = Header(default=None),
                   ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    key = _require_key(idempotency_key)
    inv = ctx.db.get(Invoice, iid)
    if not inv or inv.organization_id != ctx.org_id:
        raise not_found("Invoice")
    get_patient(ctx, inv.patient_id)
    return _apply_payment(ctx, inv, body.amount_cents, body.method, body.reference, key)


@router.get("/patients/{patient_id}/billing")
def patient_billing(patient_id: uuid.UUID, ctx: TenantContext = Depends(require(P.BILLING_READ))):
    p = get_patient(ctx, patient_id)
    claims = ctx.db.scalars(select(Claim).where(Claim.patient_id == p.id).order_by(Claim.created_at.desc())).all()
    invs = ctx.db.scalars(select(Invoice).where(Invoice.patient_id == p.id).order_by(Invoice.issued_at.desc())).all()
    pays = ctx.db.scalars(select(Payment).where(Payment.patient_id == p.id).order_by(Payment.created_at.desc())).all()
    return {"balance_cents": sum(i.balance_cents for i in invs if i.status == "open"), "claims": [claim_out(c) for c in claims],
            "invoices": [invoice_out(i) for i in invs], "payments": [payment_out(x) for x in pays]}


# ---------- portal ----------

@router.get("/portal/bills")
def portal_bills(pp=Depends(portal_patient)):
    ctx, p = pp
    invs = ctx.db.scalars(select(Invoice).where(Invoice.patient_id == p.id, Invoice.status != "void").order_by(Invoice.issued_at.desc())).all()
    pays = ctx.db.scalars(select(Payment).where(Payment.patient_id == p.id, Payment.source == "patient").order_by(Payment.created_at.desc())).all()
    return {"balance_cents": sum(i.balance_cents for i in invs if i.status == "open"), "invoices": [invoice_out(i) for i in invs],
            "payments": [payment_out(x) for x in pays], "processor": "simulated"}


@router.post("/portal/bills/{iid}/pay", status_code=201)
def portal_pay(iid: uuid.UUID, body: PortalPayIn, idempotency_key: str | None = Header(default=None), pp=Depends(portal_patient)):
    ctx, p = pp
    key = _require_key(idempotency_key)
    inv = ctx.db.get(Invoice, iid)
    if not inv or inv.patient_id != p.id:
        raise not_found("Bill")
    return _apply_payment(ctx, inv, body.amount_cents, "card_simulated", None, key)


# ---------- reporting ----------

def _bucket(days: int) -> str:
    return "0-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"


@router.get("/billing/summary")
def billing_summary(ctx: TenantContext = Depends(require(P.BILLING_READ))):
    org = ctx.org_id
    month_start = datetime.combine(date.today().replace(day=1), datetime.min.time()).astimezone()
    charges_mtd = ctx.db.scalar(select(func.coalesce(func.sum(Charge.amount_cents), 0)).where(Charge.organization_id == org, Charge.status != "void",
                                                                                              Charge.created_at >= month_start))
    pay_rows = ctx.db.execute(select(Payment.source, func.sum(Payment.amount_cents)).where(Payment.organization_id == org, Payment.status == "succeeded",
                                                                                           Payment.created_at >= month_start).group_by(Payment.source)).all()
    open_claims = ctx.db.scalars(select(Claim).where(Claim.organization_id == org, Claim.status.in_(("accepted", "submitted", "appealed", "denied")))).all()
    open_invs = ctx.db.scalars(select(Invoice).where(Invoice.organization_id == org, Invoice.status == "open")).all()
    aging = {b: {"insurance_cents": 0, "patient_cents": 0} for b in ("0-30", "31-60", "61-90", "90+")}
    today = date.today()
    for c in open_claims:
        aging[_bucket((today - c.service_date).days)]["insurance_cents"] += c.total_charge_cents
    for i in open_invs:
        aging[_bucket((today - i.issued_at.date()).days)]["patient_cents"] += i.balance_cents
    adjudicated = ctx.db.scalar(select(func.count()).select_from(Claim).where(Claim.organization_id == org, Claim.adjudicated_at.is_not(None)))
    denied_ever = ctx.db.scalar(select(func.count(func.distinct(ClaimEvent.claim_id))).where(ClaimEvent.organization_id == org, ClaimEvent.event == "denied"))
    code_expr = literal_column("claim_events.details->>'code'")  # one literal expression so SELECT and GROUP BY match
    top_denials = ctx.db.execute(select(code_expr, func.count()).where(ClaimEvent.organization_id == org, ClaimEvent.event == "denied")
                                 .group_by(code_expr).order_by(func.count().desc()).limit(5)).all()
    by_status = dict(ctx.db.execute(select(Claim.status, func.count()).where(Claim.organization_id == org).group_by(Claim.status)).all())
    six = ctx.db.execute(select(func.date_trunc("month", Payment.created_at).label("m"), Payment.source, func.sum(Payment.amount_cents))
                         .where(Payment.organization_id == org, Payment.created_at >= now() - timedelta(days=185)).group_by("m", Payment.source).order_by("m")).all()
    return {
        "charges_mtd_cents": int(charges_mtd), "payments_mtd": {s: int(v) for s, v in pay_rows},
        "ar_insurance_cents": sum(c.total_charge_cents for c in open_claims), "ar_patient_cents": sum(i.balance_cents for i in open_invs),
        "aging": aging, "denial_rate": round(denied_ever / adjudicated, 3) if adjudicated else None,
        "top_denials": [{"code": c, "reason": DENIALS.get(c, c), "count": n} for c, n in top_denials],
        "claims_by_status": by_status,
        "collections_by_month": [{"month": m.date().isoformat(), "source": s, "cents": int(v)} for m, s, v in six],
        "simulated": True,
    }
