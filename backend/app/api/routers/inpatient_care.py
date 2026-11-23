"""Discharge coordination (B5) and nursing workspace (B4) API."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import TenantContext, require
from app.api.routers.adt import _stay, stay_out
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.core.security import now
from app.engine import approvals as AP
from app.models import (
    ApprovalRequest,
    CareTeamMember,
    HandoffNote,
    InpatientStay,
    Patient,
    Task,
    User,
    VitalSigns,
)
from app.services import discharge as D

router = APIRouter(tags=["inpatient"])


# ======================= Discharge coordination =======================

@router.get("/adt/stays/{sid}/discharge")
def discharge_status(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.ADT_READ))):
    s = _stay(ctx, sid)
    r = D.readiness(ctx.db, s)
    pending = ctx.db.scalar(select(ApprovalRequest).where(ApprovalRequest.kind == "discharge.instructions", ApprovalRequest.status == "pending",
                                                          ApprovalRequest.payload["stay_id"].astext == str(s.id)).limit(1))
    ctx.db.commit()
    return {"stay": stay_out(ctx, s), "readiness": r,
            "pending_instructions": {"id": pending.id, "text": pending.payload.get("text"), "source": pending.payload.get("source"),
                                     "created_at": pending.created_at} if pending else None}


@router.post("/adt/stays/{sid}/discharge/plan")
def start_plan(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.CLINICAL_WRITE))):
    """Start discharge planning early (before the order) — creates the checklist and owner tasks."""
    s = _stay(ctx, sid)
    if s.status not in ("admitted", "discharge_ordered"):
        raise bad_request("Discharge planning applies to admitted patients")
    plan = D.ensure_plan(ctx.db, s, actor_id=ctx.user.id)
    D.sync(ctx.db, s, plan)
    created = D.fan_out(ctx.db, s, plan)
    ctx.db.commit()
    return {"tasks_created": created, "readiness": D.readiness(ctx.db, s)}


class ItemIn(BaseModel):
    status: Literal["pending", "in_progress", "done", "not_applicable"]
    note: str | None = Field(default=None, max_length=500)


@router.post("/adt/stays/{sid}/discharge/items/{key}")
def update_item(sid: uuid.UUID, key: str, body: ItemIn, ctx: TenantContext = Depends(require(P.CASES_WORK))):
    s = _stay(ctx, sid)
    try:
        D.complete_item(ctx.db, s, key, actor_id=ctx.user.id, status=body.status, note=body.note, actor_roles=ctx.roles)
    except D.DischargeError as e:
        ctx.db.rollback()
        raise bad_request(str(e)) from None
    ctx.db.commit()
    return D.readiness(ctx.db, s)


@AP.executor("discharge.instructions")
def _approve_instructions(db, req: ApprovalRequest, actor_id) -> dict:
    s = db.get(InpatientStay, uuid.UUID(req.payload["stay_id"]))
    plan = D.ensure_plan(db, s, actor_id=actor_id)
    plan.instructions_text = req.payload["text"]
    plan.instructions_source = "ai_draft_approved" if req.payload.get("source") == "ai" else "template_approved"
    plan.instructions_approved_by_id, plan.instructions_approved_at = actor_id, now()
    D.sync(db, s, plan)
    from app.engine.notifications import deliver

    deliver(db, s.organization_id, channel="portal", dedupe=f"dc:{s.id}:instructions:{plan.instructions_approved_at:%Y%m%d%H%M%S}",
            subject="Your discharge instructions are ready", body="Your care team has shared your discharge instructions in the portal.",
            category="discharge", link="/portal/visits", patient_id=s.patient_id)
    return {"approved": True}


@router.post("/adt/stays/{sid}/discharge/instructions/draft")
def draft_instructions(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.CLINICAL_WRITE))):
    """Discharge Coordination agent: prepare a plain-language DRAFT for clinician approval (never sent unapproved)."""
    s = _stay(ctx, sid)
    text, source = D.draft_instructions(ctx.db, s)
    from app.ai.openai_provider import available

    if available("discharge_coordination"):
        from pydantic import BaseModel as _B

        from app.ai.openai_provider import OpenAICore
        from app.ai.policy import contains_phi
        from app.ai.provider import AIError

        class _Out(_B):
            text: str

        try:
            out, _m = OpenAICore().structured(
                system=("Rewrite hospital discharge instructions for a patient at a 6th-grade reading level. Use ONLY facts in the "
                        "provided draft; do not add medications, doses, diagnoses or advice that are not there. Keep the warning signs."),
                content=[{"type": "input_text", "text": f"<document>{text}</document>"}], schema=_Out,
                contains_phi=contains_phi(ctx.db, ctx.org_id), max_output_tokens=1500, name="discharge_instructions")
            text, source = out.text, "ai"
        except AIError:
            pass  # keep the deterministic template draft
    for old in ctx.db.scalars(select(ApprovalRequest).where(ApprovalRequest.kind == "discharge.instructions", ApprovalRequest.status == "pending",
                                                            ApprovalRequest.payload["stay_id"].astext == str(s.id))):
        old.status, old.decision_note = "expired", "Superseded by a newer draft"
    req = AP.request_approval(ctx.db, ctx.org_id, kind="discharge.instructions", title=f"Approve discharge instructions — {s.patient.full_name}",
                              summary=text, payload={"stay_id": str(s.id), "text": text, "source": source}, required_permission=P.CLINICAL_SIGN,
                              patient_id=s.patient_id, facility_id=s.facility_id, requested_by_agent="Discharge Coordination agent")
    ctx.audit("discharge.instructions_drafted", resource_type="inpatient_stay", resource_id=s.id, patient_id=s.patient_id, details={"source": source})
    ctx.db.commit()
    return {"approval_id": req.id, "text": text, "source": source}


class ApproveIn(BaseModel):
    approval_id: uuid.UUID
    text: str = Field(min_length=20, max_length=8000)


@router.post("/adt/stays/{sid}/discharge/instructions/approve")
def approve_instructions(sid: uuid.UUID, body: ApproveIn, ctx: TenantContext = Depends(require(P.CLINICAL_SIGN))):
    """Clinician reviews/edits the draft and approves it (clinical:sign). Edits are kept as the approved text."""
    s = _stay(ctx, sid)
    req = ctx.db.get(ApprovalRequest, body.approval_id)
    if not req or req.organization_id != ctx.org_id or req.payload.get("stay_id") != str(s.id):
        raise not_found("Draft")
    edited = body.text.strip() != (req.payload.get("text") or "").strip()
    req.payload = {**req.payload, "text": body.text, "edited_by_clinician": edited}
    try:
        AP.decide(ctx.db, req, approve=True, actor_id=ctx.user.id, actor_permissions=ctx.permissions, note="Reviewed" + (" and edited" if edited else ""))
    except AP.ApprovalError as e:
        ctx.db.rollback()
        raise bad_request(str(e)) from None
    ctx.db.commit()
    return D.readiness(ctx.db, s)


# ======================= Nursing workspace =======================

def _latest_vitals(ctx: TenantContext, patient_ids: list[uuid.UUID]) -> dict:
    if not patient_ids:
        return {}
    sub = select(VitalSigns.patient_id, func.max(VitalSigns.measured_at).label("m")).where(VitalSigns.patient_id.in_(patient_ids)).group_by(
        VitalSigns.patient_id).subquery()
    rows = ctx.db.scalars(select(VitalSigns).join(sub, (VitalSigns.patient_id == sub.c.patient_id) & (VitalSigns.measured_at == sub.c.m))).all()
    return {v.patient_id: {"measured_at": v.measured_at, "bp": f"{v.systolic}/{v.diastolic}" if v.systolic else None, "hr": v.heart_rate,
                           "rr": v.respiratory_rate, "temp_c": float(v.temperature_c) if v.temperature_c else None, "spo2": v.spo2,
                           "pain": v.pain_score} for v in rows}


@router.get("/nursing/patients")
def nursing_patients(department_id: uuid.UUID | None = None, mine: bool = False, ctx: TenantContext = Depends(require(P.ADT_READ))):
    q = select(InpatientStay).join(Patient).where(InpatientStay.organization_id == ctx.org_id, InpatientStay.status.in_(("admitted", "discharge_ordered")),
                                                  Patient.is_restricted.is_(False))
    if ctx.facility_ids is not None:
        q = q.where(InpatientStay.facility_id.in_(ctx.facility_ids))
    if department_id:
        q = q.where(InpatientStay.department_id == department_id)
    elif ctx.department_ids is not None:
        q = q.where(InpatientStay.department_id.in_(ctx.department_ids))
    if mine:
        q = q.where(InpatientStay.id.in_(select(CareTeamMember.stay_id).where(CareTeamMember.user_id == ctx.user.id, CareTeamMember.end_at.is_(None))))
    stays = ctx.db.scalars(q).all()
    pids = [s.patient_id for s in stays]
    vit = _latest_vitals(ctx, pids)
    tasks = dict(ctx.db.execute(select(Task.patient_id, func.count()).where(Task.patient_id.in_(pids), Task.status.in_(("open", "in_progress")))
                                .group_by(Task.patient_id)).all()) if pids else {}
    last_handoff = dict(ctx.db.execute(select(HandoffNote.stay_id, func.max(HandoffNote.created_at)).where(
        HandoffNote.stay_id.in_([s.id for s in stays])).group_by(HandoffNote.stay_id)).all()) if stays else {}
    out = []
    for s in stays:
        r = D.readiness(ctx.db, s)
        out.append({**stay_out(ctx, s), "vitals": vit.get(s.patient_id), "open_tasks": tasks.get(s.patient_id, 0),
                    "vitals_overdue": (vit.get(s.patient_id) is None) or (now() - vit[s.patient_id]["measured_at"]).total_seconds() > 4 * 3600,
                    "last_handoff_at": last_handoff.get(s.id),
                    "discharge": {"ready": r["ready"], "done": r["done"], "total": r["total"], "blocking": r["blocking"]} if r else None})
    ctx.db.commit()
    return sorted(out, key=lambda x: (x["bed"] or {}).get("code") or "")


class CareTeamIn(BaseModel):
    user_id: uuid.UUID
    role: Literal["attending", "resident", "nurse", "case_manager", "pharmacist", "therapist", "other"]
    is_primary: bool = False


@router.get("/adt/stays/{sid}/care-team")
def care_team(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.ADT_READ))):
    s = _stay(ctx, sid)
    rows = ctx.db.scalars(select(CareTeamMember).where(CareTeamMember.stay_id == s.id, CareTeamMember.end_at.is_(None))).all()
    return [{"id": m.id, "user_id": m.user_id, "name": m.user.display_name, "role": m.role, "is_primary": m.is_primary, "since": m.start_at} for m in rows]


@router.post("/adt/stays/{sid}/care-team", status_code=201)
def add_care_team(sid: uuid.UUID, body: CareTeamIn, ctx: TenantContext = Depends(require(P.ADT_WRITE))):
    s = _stay(ctx, sid)
    if not ctx.db.scalar(select(User.id).where(User.id == body.user_id)):
        raise bad_request("Unknown user")
    if ctx.db.scalar(select(CareTeamMember.id).where(CareTeamMember.stay_id == s.id, CareTeamMember.user_id == body.user_id,
                                                     CareTeamMember.role == body.role, CareTeamMember.end_at.is_(None))):
        raise bad_request("Already on the care team in that role")
    ctx.db.add(CareTeamMember(organization_id=ctx.org_id, stay_id=s.id, user_id=body.user_id, role=body.role, is_primary=body.is_primary))
    ctx.audit("care_team.added", resource_type="inpatient_stay", resource_id=s.id, patient_id=s.patient_id, details={"role": body.role})
    ctx.db.commit()
    return care_team(sid, ctx=ctx)


@router.delete("/care-team/{mid}")
def remove_care_team(mid: uuid.UUID, ctx: TenantContext = Depends(require(P.ADT_WRITE))):
    m = ctx.db.get(CareTeamMember, mid)
    if not m or m.organization_id != ctx.org_id:
        raise not_found("Care team member")
    _stay(ctx, m.stay_id)
    m.end_at = now()
    ctx.db.commit()
    return {"message": "Removed from care team"}


class HandoffIn(BaseModel):
    shift: Literal["day", "evening", "night"]
    situation: str = Field(min_length=3, max_length=2000)
    background: str | None = Field(default=None, max_length=2000)
    assessment: str | None = Field(default=None, max_length=2000)
    recommendation: str | None = Field(default=None, max_length=2000)


def _handoff_out(h: HandoffNote, names: dict) -> dict:
    return {"id": h.id, "shift": h.shift, "situation": h.situation, "background": h.background, "assessment": h.assessment,
            "recommendation": h.recommendation, "author": names.get(h.author_id), "author_id": h.author_id, "created_at": h.created_at,
            "acknowledged_by": names.get(h.acknowledged_by_id), "acknowledged_at": h.acknowledged_at}


@router.get("/adt/stays/{sid}/handoffs")
def list_handoffs(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.ADT_READ))):
    s = _stay(ctx, sid)
    rows = ctx.db.scalars(select(HandoffNote).where(HandoffNote.stay_id == s.id).order_by(HandoffNote.created_at.desc()).limit(30)).all()
    ids = {x for h in rows for x in (h.author_id, h.acknowledged_by_id) if x}
    names = {u.id: u.display_name for u in ctx.db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    return [_handoff_out(h, names) for h in rows]


@router.post("/adt/stays/{sid}/handoffs", status_code=201)
def create_handoff(sid: uuid.UUID, body: HandoffIn, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    s = _stay(ctx, sid)
    ctx.db.add(HandoffNote(organization_id=ctx.org_id, stay_id=s.id, author_id=ctx.user.id, **body.model_dump()))
    ctx.audit("nursing.handoff_written", resource_type="inpatient_stay", resource_id=s.id, patient_id=s.patient_id, details={"shift": body.shift})
    ctx.db.commit()
    return list_handoffs(sid, ctx=ctx)


@router.post("/handoffs/{hid}/acknowledge")
def ack_handoff(hid: uuid.UUID, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    h = ctx.db.get(HandoffNote, hid)
    if not h or h.organization_id != ctx.org_id:
        raise not_found("Handoff")
    _stay(ctx, h.stay_id)
    if h.acknowledged_at:
        raise bad_request("Already acknowledged")
    if h.author_id == ctx.user.id:
        raise bad_request("The receiving nurse acknowledges a handoff")
    h.acknowledged_by_id, h.acknowledged_at = ctx.user.id, now()
    ctx.audit("nursing.handoff_acknowledged", resource_type="handoff", resource_id=h.id)
    ctx.db.commit()
    return {"acknowledged_at": h.acknowledged_at}

