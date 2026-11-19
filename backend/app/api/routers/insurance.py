"""Insurance Guardian API: eligibility history, coverage update requests (portal → staff confirmation), visit overrides,
and the Guardian dashboard. Eligibility responses are SIMULATED until a clearinghouse is contracted."""

import uuid
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import TenantContext, require
from app.api.routers.portal import portal_patient
from app.core.config import settings
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.engine.cases import log_event
from app.engine.events import emit
from app.models import (
    Appointment,
    Case,
    CoverageUpdateRequest,
    Document,
    EligibilityCheck,
    NotificationDelivery,
    Organization,
    Patient,
    PatientInsurance,
)
from app.models.engine import CASE_OPEN
from app.services.insurance import coverage_state, discrepancies, primary_insurance, run_check
from app.services.patients import get_patient
from app.services.realtime import publish

router = APIRouter(tags=["insurance"])


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CheckOut(ORM):
    id: uuid.UUID
    insurance_id: uuid.UUID
    date_of_service: date
    result: str
    coverage_start: date | None
    coverage_end: date | None
    plan_description: str | None
    copay_cents: int | None
    source: str
    trigger: str
    payer_trace: str | None
    message: str | None
    checked_at: datetime


class RequestOut(ORM):
    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str | None = None
    mrn: str | None = None
    case_id: uuid.UUID | None
    appointment_id: uuid.UUID | None
    reason: str
    status: str
    document_id: uuid.UUID | None
    document_status: str | None = None
    submitted: dict
    extracted: dict
    extraction_source: str | None = None
    discrepancies: list[str] = []
    submitted_at: datetime | None
    confirmed_insurance_id: uuid.UUID | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime


def _extracted(ctx_db, req: CoverageUpdateRequest) -> tuple[dict, str | None, str | None]:
    """Card fields read by document AI (draft). Pulled live so async processing shows up when it finishes."""
    if not req.document_id:
        return req.extracted or {}, None, None
    doc = ctx_db.get(Document, req.document_id)
    if not doc:
        return req.extracted or {}, None, None
    card = ((doc.ai_output or {}).get("insurance_card") or {}) if doc.ai_output else {}
    src = (doc.ai_output or {}).get("_provider") if doc.ai_output else None
    return ({k: v for k, v in card.items() if v} or req.extracted or {}), doc.status, src


def request_out(db, req: CoverageUpdateRequest) -> RequestOut:
    o = RequestOut.model_validate(req)
    p = db.get(Patient, req.patient_id)
    o.patient_name, o.mrn = (p.full_name, p.mrn) if p else (None, None)
    o.extracted, o.document_status, o.extraction_source = _extracted(db, req)
    o.discrepancies = discrepancies(req.submitted or {}, o.extracted)
    return o


# ---------- Staff: eligibility ----------

@router.get("/patients/{patient_id}/coverage")
def patient_coverage(patient_id: uuid.UUID, ctx: TenantContext = Depends(require(P.PATIENTS_READ))):
    """Coverage state for the patient's next visit (or today), with payer check history."""
    p = get_patient(ctx, patient_id)
    nxt = ctx.db.scalar(select(Appointment).where(Appointment.patient_id == p.id, Appointment.start_at > now(),
                                                  Appointment.status.in_(("scheduled", "confirmed"))).order_by(Appointment.start_at).limit(1))
    dos = nxt.start_at.date() if nxt else now().date()
    st = coverage_state(ctx.db, p.id, dos)
    checks = ctx.db.scalars(select(EligibilityCheck).where(EligibilityCheck.patient_id == p.id)
                            .order_by(EligibilityCheck.checked_at.desc()).limit(25)).all()
    cases = ctx.db.scalars(select(Case).where(Case.patient_id == p.id, Case.category == "insurance", Case.status.in_(CASE_OPEN))).all()
    reqs = ctx.db.scalars(select(CoverageUpdateRequest).where(CoverageUpdateRequest.patient_id == p.id)
                          .order_by(CoverageUpdateRequest.created_at.desc()).limit(5)).all()
    return {"date_of_service": dos, "next_visit": {"id": nxt.id, "start_at": nxt.start_at, "coverage_override": nxt.coverage_override} if nxt else None,
            "state": st.state, "reason": st.reason, "insurance_id": st.insurance.id if st.insurance else None,
            "verified_by_check": CheckOut.model_validate(st.check) if st.check and st.verified else None,
            "simulated": settings.eligibility_adapter == "simulated",
            "checks": [CheckOut.model_validate(c) for c in checks],
            "open_cases": [{"id": c.id, "number": c.number, "title": c.title, "severity": c.severity, "status": c.status} for c in cases],
            "requests": [request_out(ctx.db, r) for r in reqs]}


