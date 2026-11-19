"""Radiology API (B8): worklist, study status (technologist), report draft + sign (radiologist), addenda,
critical-finding acknowledgment. PACS/DICOMweb is an adapter; simulated until a vendor is connected."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import TenantContext, require
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.engine.events import emit
from app.integrations.adapters import imaging_archive
from app.models import ImagingStudy, Order, Patient, User
from app.services.notify import notify
from app.services.patients import get_patient
from app.services.realtime import publish

router = APIRouter(tags=["radiology"])

MODALITY = {"71046": "XR", "73562": "XR", "72100": "XR", "74177": "CT", "70450": "CT", "72148": "MR", "76700": "US", "77067": "MG", "93306": "ECHO"}
NEXT = {"scheduled": {"arrived", "cancelled"}, "arrived": {"in_progress", "cancelled"}, "in_progress": {"completed"}}


def _study(ctx, sid) -> ImagingStudy:
    s = ctx.db.get(ImagingStudy, sid)
    if not s or s.organization_id != ctx.org_id:
        raise not_found("Study")
    get_patient(ctx, s.patient_id)
    return s


def study_out(ctx, s: ImagingStudy, names: dict | None = None) -> dict:
    names = names if names is not None else {u.id: u.display_name for u in ctx.db.scalars(select(User).where(
        User.id.in_({x for x in (s.performed_by_id, s.drafted_by_id, s.signed_by_id) if x})))}
    o = s.order
    return {"id": s.id, "accession_number": s.accession_number, "modality": s.modality, "status": s.status, "priority": o.priority,
            "order": {"id": o.id, "title": o.title, "clinical_question": (o.details or {}).get("clinical_question"), "contrast": (o.details or {}).get("contrast")},
            "patient": {"id": s.patient_id, "name": s.patient.full_name, "mrn": s.patient.mrn}, "scheduled_at": s.scheduled_at, "started_at": s.started_at,
            "completed_at": s.completed_at, "technologist": names.get(s.performed_by_id), "technologist_note": s.technologist_note,
            "findings": s.findings, "impression": s.impression, "critical_finding": s.critical_finding, "drafted_by": names.get(s.drafted_by_id),
            "signed_by": names.get(s.signed_by_id), "signed_at": s.signed_at, "addenda": s.addenda or [],
            "critical_ack_at": s.critical_ack_at, "viewer_url": imaging_archive().viewer_url(study_instance_uid=s.study_instance_uid, accession=s.accession_number),
            "pacs": imaging_archive().name, "study_instance_uid": s.study_instance_uid}


@router.get("/radiology/worklist")
def worklist(ctx: TenantContext = Depends(require(P.RADIOLOGY_WORK))):
    to_schedule = ctx.db.execute(select(Order, Patient).join(Patient, Patient.id == Order.patient_id).outerjoin(
        ImagingStudy, (ImagingStudy.order_id == Order.id) & (ImagingStudy.status != "cancelled")).where(
        Order.organization_id == ctx.org_id, Order.order_type == "imaging", Order.status.in_(("signed", "transmitted")), ImagingStudy.id.is_(None),
        Patient.is_restricted.is_(False)).order_by(Order.signed_at)).all()
    studies = ctx.db.scalars(select(ImagingStudy).where(ImagingStudy.organization_id == ctx.org_id, ImagingStudy.status.in_(
        ("scheduled", "arrived", "in_progress", "completed", "preliminary"))).order_by(ImagingStudy.created_at)).all()
    return {"to_schedule": [{"order_id": o.id, "title": o.title, "priority": o.priority, "modality": MODALITY.get(o.code or "", "XR"),
                             "clinical_question": (o.details or {}).get("clinical_question"), "signed_at": o.signed_at,
                             "patient": {"id": p.id, "name": p.full_name, "mrn": p.mrn}} for o, p in to_schedule],
            "studies": [study_out(ctx, s) for s in studies]}


class ScheduleIn(BaseModel):
    order_id: uuid.UUID
    scheduled_at: datetime | None = None


@router.post("/radiology/studies", status_code=201)
def schedule(body: ScheduleIn, ctx: TenantContext = Depends(require(P.RADIOLOGY_WORK))):
    o = ctx.db.get(Order, body.order_id)
    if not o or o.organization_id != ctx.org_id or o.order_type != "imaging" or o.status not in ("signed", "transmitted"):
        raise bad_request("Choose a signed imaging order")
    p = get_patient(ctx, o.patient_id)
    if ctx.db.scalar(select(ImagingStudy.id).where(ImagingStudy.order_id == o.id, ImagingStudy.status != "cancelled")):
        raise bad_request("A study already exists for this order")
    s = ImagingStudy(organization_id=ctx.org_id, order_id=o.id, patient_id=o.patient_id, modality=MODALITY.get(o.code or "", "XR"),
                     scheduled_at=body.scheduled_at or now())
    ctx.db.add(s)
    ctx.db.flush()
    s.study_instance_uid = imaging_archive().register_order(accession=s.accession_number, modality=s.modality, patient_mrn=p.mrn)
    o.status = "in_progress"
    ctx.audit("radiology.scheduled", resource_type="imaging_study", resource_id=s.id, patient_id=o.patient_id)
    publish(ctx.db, ctx.org_id, "radiology", study_id=s.id)
    ctx.db.commit()
    return study_out(ctx, s)


class StatusIn(BaseModel):
    to: Literal["arrived", "in_progress", "completed", "cancelled"]
    note: str | None = Field(default=None, max_length=1000)


@router.post("/radiology/studies/{sid}/status")
def set_status(sid: uuid.UUID, body: StatusIn, ctx: TenantContext = Depends(require(P.RADIOLOGY_WORK))):
    s = _study(ctx, sid)
    if body.to not in NEXT.get(s.status, set()):
        raise bad_request(f"A {s.status} study can't move to {body.to}")
    if body.to == "cancelled" and not body.note:
        raise bad_request("Give a reason for cancelling")
    s.status = body.to
    if body.to == "in_progress":
        s.started_at, s.performed_by_id = now(), ctx.user.id
    if body.to == "completed":
        s.completed_at = now()
    if body.note:
        s.technologist_note = body.note
    if body.to == "cancelled":
        s.order.status = "signed"
    ctx.audit(f"radiology.{body.to}", resource_type="imaging_study", resource_id=s.id, patient_id=s.patient_id)
    publish(ctx.db, ctx.org_id, "radiology", study_id=s.id)
    ctx.db.commit()
    return study_out(ctx, s)


class ReportIn(BaseModel):
    findings: str = Field(min_length=3, max_length=10000)
    impression: str = Field(min_length=3, max_length=4000)
    critical_finding: bool = False


@router.put("/radiology/studies/{sid}/report")
def draft_report(sid: uuid.UUID, body: ReportIn, ctx: TenantContext = Depends(require(P.RADIOLOGY_SIGN))):
    s = _study(ctx, sid)
    if s.status not in ("completed", "preliminary"):
        raise bad_request("Reports are drafted after the study is completed")
    s.findings, s.impression, s.critical_finding, s.drafted_by_id, s.status = body.findings, body.impression, body.critical_finding, ctx.user.id, "preliminary"
    ctx.audit("radiology.report_drafted", resource_type="imaging_study", resource_id=s.id, patient_id=s.patient_id)
    ctx.db.commit()
    return study_out(ctx, s)


@router.post("/radiology/studies/{sid}/sign")
def sign_report(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.RADIOLOGY_SIGN))):
    s = _study(ctx, sid)
    if s.status != "preliminary" or not s.impression:
        raise bad_request("Draft the report before signing")
    s.status, s.signed_by_id, s.signed_at = "final", ctx.user.id, now()
    o = s.order
    o.status, o.resulted_at = "resulted", now()
    o.result_text = f"FINDINGS: {s.findings}\n\nIMPRESSION: {s.impression}"
    clinician = o.signed_by_id or o.ordered_by_id
    notify(ctx.db, ctx.org_id, clinician, "critical_result" if s.critical_finding else "result",
           f"{'CRITICAL ' if s.critical_finding else ''}Imaging report: {o.title} — {s.patient.full_name}", s.impression[:200], f"/patients/{s.patient_id}/results")
    emit(ctx.db, ctx.org_id, "radiology.report_signed", {"subject_type": "imaging_study", "subject_id": s.id, "patient_id": s.patient_id,
                                                         "critical": s.critical_finding}, actor_id=ctx.user.id)
    ctx.audit("radiology.report_signed", resource_type="imaging_study", resource_id=s.id, patient_id=s.patient_id, details={"critical": s.critical_finding})
    publish(ctx.db, ctx.org_id, "radiology", study_id=s.id)
    ctx.db.commit()
    return study_out(ctx, s)


class AddendumIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)


@router.post("/radiology/studies/{sid}/addendum")
def addendum(sid: uuid.UUID, body: AddendumIn, ctx: TenantContext = Depends(require(P.RADIOLOGY_SIGN))):
    s = _study(ctx, sid)
    if s.status != "final":
        raise bad_request("Addenda are for signed reports; edit the draft instead")
    s.addenda = [*(s.addenda or []), {"text": body.text, "by": ctx.user.display_name, "at": now().isoformat()}]
    s.order.result_text = (s.order.result_text or "") + f"\n\nADDENDUM ({now():%Y-%m-%d}): {body.text}"
    notify(ctx.db, ctx.org_id, s.order.signed_by_id or s.order.ordered_by_id, "result", f"Addendum: {s.order.title}", body.text[:200], f"/patients/{s.patient_id}/results")
    ctx.audit("radiology.addendum", resource_type="imaging_study", resource_id=s.id, patient_id=s.patient_id)
    ctx.db.commit()
    return study_out(ctx, s)


class AckIn(BaseModel):
    read_back: str = Field(min_length=3, max_length=500)


@router.post("/radiology/studies/{sid}/acknowledge")
def acknowledge(sid: uuid.UUID, body: AckIn, ctx: TenantContext = Depends(require(P.CLINICAL_WRITE))):
    s = _study(ctx, sid)
    if not (s.critical_finding and s.status == "final"):
        raise bad_request("Nothing to acknowledge")
    if s.critical_ack_at:
        raise bad_request("Already acknowledged")
    if (s.order.signed_by_id or s.order.ordered_by_id) != ctx.user.id and not ctx.can(P.ORDERS_SIGN):
        raise forbidden("Only the ordering or covering clinician can acknowledge")
    s.critical_ack_at, s.critical_ack_by_id, s.critical_read_back = now(), ctx.user.id, body.read_back
    emit(ctx.db, ctx.org_id, "radiology.critical_acknowledged", {"subject_type": "imaging_study", "subject_id": s.id, "patient_id": s.patient_id},
         actor_id=ctx.user.id)
    ctx.audit("radiology.critical_acknowledged", resource_type="imaging_study", resource_id=s.id, patient_id=s.patient_id)
    ctx.db.commit()
    return study_out(ctx, s)


@router.get("/radiology/studies/{sid}")
def get_study(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    return study_out(ctx, _study(ctx, sid))
