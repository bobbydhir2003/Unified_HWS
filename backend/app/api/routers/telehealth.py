"""Telehealth signaling. Media flows peer-to-peer over the browser's WebRTC stack; this API only relays
offer/answer/ICE between the two authorized participants of a telehealth appointment.

Production: replace with a BAA-covered video vendor (TURN relays, recording controls, SFU) — see docs/INTEGRATIONS.md.
"""

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.api.deps import TenantContext, get_ctx
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import Appointment, Encounter, Patient, TelehealthSession, TelehealthSignal
from app.services.notify import notify

router = APIRouter(prefix="/telehealth", tags=["telehealth"])

ICE_SERVERS = [{"urls": ["stun:stun.l.google.com:19302"]}]  # STUN only (no media relayed); TURN comes with the vendor


class SignalIn(BaseModel):
    kind: Literal["hello", "offer", "answer", "ice", "hangup"]
    payload: dict = Field(default_factory=dict)


def _role(ctx: TenantContext, a: Appointment) -> Literal["patient", "provider"]:
    if ctx.is_patient_only:
        p = ctx.db.get(Patient, a.patient_id)
        if not p or p.portal_user_id != ctx.user.id:
            raise not_found("Appointment")
        return "patient"
    if not ctx.can(P.CLINICAL_READ):
        raise forbidden("Only clinical staff can join video visits")
    ctx.require_clinic(a.clinic_id)
    return "provider"


def _appt(ctx: TenantContext, appt_id: uuid.UUID) -> Appointment:
    a = ctx.db.get(Appointment, appt_id)
    if not a or a.organization_id != ctx.org_id:
        raise not_found("Appointment")
    return a


def _session(ctx: TenantContext, sid: uuid.UUID) -> tuple[TelehealthSession, str]:
    s = ctx.db.get(TelehealthSession, sid)
    if not s or s.organization_id != ctx.org_id:
        raise not_found("Video visit")
    return s, _role(ctx, _appt(ctx, s.appointment_id))


@router.post("/appointments/{appt_id}/join")
def join(appt_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    a = _appt(ctx, appt_id)
    role = _role(ctx, a)
    if a.mode != "telehealth":
        raise bad_request("This is an in-person appointment")
    if a.status in ("cancelled", "no_show", "checked_out"):
        raise bad_request(f"This appointment is {a.status.replace('_', ' ')}")
    t = now()
    if role == "patient" and not (a.start_at - timedelta(minutes=30) <= t <= a.end_at + timedelta(hours=1)):
        raise bad_request("You can join from 30 minutes before your appointment.")
    s = ctx.db.scalar(select(TelehealthSession).where(TelehealthSession.appointment_id == a.id))
    if s is None:
        s = TelehealthSession(organization_id=ctx.org_id, appointment_id=a.id)
        ctx.db.add(s)
        ctx.db.flush()
    if s.status == "ended":
        s.status, s.ended_at = "waiting", None
        ctx.db.execute(delete(TelehealthSignal).where(TelehealthSignal.session_id == s.id))
    if role == "patient":
        s.patient_joined_at = t
        if a.status in ("scheduled", "confirmed"):
            a.status, a.checked_in_at = "checked_in", t  # joining the virtual waiting room checks the patient in
            notify(ctx.db, ctx.org_id, a.provider.user_id, "patient_arrived", f"{a.patient.full_name} is in the virtual waiting room",
                   None, f"/telehealth/{a.id}")
    else:
        s.provider_joined_at = t
    if s.patient_joined_at and s.provider_joined_at:
        s.status = "active"
    ctx.audit("telehealth.joined", resource_type="appointment", resource_id=a.id, patient_id=a.patient_id, details={"role": role})
    ctx.db.commit()
    enc = ctx.db.scalar(select(Encounter.id).where(Encounter.appointment_id == a.id))
    return {"session_id": s.id, "role": role, "status": s.status, "ice_servers": ICE_SERVERS, "encounter_id": enc,
            "appointment": {"id": a.id, "start_at": a.start_at, "patient": a.patient.full_name, "provider": a.provider.user.display_name,
                            "reason": a.reason, "patient_id": a.patient_id}}


@router.post("/sessions/{sid}/signal")
def send_signal(sid: uuid.UUID, body: SignalIn, ctx: TenantContext = Depends(get_ctx)):
    s, role = _session(ctx, sid)
    if s.status == "ended" and body.kind != "hangup":
        raise bad_request("This video visit has ended")
    if len(str(body.payload)) > 20000:
        raise bad_request("Signal too large")
    ctx.db.add(TelehealthSignal(session_id=s.id, sender_role=role, kind=body.kind, payload=body.payload))
    ctx.db.commit()
    return {"ok": True}


@router.get("/sessions/{sid}/signals")
def poll_signals(sid: uuid.UUID, after: int = Query(0, ge=0), ctx: TenantContext = Depends(get_ctx)):
    s, role = _session(ctx, sid)
    rows = ctx.db.scalars(select(TelehealthSignal).where(TelehealthSignal.session_id == s.id, TelehealthSignal.id > after,
                                                         TelehealthSignal.sender_role != role).order_by(TelehealthSignal.id).limit(200)).all()
    return {"status": s.status, "signals": [{"id": r.id, "kind": r.kind, "payload": r.payload} for r in rows]}


@router.post("/sessions/{sid}/leave")
def leave(sid: uuid.UUID, end_for_all: bool = False, ctx: TenantContext = Depends(get_ctx)):
    s, role = _session(ctx, sid)
    ctx.db.add(TelehealthSignal(session_id=s.id, sender_role=role, kind="hangup", payload={}))
    if end_for_all and role == "provider":
        s.status, s.ended_at = "ended", now()
    a = _appt(ctx, s.appointment_id)
    ctx.audit("telehealth.left", resource_type="appointment", resource_id=a.id, patient_id=a.patient_id,
              details={"role": role, "ended": end_for_all})
    ctx.db.commit()
    return {"status": s.status}
