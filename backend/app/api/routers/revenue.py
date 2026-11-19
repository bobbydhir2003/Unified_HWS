"""Revenue expansion API (B10): prior authorizations, claim review findings, coding worklist, denial analytics."""

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import TenantContext, require
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import Charge, Claim, ClaimFinding, Encounter, Order, Patient, PriorAuthorization
from app.services import revenue as R
from app.services.patients import get_patient

router = APIRouter(tags=["revenue"])


def pa_out(pa: PriorAuthorization) -> dict:
    return {"id": pa.id, "number": pa.number, "status": pa.status, "patient": {"id": pa.patient_id, "name": pa.patient.full_name, "mrn": pa.patient.mrn},
            "order_id": pa.order_id, "service_code": pa.service_code, "service_description": pa.service_description, "payer_name": pa.payer_name,
            "checklist": pa.checklist, "clinical_summary": pa.clinical_summary, "auth_number": pa.auth_number, "valid_from": pa.valid_from,
            "valid_to": pa.valid_to, "submitted_at": pa.submitted_at, "decided_at": pa.decided_at, "denial_reason": pa.denial_reason,
            "source": pa.source, "channel": pa.channel, "created_at": pa.created_at}


def _pa(ctx, pid) -> PriorAuthorization:
    pa = ctx.db.get(PriorAuthorization, pid)
    if not pa or pa.organization_id != ctx.org_id:
        raise not_found("Authorization")
    get_patient(ctx, pa.patient_id)
    return pa


@router.get("/prior-auths")
def list_pas(status: str | None = None, ctx: TenantContext = Depends(require(P.INSURANCE_WRITE))):
    q = select(PriorAuthorization).join(Patient).where(PriorAuthorization.organization_id == ctx.org_id, Patient.is_restricted.is_(False))
    if status == "open":
        q = q.where(PriorAuthorization.status.in_(("draft", "submitted", "pended")))
    elif status:
        q = q.where(PriorAuthorization.status == status)
    return [pa_out(p) for p in ctx.db.scalars(q.order_by(PriorAuthorization.created_at.desc()).limit(200))]


class PAIn(BaseModel):
    order_id: uuid.UUID


@router.post("/prior-auths", status_code=201)
def create_pa(body: PAIn, ctx: TenantContext = Depends(require(P.INSURANCE_WRITE))):
    o = ctx.db.get(Order, body.order_id)
    if not o or o.organization_id != ctx.org_id:
        raise not_found("Order")
    get_patient(ctx, o.patient_id)
    pa = R.ensure_pa_for_order(ctx.db, o, source="manual", actor_id=ctx.user.id)
    ctx.audit("prior_auth.created", resource_type="prior_auth", resource_id=pa.id, patient_id=pa.patient_id)
    ctx.db.commit()
    return pa_out(pa)


class ChecklistIn(BaseModel):
    key: str
    done: bool
    note: str | None = Field(default=None, max_length=300)


@router.post("/prior-auths/{pid}/checklist")
def update_checklist(pid: uuid.UUID, body: ChecklistIn, ctx: TenantContext = Depends(require(P.INSURANCE_WRITE))):
    pa = _pa(ctx, pid)
    if pa.status not in ("draft", "pended"):
        raise bad_request("Checklist is locked after submission")
    if not any(c["key"] == body.key for c in pa.checklist):
        raise not_found("Checklist item")
    pa.checklist = [{**c, "done": body.done, "note": body.note} if c["key"] == body.key else c for c in pa.checklist]
    ctx.db.commit()
    return pa_out(pa)


@router.post("/prior-auths/{pid}/submit")
def submit(pid: uuid.UUID, ctx: TenantContext = Depends(require(P.INSURANCE_WRITE))):
    """Submit to the payer. SIMULATED (no X12 278 / payer portal connection): deterministic decision for workflow testing."""
    pa = _pa(ctx, pid)
    try:
        R.submit_pa(ctx.db, pa, actor_id=ctx.user.id)
    except R.RevenueError as e:
        ctx.db.rollback()
        raise bad_request(str(e)) from None
    from app.engine.events import emit

    emit(ctx.db, ctx.org_id, "prior_auth.decided", {"subject_type": "prior_auth", "subject_id": pa.id, "patient_id": pa.patient_id, "status": pa.status},
         actor_id=ctx.user.id)
    ctx.db.commit()
    return pa_out(pa)


@router.post("/prior-auths/{pid}/cancel")
def cancel(pid: uuid.UUID, ctx: TenantContext = Depends(require(P.INSURANCE_WRITE))):
    pa = _pa(ctx, pid)
    if pa.status in ("approved", "cancelled"):
        raise bad_request(f"Authorization is {pa.status}")
    pa.status = "cancelled"
    ctx.audit("prior_auth.cancelled", resource_type="prior_auth", resource_id=pa.id, patient_id=pa.patient_id)
    ctx.db.commit()
    return pa_out(pa)


