import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import TenantContext, require
from app.api.routers.portal import portal_patient
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import MessageThread, Patient, ProviderProfile, SecureMessage
from app.services.notify import notify
from app.services.patients import get_patient

router = APIRouter(tags=["messages"])


class NewThread(BaseModel):
    subject: str = Field(min_length=2, max_length=200)
    category: Literal["general", "medication", "results", "appointment", "billing"] = "general"
    body: str = Field(min_length=1, max_length=5000)


class StaffNewThread(NewThread):
    patient_id: uuid.UUID


class Reply(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


def thread_out(t: MessageThread, patient: Patient | None = None, *, for_patient: bool) -> dict:
    return {
        "id": t.id, "subject": t.subject, "category": t.category, "status": t.status, "last_message_at": t.last_message_at,
        "unread": t.patient_unread if for_patient else t.staff_unread, "created_at": t.created_at,
        "patient": {"id": patient.id, "name": patient.full_name, "mrn": patient.mrn, "date_of_birth": patient.date_of_birth} if patient and not for_patient else None,
        "messages": [{"id": m.id, "body": m.body, "created_at": m.created_at, "from_patient": m.sender_is_patient,
                      "sender": m.sender.first_name if for_patient and not m.sender_is_patient else m.sender.display_name} for m in t.messages],
    }


def _pcp_user(ctx: TenantContext, p: Patient):
    if p.primary_provider_id:
        prov = ctx.db.get(ProviderProfile, p.primary_provider_id)
        return prov
    return None


# ---------- Patient side ----------

@router.get("/portal/messages")
def my_threads(pp=Depends(portal_patient)):
    ctx, p = pp
    rows = ctx.db.scalars(select(MessageThread).where(MessageThread.patient_id == p.id).order_by(MessageThread.last_message_at.desc())).all()
    return [thread_out(t, for_patient=True) for t in rows]


@router.post("/portal/messages", status_code=201)
def patient_new_thread(body: NewThread, pp=Depends(portal_patient)):
    ctx, p = pp
    prov = _pcp_user(ctx, p)
    t = MessageThread(organization_id=ctx.org_id, patient_id=p.id, subject=body.subject, category=body.category,
                      assigned_provider_id=prov.id if prov else None, staff_unread=1, last_message_at=now())
    ctx.db.add(t)
    ctx.db.flush()
    ctx.db.add(SecureMessage(organization_id=ctx.org_id, thread_id=t.id, sender_id=ctx.user.id, sender_is_patient=True, body=body.body))
    if prov:
        notify(ctx.db, ctx.org_id, prov.user_id, "patient_message", f"Message from {p.full_name}", body.subject, f"/messages?thread={t.id}")
    ctx.audit("message.sent", resource_type="message_thread", resource_id=t.id, patient_id=p.id, details={"by": "patient"})
    ctx.db.commit()
    ctx.db.refresh(t)
    return thread_out(t, for_patient=True)


def _my_thread(ctx: TenantContext, p: Patient, tid: uuid.UUID) -> MessageThread:
    t = ctx.db.get(MessageThread, tid)
    if not t or t.patient_id != p.id:
        raise not_found("Conversation")
    return t


@router.get("/portal/messages/{tid}")
def patient_read(tid: uuid.UUID, pp=Depends(portal_patient)):
    ctx, p = pp
    t = _my_thread(ctx, p, tid)
    t.patient_unread = 0
    ctx.db.commit()
    return thread_out(t, for_patient=True)


@router.post("/portal/messages/{tid}/reply")
def patient_reply(tid: uuid.UUID, body: Reply, pp=Depends(portal_patient)):
    ctx, p = pp
    t = _my_thread(ctx, p, tid)
    if t.status == "closed":
        raise bad_request("This conversation is closed. Start a new message.")
    ctx.db.add(SecureMessage(organization_id=ctx.org_id, thread_id=t.id, sender_id=ctx.user.id, sender_is_patient=True, body=body.body))
    t.staff_unread += 1
    t.last_message_at = now()
    if (prov := _pcp_user(ctx, p)):
        notify(ctx.db, ctx.org_id, prov.user_id, "patient_message", f"Reply from {p.full_name}", t.subject, f"/messages?thread={t.id}")
    ctx.audit("message.sent", resource_type="message_thread", resource_id=t.id, patient_id=p.id, details={"by": "patient"})
    ctx.db.commit()
    ctx.db.refresh(t)
    return thread_out(t, for_patient=True)


# ---------- Staff side ----------

def _staff_thread(ctx: TenantContext, tid: uuid.UUID) -> tuple[MessageThread, Patient]:
    t = ctx.db.get(MessageThread, tid)
    if not t or t.organization_id != ctx.org_id:
        raise not_found("Conversation")
    return t, get_patient(ctx, t.patient_id)


@router.get("/messages")
def inbox(status: Literal["open", "closed"] = "open", mine: bool = False, page_size: int = Query(50, le=100),
          ctx: TenantContext = Depends(require(P.MESSAGES, P.PATIENTS_READ))):
    q = select(MessageThread, Patient).join(Patient, Patient.id == MessageThread.patient_id).where(
        MessageThread.organization_id == ctx.org_id, MessageThread.status == status, Patient.is_restricted.is_(False))
    if mine and ctx.provider:
        q = q.where(MessageThread.assigned_provider_id == ctx.provider.id)
    rows = ctx.db.execute(q.order_by(MessageThread.last_message_at.desc()).limit(page_size)).all()
    unread = ctx.db.scalar(select(func.count()).select_from(MessageThread).where(
        MessageThread.organization_id == ctx.org_id, MessageThread.status == "open", MessageThread.staff_unread > 0))
    return {"unread_threads": unread, "items": [thread_out(t, p, for_patient=False) for t, p in rows]}


@router.post("/messages", status_code=201)
def staff_new_thread(body: StaffNewThread, ctx: TenantContext = Depends(require(P.MESSAGES, P.PATIENTS_READ))):
    p = get_patient(ctx, body.patient_id)
    t = MessageThread(organization_id=ctx.org_id, patient_id=p.id, subject=body.subject, category=body.category,
                      assigned_provider_id=p.primary_provider_id, patient_unread=1, last_message_at=now())
    ctx.db.add(t)
    ctx.db.flush()
    ctx.db.add(SecureMessage(organization_id=ctx.org_id, thread_id=t.id, sender_id=ctx.user.id, sender_is_patient=False, body=body.body))
    if p.portal_user_id:
        notify(ctx.db, ctx.org_id, p.portal_user_id, "message", "New message from your care team", body.subject, f"/portal/messages/{t.id}")
    ctx.audit("message.sent", resource_type="message_thread", resource_id=t.id, patient_id=p.id, details={"by": "staff"})
    ctx.db.commit()
    ctx.db.refresh(t)
    return thread_out(t, p, for_patient=False)


@router.get("/messages/{tid}")
def staff_read(tid: uuid.UUID, ctx: TenantContext = Depends(require(P.MESSAGES, P.PATIENTS_READ))):
    t, p = _staff_thread(ctx, tid)
    t.staff_unread = 0
    ctx.audit("message.viewed", resource_type="message_thread", resource_id=t.id, patient_id=p.id)
    ctx.db.commit()
    return thread_out(t, p, for_patient=False)


@router.post("/messages/{tid}/reply")
def staff_reply(tid: uuid.UUID, body: Reply, ctx: TenantContext = Depends(require(P.MESSAGES, P.PATIENTS_READ))):
    t, p = _staff_thread(ctx, tid)
    ctx.db.add(SecureMessage(organization_id=ctx.org_id, thread_id=t.id, sender_id=ctx.user.id, sender_is_patient=False, body=body.body))
    t.patient_unread += 1
    t.staff_unread = 0
    t.status = "open"
    t.last_message_at = now()
    if p.portal_user_id:
        notify(ctx.db, ctx.org_id, p.portal_user_id, "message", "New reply from your care team", t.subject, f"/portal/messages/{t.id}")
    ctx.audit("message.sent", resource_type="message_thread", resource_id=t.id, patient_id=p.id, details={"by": "staff"})
    ctx.db.commit()
    ctx.db.refresh(t)
    return thread_out(t, p, for_patient=False)


@router.post("/messages/{tid}/close")
def close_thread(tid: uuid.UUID, ctx: TenantContext = Depends(require(P.MESSAGES, P.PATIENTS_READ))):
    t, p = _staff_thread(ctx, tid)
    t.status, t.staff_unread = "closed", 0
    ctx.audit("message.closed", resource_type="message_thread", resource_id=t.id, patient_id=p.id)
    ctx.db.commit()
    return thread_out(t, p, for_patient=False)


@router.get("/patients/{patient_id}/messages")
def patient_threads(patient_id: uuid.UUID, ctx: TenantContext = Depends(require(P.MESSAGES, P.PATIENTS_READ))):
    p = get_patient(ctx, patient_id)
    rows = ctx.db.scalars(select(MessageThread).where(MessageThread.patient_id == p.id).order_by(MessageThread.last_message_at.desc())).all()
    return [thread_out(t, p, for_patient=False) for t in rows]