class CheckIn(BaseModel):
    date_of_service: date | None = None


@router.post("/patients/{patient_id}/insurances/{ins_id}/eligibility-checks", response_model=CheckOut, status_code=201)
def run_eligibility(patient_id: uuid.UUID, ins_id: uuid.UUID, body: CheckIn, ctx: TenantContext = Depends(require(P.INSURANCE_WRITE))):
    p = get_patient(ctx, patient_id)
    ins = ctx.db.get(PatientInsurance, ins_id)
    if not ins or ins.patient_id != p.id:
        raise not_found("Insurance")
    chk = run_check(ctx.db, ins, dos=body.date_of_service or now().date(), trigger="staff", actor_id=ctx.user.id)
    ctx.db.commit()
    return chk


# ---------- Staff: coverage update requests ----------

@router.get("/insurance/requests", response_model=list[RequestOut])
def list_requests(status: Literal["requested", "submitted", "confirmed", "rejected", "open", "all"] = "submitted",
                  ctx: TenantContext = Depends(require(P.INSURANCE_WRITE))):
    q = select(CoverageUpdateRequest).where(CoverageUpdateRequest.organization_id == ctx.org_id)
    if status == "open":
        q = q.where(CoverageUpdateRequest.status.in_(("requested", "submitted")))
    elif status != "all":
        q = q.where(CoverageUpdateRequest.status == status)
    rows = ctx.db.scalars(q.order_by(CoverageUpdateRequest.submitted_at.desc().nulls_last(), CoverageUpdateRequest.created_at.desc())
                          .limit(200)).all()
    return [request_out(ctx.db, r) for r in rows]


class ConfirmIn(BaseModel):
    payer_name: str = Field(min_length=2, max_length=200)
    plan_name: str | None = Field(default=None, max_length=200)
    member_id: str = Field(min_length=2, max_length=60)
    group_number: str | None = Field(default=None, max_length=60)
    subscriber_name: str | None = Field(default=None, max_length=200)
    subscriber_relation: Literal["self", "spouse", "child", "other"] = "self"
    effective_date: date | None = None
    termination_date: date | None = None
    replaces_insurance_id: uuid.UUID | None = None
    attest_reviewed_card: bool = False


def _req(ctx: TenantContext, rid: uuid.UUID) -> CoverageUpdateRequest:
    r = ctx.db.get(CoverageUpdateRequest, rid)
    if not r or r.organization_id != ctx.org_id:
        raise not_found("Request")
    get_patient(ctx, r.patient_id)
    return r