# ---------- Claim review ----------

def finding_out(f: ClaimFinding) -> dict:
    return {"id": f.id, "source": f.source, "code": f.code, "severity": f.severity, "message": f.message, "evidence": f.evidence, "status": f.status,
            "resolution_note": f.resolution_note, "created_at": f.created_at, "model": f.model}


@router.post("/claims/{cid}/review")
def review(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    c = ctx.db.get(Claim, cid)
    if not c or c.organization_id != ctx.org_id:
        raise not_found("Claim")
    rows = R.review_claim(ctx.db, c, actor_id=ctx.user.id)
    ctx.db.commit()
    from app.ai.config import active_provider

    return {"findings": [finding_out(f) for f in rows], "ai_provider": active_provider(),
            "note": "Findings are advisory. They never change the claim, its codes, or submit it."}


@router.get("/claims/{cid}/findings")
def findings(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.BILLING_READ))):
    c = ctx.db.get(Claim, cid)
    if not c or c.organization_id != ctx.org_id:
        raise not_found("Claim")
    return [finding_out(f) for f in ctx.db.scalars(select(ClaimFinding).where(ClaimFinding.claim_id == c.id).order_by(ClaimFinding.created_at.desc()))]


class FindingIn(BaseModel):
    status: Literal["resolved", "dismissed"]
    note: str = Field(min_length=3, max_length=300)


@router.post("/claim-findings/{fid}")
def decide_finding(fid: uuid.UUID, body: FindingIn, ctx: TenantContext = Depends(require(P.BILLING_WRITE))):
    f = ctx.db.get(ClaimFinding, fid)
    if not f or f.organization_id != ctx.org_id:
        raise not_found("Finding")
    if f.status != "open":
        raise bad_request("Already closed")
    f.status, f.resolution_note, f.resolved_by_id = body.status, body.note, ctx.user.id
    ctx.audit(f"claim.finding_{body.status}", resource_type="claim", resource_id=f.claim_id, details={"code": f.code, "severity": f.severity})
    ctx.db.commit()
    return finding_out(f)


# ---------- Coding worklist & analytics ----------

@router.get("/coding/queue")
def coding_queue(ctx: TenantContext = Depends(require(P.BILLING_READ))):
    """Completed encounters (incl. inpatient/ED) not yet billed, with what is missing for a clean claim."""
    billed = select(Claim.encounter_id).where(Claim.status != "void")
    encs = ctx.db.scalars(select(Encounter).join(Patient, Patient.id == Encounter.patient_id).where(
        Encounter.organization_id == ctx.org_id, Encounter.status == "completed", Encounter.completed_at >= now() - timedelta(days=60),
        Encounter.id.not_in(billed), Patient.is_restricted.is_(False)).order_by(Encounter.completed_at.desc()).limit(200)).all()
    out = []
    for e in encs:
        charges = ctx.db.scalars(select(Charge).where(Charge.encounter_id == e.id, Charge.status == "pending")).all()
        missing = []
        if not e.diagnoses:
            missing.append("diagnoses")
        if not charges:
            missing.append("charges")
        elif any(not ch.diagnosis_codes for ch in charges):
            missing.append("diagnosis pointers")
        out.append({"encounter_id": e.id, "type": e.encounter_type, "patient": {"id": e.patient_id, "name": e.patient.full_name, "mrn": e.patient.mrn},
                    "service_date": e.started_at, "completed_at": e.completed_at, "charges_cents": sum(ch.amount_cents for ch in charges),
                    "charge_codes": [ch.code for ch in charges], "missing": missing})
    return out


@router.get("/revenue/denials")
def denial_analytics(days: int = 180, ctx: TenantContext = Depends(require(P.BILLING_READ))):
    since = now() - timedelta(days=min(days, 730))
    rows = ctx.db.execute(select(Claim.denial_code, Claim.denial_reason, Claim.payer_name, func.count(), func.sum(Claim.total_charge_cents))
                          .where(Claim.organization_id == ctx.org_id, Claim.denial_code.is_not(None), Claim.created_at >= since)
                          .group_by(Claim.denial_code, Claim.denial_reason, Claim.payer_name).order_by(func.count().desc())).all()
    total = ctx.db.scalar(select(func.count()).select_from(Claim).where(Claim.organization_id == ctx.org_id, Claim.submitted_at >= since)) or 0
    denied = sum(r[3] for r in rows)
    prevention = {"CO-27": "Insurance Guardian visit readiness", "CO-197": "Prior authorization monitor", "CO-16": "Claim review findings"}
    return {"window_days": days, "submitted": total, "denied": denied, "denial_rate_pct": round(100 * denied / total, 1) if total else None,
            "by_reason": [{"code": c, "reason": r, "payer": p, "count": n, "charges_cents": int(v or 0), "prevention": prevention.get(c)} for c, r, p, n, v in rows]}
