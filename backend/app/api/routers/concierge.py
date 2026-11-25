"""HMS Voice Concierge API (paths keep the original /receptionist prefix).

Staff (schedule:write) run test calls — typed, or browser voice over OpenAI Realtime — against the same server-side engine the
telephony webhook uses. Call lists carry no transcripts; a call's transcript is returned only to front-desk staff and access is
audited. Calls are scoped to the viewer's facilities. The telephony webhook is disabled unless VOICE_TELEPHONY_ENABLED is set."""

import hmac
import uuid
from datetime import datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import TenantContext, get_db, require
from app.core.config import settings
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import AIJob, Clinic, Organization, Patient, Task, VoiceCall
from app.services import concierge as C

router = APIRouter(tags=["voice-concierge"])


class CallStart(BaseModel):
    from_number: str | None = Field(default=None, max_length=40)
    clinic_id: uuid.UUID | None = None
    channel: Literal["text", "browser_voice"] = "text"


class CallMsg(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class StaffAction(BaseModel):
    action: Literal["callback", "handoff"]
    note: str = Field(min_length=2, max_length=200)
    category: Literal["scheduling", "billing", "records", "clinical_question", "other"] = "scheduling"


class Utterance(BaseModel):
    speaker: Literal["caller", "assistant"]
    text: str = Field(min_length=1, max_length=1000)


class VoiceIn(BaseModel):
    voice: Literal["marin", "cedar", "alloy", "verse"] = "marin"


def _scoped(ctx: TenantContext, q):
    q = q.where(VoiceCall.organization_id == ctx.org_id)
    if ctx.clinic_ids is not None:
        q = q.where(VoiceCall.clinic_id.in_(ctx.clinic_ids))
    return q


def _get(ctx: TenantContext, cid: uuid.UUID, *, lock: bool = False) -> VoiceCall:
    q = _scoped(ctx, select(VoiceCall).where(VoiceCall.id == cid))
    c = ctx.db.scalar(q.with_for_update() if lock else q)  # row lock: concurrent requests can't run the same action twice
    if not c:
        raise not_found("Call")
    return c


def _active(c: VoiceCall) -> None:
    if c.status != "active":
        raise bad_request("This call has ended")


def _detail(ctx: TenantContext, c: VoiceCall) -> dict:
    return C.call_detail(ctx.db, c, show_test_code=c.mode == "test" and C.synthetic_org(ctx.db, ctx.org_id))


def _pick_clinic(ctx: TenantContext, clinic_id: uuid.UUID | None) -> Clinic:
    if clinic_id:
        c = ctx.db.get(Clinic, clinic_id)
        if not c or c.organization_id != ctx.org_id or not c.is_active:
            raise not_found("Facility")
        ctx.require_clinic(c.id)
        return c
    q = select(Clinic).where(Clinic.organization_id == ctx.org_id, Clinic.is_active.is_(True))
    if ctx.clinic_ids is not None:
        q = q.where(Clinic.id.in_(ctx.clinic_ids))
    c = ctx.db.scalar(q.order_by(Clinic.name))
    if not c:
        raise bad_request("No facility is available for calls")
    return c


@router.get("/receptionist/overview")
def overview(ctx: TenantContext = Depends(require(P.SCHEDULE_READ))):
    from app.ai.config import effective
    from app.ai.openai_provider import available
    from app.ai.policy import contains_phi
    from app.ai.realtime import realtime_status

    tzname = ctx.db.scalar(select(Clinic.timezone).where(Clinic.organization_id == ctx.org_id).limit(1)) or "America/New_York"
    tz = ZoneInfo(tzname)
    day0 = datetime.combine(now().astimezone(tz).date(), time(0), tz)
    calls = _scoped(ctx, select(func.count()).select_from(VoiceCall))
    tasks = select(func.count()).select_from(Task).where(Task.organization_id == ctx.org_id, Task.source == "voice_ai",
                                                         Task.status.in_(("open", "in_progress")))
    if ctx.clinic_ids is not None:
        tasks = tasks.where(Task.facility_id.in_(ctx.clinic_ids))
    synthetic = C.synthetic_org(ctx.db, ctx.org_id)
    phi = contains_phi(ctx.db, ctx.org_id)
    live_text = available(C.AGENT) and (not phi or settings.ai_phi_allowed)
    eff = effective()
    return {
        "stats": {"active": ctx.db.scalar(calls.where(VoiceCall.status == "active", VoiceCall.created_at >= now() - timedelta(hours=2))) or 0,
                  "pending_callbacks": ctx.db.scalar(tasks.where(Task.kind == "callback")) or 0,
                  "completed_today": ctx.db.scalar(calls.where(VoiceCall.created_at >= day0, VoiceCall.outcome_code.in_(
                      ("booked", "rescheduled", "cancelled", "callback", "handoff", "info")))) or 0,
                  "escalations_open": ctx.db.scalar(tasks.where(Task.kind.in_(("handoff", "emergency_call")))) or 0},
        "conversation": {"mode": "openai" if live_text else "built_in", "model": eff.model_for(C.AGENT) if live_text else None,
                         "reason": None if live_text else ("External AI isn't allowed for real patient data in this organization."
                                                           if available(C.AGENT) else "No OpenAI text model is configured; the built-in engine runs the conversation.")},
        "voice": realtime_status(),
        "telephony": {"enabled": settings.voice_telephony_enabled,
                      "note": None if settings.voice_telephony_enabled else "No telephony provider is connected: no public phone answering and no live call transfer."},
        "synthetic": synthetic,
        "test_writes": synthetic,  # test calls change appointments only in synthetic organizations
        "timezone": tzname,
    }


@router.get("/receptionist/calls")
def list_calls(ctx: TenantContext = Depends(require(P.SCHEDULE_READ))):
    rows = ctx.db.execute(_scoped(ctx, select(VoiceCall, Patient.first_name + " " + Patient.last_name)
                                  .outerjoin(Patient, Patient.id == VoiceCall.verified_patient_id))
                          .order_by(VoiceCall.created_at.desc()).limit(50)).all()
    return [C.call_summary(c, n) for c, n in rows]  # no transcripts in the list


@router.post("/receptionist/calls", status_code=201)
def start_call(body: CallStart, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    from app.ai import usage

    if not usage.take_request(f"voice:calls:{ctx.user.id}:{usage.day_key()}", settings.voice_concierge_calls_per_user_day):
        raise HTTPException(429, {"code": "call_limit", "message": "Daily test-call limit reached. It resets at midnight UTC."})
    clinic = _pick_clinic(ctx, body.clinic_id)
    c = C.start_call(ctx.db, ctx.db.get(Organization, ctx.org_id), clinic=clinic, user_id=ctx.user.id, from_number=body.from_number,
                     channel=body.channel, mode="test")
    ctx.audit("concierge.call_started", resource_type="voice_call", resource_id=c.id, details={"channel": body.channel, "mode": "test"})
    ctx.db.commit()
    return _detail(ctx, c)


@router.get("/receptionist/calls/{cid}")
def get_call(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    c = _get(ctx, cid)
    if c.started_by_id != ctx.user.id:
        ctx.audit("concierge.transcript_viewed", resource_type="voice_call", resource_id=c.id, patient_id=c.verified_patient_id)
        ctx.db.commit()
    return _detail(ctx, c)


@router.post("/receptionist/calls/{cid}/message")
def call_message(cid: uuid.UUID, body: CallMsg, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    c = _get(ctx, cid, lock=True)
    _active(c)
    C.handle_turn(ctx.db, c, body.text, actor_id=ctx.user.id)
    ctx.db.commit()
    return _detail(ctx, c)


@router.post("/receptionist/calls/{cid}/end")
def end_call(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    c = _get(ctx, cid, lock=True)
    if c.status == "active":
        C.finish(ctx.db, c, "ended_by_staff")
        ctx.audit("concierge.call_ended", resource_type="voice_call", resource_id=c.id, details={"outcome": c.outcome_code})
    ctx.db.commit()
    return _detail(ctx, c)


@router.post("/receptionist/calls/{cid}/staff-action")
def staff_action(cid: uuid.UUID, body: StaffAction, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    """Front-desk staff create the callback or handoff themselves (same idempotent tools, recorded as a staff action)."""
    c = _get(ctx, cid, lock=True)
    name = "create_callback_request" if body.action == "callback" else "request_staff_handoff"
    args = {"reason": body.note, "category": body.category} if body.action == "callback" else {"reason": body.note}
    was_active = c.status == "active"
    if not was_active:
        c.status = "active"  # allow a follow-up task on an ended call, then restore its status
    r = C.run_tool(ctx.db, c, name, args, actor_id=ctx.user.id, source="staff")
    if not was_active:
        c.status = "completed"
    if not r.get("ok"):
        raise bad_request(r.get("error") or "Couldn't create the task")
    ctx.db.commit()
    return _detail(ctx, c)


# ---------------------------------------------------------------------------------------------- browser voice (Realtime)
@router.post("/receptionist/calls/{cid}/voice/session")
def voice_session(cid: uuid.UUID, body: VoiceIn, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    """Short-lived Realtime credential bound to this call's concierge instructions and tool set. Permanent key never returned."""
    from app.ai.policy import contains_phi
    from app.ai.provider import AIError, AIPolicyError
    from app.ai.realtime import mint_client_secret, realtime_status

    ctx.require(P.AI_USE)
    c = _get(ctx, cid)
    _active(c)
    if c.channel != "browser_voice":
        raise bad_request("Start a voice call to use browser voice")
    st = realtime_status()
    if st["mode"] != "openai":
        return {"mode": "simulated", "reason": st["reason"], "model": st["model"]}
    job = AIJob(organization_id=ctx.org_id, kind="realtime_session", provider="openai", model=st["model"], status="running",
                subject_type="voice_call", subject_id=c.id, created_by_id=ctx.user.id)
    ctx.db.add(job)
    try:
        out = mint_client_secret(org_id=ctx.org_id, user_id=ctx.user.id, contains_phi=contains_phi(ctx.db, ctx.org_id), voice=body.voice,
                                 instructions=C.system_prompt(ctx.db, c) + "\nStart by greeting the caller exactly as the disclosure in the transcript.",
                                 tools=C.TOOL_SPECS)
        job.status = "succeeded"
    except AIPolicyError as e:
        job.status, job.error, job.finished_at = "failed", "policy", now()
        ctx.audit("ai.realtime_session", outcome="denied", details={"reason": "phi_policy", "call_id": str(c.id)})
        ctx.db.commit()
        raise HTTPException(403, str(e)) from None
    except AIError as e:
        job.status, job.error, job.finished_at = "failed", str(e)[:300], now()
        ctx.audit("ai.realtime_session", outcome="error", details={"model": st["model"], "call_id": str(c.id)})
        ctx.db.commit()
        raise HTTPException(502, str(e)) from None
    job.finished_at = now()
    C._event(c, "voice_session", "info", "Browser voice session connected", f"Model {out['model']} (not a telephone call)")
    ctx.audit("ai.realtime_session", details={"model": out["model"], "purpose": "voice_concierge", "call_id": str(c.id)})
    ctx.db.commit()
    return {"mode": "openai", **out, "greeting": c.transcript[0]["text"] if c.transcript else C.greeting(ctx.db, c)}


@router.post("/receptionist/calls/{cid}/voice/tools/{name}")
def voice_tool(cid: uuid.UUID, name: str, args: dict, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    """The Realtime model may only request a tool; the browser relays it here and the server validates and executes it."""
    c = _get(ctx, cid, lock=True)
    _active(c)
    if c.channel != "browser_voice":
        raise bad_request("Not a voice call")
    r = C.run_tool(ctx.db, c, name, args if isinstance(args, dict) else {}, actor_id=ctx.user.id, source="voice")
    if C._st(c).get("end_requested"):
        C.finish(ctx.db, c, C._st(c)["end_requested"])
    ctx.db.commit()
    return r


@router.post("/receptionist/calls/{cid}/voice/utterance")
def voice_utterance(cid: uuid.UUID, body: Utterance, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    c = _get(ctx, cid, lock=True)
    _active(c)
    if c.channel != "browser_voice":
        raise bad_request("Not a voice call")
    r = C.record_utterance(ctx.db, c, body.speaker, body.text, actor_id=ctx.user.id)
    ctx.db.commit()
    return r


# ---------------------------------------------------------------------------------------------- telephony webhook
class VoiceHook(BaseModel):
    call_sid: str = Field(min_length=4, max_length=80)
    from_number: str | None = None
    speech: str | None = Field(default=None, max_length=500)


@router.post("/integrations/voice/{org_slug}/inbound")
def voice_webhook(org_slug: str, body: VoiceHook, x_voice_secret: str | None = Header(default=None), db=Depends(get_db)):
    """Telephony integration point: the provider posts each recognized utterance; we return what to say. Disabled unless
    VOICE_TELEPHONY_ENABLED; authenticated with a per-organization secret. `transfer` is always false — no live transfer exists."""
    if not settings.voice_telephony_enabled:
        raise HTTPException(404, "Telephony is not enabled")
    org = db.scalar(select(Organization).where(Organization.slug == org_slug))
    secret = (org.settings or {}).get("voice_webhook_secret") if org else None
    if not org or not secret or not x_voice_secret or not hmac.compare_digest(secret, x_voice_secret):
        raise HTTPException(401, "Invalid voice webhook credentials")
    c = db.scalar(select(VoiceCall).where(VoiceCall.organization_id == org.id, VoiceCall.channel == "phone",
                                          VoiceCall.state["call_sid"].astext == body.call_sid).with_for_update())
    if c is None:
        clinic = db.scalar(select(Clinic).where(Clinic.organization_id == org.id, Clinic.is_active.is_(True)).order_by(Clinic.name))
        c = C.start_call(db, org, clinic=clinic, user_id=None, from_number=body.from_number, channel="phone", mode="live")
        c.state = {**c.state, "call_sid": body.call_sid}
        db.flush()
        say = c.transcript[-1]["text"]
    elif c.status != "active":
        say = "This call has ended. Goodbye."
    else:
        say = C.handle_turn(db, c, body.speech or "", actor_id=None)
    db.commit()
    return {"say": say, "hangup": c.status != "active", "transfer": False}