@router.post("/insurance/requests/{rid}/confirm", response_model=RequestOut)
def confirm_request(rid: uuid.UUID, body: ConfirmIn, ctx: TenantContext = Depends(require(P.INSURANCE_WRITE))):
    """Staff confirm the card details (AI extraction is only a draft) → new coverage on file → immediate re-verification."""
    r = _req(ctx, rid)
    if r.status not in ("requested", "submitted"):
        raise bad_request(f"Request is already {r.status}")
    if not body.attest_reviewed_card:
        raise bad_request("Confirm that you reviewed the card image/details against the entered fields")
    old = None
    if body.replaces_insurance_id:
        old = ctx.db.get(PatientInsurance, body.replaces_insurance_id)
        if not old or old.patient_id != r.patient_id:
            raise not_found("Insurance to replace")
    else:
        old = primary_insurance(ctx.db, r.patient_id)
    if old:
        old.is_active = False
    data = body.model_dump(exclude={"replaces_insurance_id", "attest_reviewed_card"})
    ins = PatientInsurance(organization_id=ctx.org_id, patient_id=r.patient_id, priority="primary", **data)
    ctx.db.add(ins)
    ctx.db.flush()
    r.status, r.confirmed_insurance_id, r.reviewed_by_id, r.reviewed_at = "confirmed", ins.id, ctx.user.id, now()
    if r.document_id:
        doc = ctx.db.get(Document, r.document_id)
        if doc and doc.status in ("needs_review", "processing", "failed"):
            doc.patient_id, doc.status, doc.reviewed_by_id, doc.reviewed_at = r.patient_id, "filed", ctx.user.id, now()
            doc.doc_type = "insurance_card"
    nxt = ctx.db.scalar(select(Appointment).where(Appointment.patient_id == r.patient_id, Appointment.start_at > now(),
                                                  Appointment.status.in_(("scheduled", "confirmed"))).order_by(Appointment.start_at).limit(1))
    chk = run_check(ctx.db, ins, dos=nxt.start_at.date() if nxt else now().date(), trigger="recheck", actor_id=ctx.user.id,
                    appointment_id=nxt.id if nxt else None, emit_event=False)
    if r.case_id:
        case = ctx.db.get(Case, r.case_id)
        if case:
            log_event(ctx.db, case, "coverage_confirmed", f"Staff confirmed new coverage ({body.payer_name}); payer re-check: {chk.result}",
                      actor_id=ctx.user.id, data={"insurance_id": str(ins.id), "check_id": str(chk.id)})
    ctx.audit("insurance.update_confirmed", resource_type="insurance", resource_id=ins.id, patient_id=r.patient_id,
              details={"request_id": str(r.id), "replaced": str(old.id) if old else None, "recheck": chk.result,
                       "discrepancies": discrepancies(r.submitted or {}, _extracted(ctx.db, r)[0])})
    emit(ctx.db, ctx.org_id, "insurance.coverage_changed", {"subject_type": "insurance", "subject_id": ins.id, "patient_id": r.patient_id},
         actor_id=ctx.user.id)
    ctx.db.commit()
    return request_out(ctx.db, r)


class RejectIn(BaseModel):
    note: str = Field(min_length=5, max_length=500)


@router.post("/insurance/requests/{rid}/reject", response_model=RequestOut)
def reject_request(rid: uuid.UUID, body: RejectIn, ctx: TenantContext = Depends(require(P.INSURANCE_WRITE))):
    r = _req(ctx, rid)
    if r.status != "submitted":
        raise bad_request("Only submitted requests can be sent back")
    # Send back to the patient (keeps the request open for a new upload).
    r.status, r.review_note, r.reviewed_by_id, r.reviewed_at = "requested", body.note, ctx.user.id, now()
    from app.engine.notifications import deliver

    deliver(ctx.db, ctx.org_id, channel="portal", dedupe=f"cur:{r.id}:returned:{now():%Y%m%d%H%M}", subject="We need a clearer insurance card",
            body=f"We couldn't confirm your insurance: {body.note}. Please upload it again in the portal.", category="insurance",
            link="/portal/insurance", case=ctx.db.get(Case, r.case_id) if r.case_id else None, patient_id=r.patient_id)
    ctx.audit("insurance.update_returned", resource_type="coverage_request", resource_id=r.id, patient_id=r.patient_id)
    ctx.db.commit()
    return request_out(ctx.db, r)


class OverrideIn(BaseModel):
    kind: Literal["self_pay", "financial_counseling", "charity", "other"]
    reason: str = Field(min_length=5, max_length=300)


@router.post("/appointments/{appointment_id}/coverage-override")
def coverage_override(appointment_id: uuid.UUID, body: OverrideIn, ctx: TenantContext = Depends(require(P.INSURANCE_WRITE))):
    a = ctx.db.get(Appointment, appointment_id)
    if not a or a.organization_id != ctx.org_id:
        raise not_found("Appointment")
    ctx.require_clinic(a.clinic_id)
    a.coverage_override, a.coverage_override_reason, a.coverage_override_by_id, a.coverage_override_at = body.kind, body.reason, ctx.user.id, now()
    ctx.audit("appointment.coverage_override", resource_type="appointment", resource_id=a.id, patient_id=a.patient_id,
              details={"kind": body.kind})
    emit(ctx.db, ctx.org_id, "appointment.coverage_override", {"subject_type": "appointment", "subject_id": a.id, "patient_id": a.patient_id},
         actor_id=ctx.user.id)
    ctx.db.commit()
    return {"message": "Visit cleared without verified coverage", "kind": body.kind}


