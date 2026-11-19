"""Patient portal expansion (B12): pre-visit readiness, hospital stays with approved discharge instructions, outside
records upload, notification preferences. Patients only ever see clinician-approved / released content."""

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from app.api.routers.portal import portal_patient
from app.core.config import settings
from app.core.security import now
from app.models import (
    Appointment,
    Clinic,
    CoverageUpdateRequest,
    DischargePlan,
    Document,
    InpatientStay,
    IntakeSubmission,
    NotificationPreference,
)
from app.services.insurance import coverage_state

router = APIRouter(tags=["portal"])
CATEGORIES = {"appointments": "Appointment reminders", "insurance": "Insurance updates", "discharge": "Discharge & hospital stays",
              "billing": "Bills & payments", "results": "Test results", "general": "Other messages"}


@router.get("/portal/readiness")
def readiness(pp=Depends(portal_patient)):
    """What's left before each upcoming visit. Insurance status comes from payer-verified eligibility, not stored dates."""
    ctx, p = pp
    appts = ctx.db.scalars(select(Appointment).where(Appointment.patient_id == p.id, Appointment.start_at > now(),
                                                     Appointment.start_at < now() + timedelta(days=30),
                                                     Appointment.status.in_(("scheduled", "confirmed"))).order_by(Appointment.start_at)).all()
    open_req = ctx.db.scalar(select(CoverageUpdateRequest).where(CoverageUpdateRequest.patient_id == p.id,
                                                                 CoverageUpdateRequest.status.in_(("requested", "submitted"))))
    out = []
    for a in appts:
        st = coverage_state(ctx.db, p.id, a.start_at.date())
        intake = ctx.db.scalar(select(IntakeSubmission.id).where(IntakeSubmission.appointment_id == a.id))
        if a.coverage_override:
            ins_item = {"key": "insurance", "label": "Insurance", "done": True, "detail": "Cleared by your care team"}
        elif st.verified:
            ins_item = {"key": "insurance", "label": "Insurance verified", "done": True, "detail": "Confirmed with your insurance company"}
        elif open_req and open_req.status == "submitted":
            ins_item = {"key": "insurance", "label": "Insurance", "done": False, "detail": "We're reviewing the card you sent", "pending_staff": True}
        elif st.state in ("verified_inactive", "no_coverage"):
            ins_item = {"key": "insurance", "label": "Update your insurance", "done": False, "detail": "We couldn't confirm active coverage", "link": "/portal/insurance"}
        else:
            ins_item = {"key": "insurance", "label": "Insurance", "done": False, "detail": "Your care team is checking with your insurance", "pending_staff": True}
        items = [ins_item, {"key": "intake", "label": "Pre-visit questionnaire", "done": bool(intake),
                            "link": None if intake else f"/portal/appointments/{a.id}/intake"}]
        if a.mode == "telehealth":
            items.append({"key": "device", "label": "Camera and microphone ready", "done": False, "detail": "Test your device before the visit", "optional": True})
        required = [i for i in items if not i.get("optional")]
        out.append({"appointment_id": a.id, "start_at": a.start_at, "clinic": a.clinic.name, "mode": a.mode,
                    "provider": a.provider.user.display_name if a.provider else None, "items": items,
                    "ready": all(i["done"] or i.get("pending_staff") for i in required)})
    return out


@router.get("/portal/stays")
def stays(pp=Depends(portal_patient)):
    ctx, p = pp
    rows = ctx.db.scalars(select(InpatientStay).where(InpatientStay.patient_id == p.id, InpatientStay.status.in_(("admitted", "discharge_ordered", "discharged")),
                                                      (InpatientStay.discharged_at.is_(None)) | (InpatientStay.discharged_at > now() - timedelta(days=365)))
                          .order_by(InpatientStay.requested_at.desc())).all()
    out = []
    for s in rows:
        plan = ctx.db.scalar(select(DischargePlan).where(DischargePlan.stay_id == s.id))
        approved = plan is not None and plan.instructions_approved_at is not None
        fu = next((i.evidence for i in (plan.items if plan else []) if i.key == "follow_up" and i.status == "done"), None)
        fac = ctx.db.get(Clinic, s.facility_id)
        out.append({"id": s.id, "status": s.status, "facility": fac.name if fac else None, "reason": s.reason,
                    "admitted_at": s.admitted_at, "discharged_at": s.discharged_at, "disposition": s.discharge_disposition,
                    "instructions": plan.instructions_text if approved else None, "instructions_approved_at": plan.instructions_approved_at if approved else None,
                    "follow_up_at": (fu or {}).get("at")})
    return out


@router.get("/portal/documents")
def my_documents(pp=Depends(portal_patient)):
    ctx, p = pp
    docs = ctx.db.scalars(select(Document).where(Document.uploaded_by_id == ctx.user.id, Document.source == "portal")
                          .order_by(Document.created_at.desc()).limit(50)).all()
    label = {"processing": "Received", "needs_review": "With your care team", "filed": "Added to your record", "rejected": "Not accepted", "failed": "Received"}
    return [{"id": d.id, "filename": d.filename, "status": label.get(d.status, d.status), "uploaded_at": d.created_at, "note": d.reject_reason} for d in docs]


@router.post("/portal/documents", status_code=201)
async def upload_document(file: UploadFile = File(...), pp=Depends(portal_patient)):
    """Outside records (e.g. results from another hospital). Staff confirm identity and file them; nothing is auto-filed."""
    ctx, p = pp
    from app.services.documents import create_document

    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        doc, _ = create_document(ctx.db, org_id=ctx.org_id, data=data, filename=file.filename or "document", source="portal",
                                 uploaded_by_id=ctx.user.id, patient_hint_id=p.id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    from app.engine.cases import add_task

    add_task(ctx.db, None, org_id=ctx.org_id, title=f"Review outside records uploaded by {p.full_name}", role="nurse",
             dedupe_key=f"task:portaldoc:{doc.id}", kind="documents.portal_upload", link=f"/documents/{doc.id}", patient_id=p.id)
    ctx.audit("portal.document_uploaded", resource_type="document", resource_id=doc.id, patient_id=p.id)
    ctx.db.commit()
    from app.tasks import process_document_task

    process_document_task.delay(str(doc.id))
    return {"id": doc.id, "message": "Thanks — your care team will review it."}


@router.get("/portal/notification-preferences")
def get_prefs(pp=Depends(portal_patient)):
    ctx, p = pp
    rows = {r.category: r for r in ctx.db.scalars(select(NotificationPreference).where(NotificationPreference.patient_id == p.id))}
    return [{"category": k, "label": v, "email": rows[k].email if k in rows else True, "sms": rows[k].sms if k in rows else False,
             "portal": rows[k].portal if k in rows else True} for k, v in CATEGORIES.items()]


class PrefIn(BaseModel):
    category: Literal["appointments", "insurance", "discharge", "billing", "results", "general"]
    email: bool = True
    sms: bool = False
    portal: bool = True


@router.put("/portal/notification-preferences")
def set_pref(body: PrefIn, pp=Depends(portal_patient)):
    ctx, p = pp
    row = ctx.db.scalar(select(NotificationPreference).where(NotificationPreference.patient_id == p.id, NotificationPreference.category == body.category))
    if not row:
        row = NotificationPreference(organization_id=ctx.org_id, patient_id=p.id, category=body.category)
        ctx.db.add(row)
    row.email, row.sms, row.portal, row.in_app = body.email, body.sms, body.portal, True
    ctx.audit("portal.notification_preferences", patient_id=p.id, details=body.model_dump())
    ctx.db.commit()
    return get_prefs(pp=pp)