# ---------- Dashboard ----------

@router.get("/insurance/guardian/summary")
def guardian_summary(days: int = 7, ctx: TenantContext = Depends(require(P.CASES_READ))):
    """Readiness of upcoming visits + Guardian workload. Every number comes from live rows."""
    org = ctx.org_id
    horizon = now() + timedelta(days=min(max(days, 1), 30))
    appts = ctx.db.scalars(select(Appointment).where(Appointment.organization_id == org, Appointment.start_at > now(),
                                                     Appointment.start_at <= horizon, Appointment.status.in_(("scheduled", "confirmed")))).all()
    states: dict[str, int] = {}
    for a in appts:
        s = "cleared_override" if a.coverage_override else coverage_state(ctx.db, a.patient_id, a.start_at.date()).state
        states[s] = states.get(s, 0) + 1
    total = len(appts)
    ready = states.get("verified_active", 0) + states.get("cleared_override", 0)
    open_cases = ctx.db.execute(select(Case.kind, Case.severity, func.count()).where(
        Case.organization_id == org, Case.category == "insurance", Case.status.in_(CASE_OPEN)).group_by(Case.kind, Case.severity)).all()
    since = now() - timedelta(days=30)
    resolved = ctx.db.execute(select(Case.resolution_code, func.count(), func.avg(func.extract("epoch", Case.resolved_at - Case.created_at)))
                              .where(Case.organization_id == org, Case.category == "insurance", Case.status == "resolved",
                                     Case.resolved_at > since).group_by(Case.resolution_code)).all()
    reminders = dict(ctx.db.execute(select(NotificationDelivery.status, func.count()).where(
        NotificationDelivery.organization_id == org, NotificationDelivery.category == "insurance",
        NotificationDelivery.created_at > now() - timedelta(days=7)).group_by(NotificationDelivery.status)).all())
    escalated = ctx.db.scalar(select(func.count()).select_from(Case).where(Case.organization_id == org, Case.category == "insurance",
                                                                          Case.status.in_(CASE_OPEN), Case.escalation_level > 0))
    checks = dict(ctx.db.execute(select(EligibilityCheck.result, func.count()).where(
        EligibilityCheck.organization_id == org, EligibilityCheck.checked_at > now() - timedelta(days=7)).group_by(EligibilityCheck.result)).all())
    pending_review = ctx.db.scalar(select(func.count()).select_from(CoverageUpdateRequest).where(
        CoverageUpdateRequest.organization_id == org, CoverageUpdateRequest.status == "submitted"))
    awaiting_patient = ctx.db.scalar(select(func.count()).select_from(CoverageUpdateRequest).where(
        CoverageUpdateRequest.organization_id == org, CoverageUpdateRequest.status == "requested"))
    return {
        "window_days": days, "visits": total, "ready": ready, "ready_pct": round(100 * ready / total, 1) if total else None,
        "states": states,
        "open_cases": [{"kind": k, "severity": s, "count": n} for k, s, n in open_cases],
        "escalated_open": escalated,
        "resolved_30d": [{"code": c or "resolved", "count": n, "avg_hours": round((sec or 0) / 3600, 1)} for c, n, sec in resolved],
        "reminders_7d": reminders, "eligibility_checks_7d": checks,
        "requests": {"awaiting_patient": awaiting_patient, "awaiting_staff_review": pending_review},
        "simulated_eligibility": settings.eligibility_adapter == "simulated",
    }


# ---------- Patient portal ----------

def _mask(member_id: str) -> str:
    return ("•" * max(len(member_id) - 4, 0)) + member_id[-4:]


@router.get("/portal/insurance")
def portal_insurance(pp=Depends(portal_patient)):
    ctx, p = pp
    ins = ctx.db.scalars(select(PatientInsurance).where(PatientInsurance.patient_id == p.id, PatientInsurance.is_active.is_(True))).all()
    reqs = ctx.db.scalars(select(CoverageUpdateRequest).where(CoverageUpdateRequest.patient_id == p.id,
                                                              CoverageUpdateRequest.status.in_(("requested", "submitted")))).all()
    org = ctx.db.get(Organization, ctx.org_id)
    return {"insurances": [{"id": i.id, "payer_name": i.payer_name, "plan_name": i.plan_name, "member_id": _mask(i.member_id),
                            "priority": i.priority, "termination_date": i.termination_date} for i in ins],
            "requests": [{"id": r.id, "reason": r.reason, "status": r.status, "review_note": r.review_note, "created_at": r.created_at}
                         for r in reqs],
            "sample_cards_available": bool((org.settings or {}).get("synthetic_data"))}


@router.post("/portal/insurance/update", status_code=201)
async def portal_update(file: UploadFile | None = File(None), request_id: uuid.UUID | None = Form(None),
                        payer_name: str | None = Form(None, max_length=200), member_id: str | None = Form(None, max_length=60),
                        group_number: str | None = Form(None, max_length=60), plan_name: str | None = Form(None, max_length=200),
                        subscriber_name: str | None = Form(None, max_length=200), use_sample_card: bool = Form(False),
                        pp=Depends(portal_patient)):
    """Patient submits a new card (photo/PDF) and/or typed details. Staff must confirm before anything changes on file."""
    ctx, p = pp
    from app.services.documents import create_document

    if request_id:
        req = ctx.db.get(CoverageUpdateRequest, request_id)
        if not req or req.patient_id != p.id or req.status not in ("requested", "submitted"):
            raise not_found("Request")
    else:
        req = ctx.db.scalar(select(CoverageUpdateRequest).where(CoverageUpdateRequest.patient_id == p.id,
                                                                CoverageUpdateRequest.status.in_(("requested", "submitted"))))
        if not req:
            req = CoverageUpdateRequest(organization_id=ctx.org_id, patient_id=p.id, reason="Patient-initiated insurance update")
            ctx.db.add(req)
            ctx.db.flush()
    data = None
    filename = "insurance-card"
    if use_sample_card:
        org = ctx.db.get(Organization, ctx.org_id)
        if not (org.settings or {}).get("synthetic_data"):
            raise forbidden("Sample cards are only available in synthetic demo organizations")
        from app.services.sample_docs import make_sample

        data, filename, _ = make_sample("insurance_card", p)
    elif file is not None:
        data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        filename = file.filename or filename
    typed = {k: v for k, v in {"payer_name": payer_name, "member_id": member_id, "group_number": group_number, "plan_name": plan_name,
                               "subscriber_name": subscriber_name}.items() if v}
    if not data and not typed.get("member_id"):
        raise bad_request("Upload a photo of your card or enter at least your member ID")
    doc_id = None
    if data:
        try:
            doc, _ = create_document(ctx.db, org_id=ctx.org_id, data=data, filename=filename, source="portal", uploaded_by_id=ctx.user.id,
                                     patient_hint_id=p.id)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        doc.patient_id = None  # filed to the chart only after staff confirmation
        doc_id = doc.id
    req.document_id = doc_id or req.document_id
    req.submitted = {**typed}
    req.status, req.submitted_at, req.review_note = "submitted", now(), None
    if req.case_id:
        case = ctx.db.get(Case, req.case_id)
        if case:
            log_event(ctx.db, case, "patient_submitted", "Patient submitted updated insurance in the portal; awaiting staff confirmation",
                      data={"request_id": str(req.id), "document_id": str(doc_id) if doc_id else None})
            if case.status in ("open", "in_progress"):
                case.status = "waiting"
    from app.engine.cases import add_task

    add_task(ctx.db, ctx.db.get(Case, req.case_id) if req.case_id else None, org_id=ctx.org_id,
             title=f"Confirm updated insurance card — {p.full_name}", role="insurance_specialist", dedupe_key=f"task:cur:{req.id}",
             priority="high", kind="insurance.confirm_card", link=f"/insurance?request={req.id}", patient_id=p.id)
    ctx.audit("portal.insurance_submitted", resource_type="coverage_request", resource_id=req.id, patient_id=p.id,
              details={"with_document": bool(doc_id), "sample": use_sample_card})
    publish(ctx.db, ctx.org_id, "insurance", patient_id=p.id)
    ctx.db.commit()
    if doc_id:
        from app.tasks import process_document_task

        process_document_task.delay(str(doc_id))
    return {"message": "Thanks — our team will confirm your insurance and let you know if anything else is needed.",
            "request_id": req.id}
