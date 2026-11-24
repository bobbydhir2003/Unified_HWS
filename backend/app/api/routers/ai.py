import hmac
import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.ai.assistant import build_sources, get_assistant, refusal
from app.ai.config import active_provider, effective
from app.ai.provider import AIError
from app.api.deps import TenantContext, require
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import (
    AIJob,
    AutomationRun,
    AutomationWorkflow,
    Membership,
    Organization,
    Patient,
    Task,
    VoiceCall,
)
from app.services import receptionist
from app.services.automation import ACTIONS, TEMPLATES, execute
from app.services.patients import get_patient

router = APIRouter(tags=["ai"])


# ======================= Chart assistant =======================

class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    history: list[dict] = Field(default_factory=list, max_length=12)


@router.post("/patients/{patient_id}/assistant")
def ask_chart(patient_id: uuid.UUID, body: AskIn, ctx: TenantContext = Depends(require(P.AI_USE, P.CLINICAL_READ))):
    p = get_patient(ctx, patient_id, P.CLINICAL_READ)  # restricted charts, tenant and role checks apply first
    job = AIJob(organization_id=ctx.org_id, kind="chart_qa", provider=active_provider(), subject_type="patient", subject_id=p.id,
                patient_id=p.id, status="running", created_by_id=ctx.user.id)
    ctx.db.add(job)
    refused_text = refusal(body.question)
    if refused_text:
        job.status, job.provider, job.model, job.finished_at = "succeeded", "policy", None, now()
        ctx.audit("ai.chart_assistant", resource_type="patient", resource_id=p.id, patient_id=p.id, details={"refused": True})
        ctx.db.commit()
        return {"answer": refused_text, "citations": [], "refused": True, "insufficient": False, "provider": "policy"}
    sources = build_sources(ctx.db, p)
    try:
        from app.ai.policy import contains_phi

        a = get_assistant().answer(body.question, sources, body.history, contains_phi=contains_phi(ctx.db, ctx.org_id))
    except AIError as e:
        job.status, job.error, job.finished_at = "failed", str(e), now()
        ctx.db.commit()
        raise HTTPException(502, str(e)) from None
    job.status, job.provider, job.model, job.latency_ms = "succeeded", a.provider, a.model, a.latency_ms
    job.phi_sent_externally, job.input_tokens, job.output_tokens, job.finished_at = a.phi_sent_externally, a.input_tokens, a.output_tokens, now()
    job.cost_usd = getattr(a, "cost_usd", None)
    # The question text may contain PHI; the audit records only that a query happened and how it was answered.
    ctx.audit("ai.chart_assistant", resource_type="patient", resource_id=p.id, patient_id=p.id,
              details={"provider": a.provider, "citations": len(a.citations), "sources_available": len(sources)})
    ctx.db.commit()
    return {"answer": a.answer, "refused": False, "insufficient": a.insufficient, "provider": a.provider,
            "citations": [{"id": s.id, "type": s.type, "title": s.title, "date": s.date, "snippet": s.text[:240], "link": s.link} for s in a.citations]}


# ======================= Automation studio =======================

class WorkflowPatch(BaseModel):
    is_enabled: bool | None = None
    requires_approval: bool | None = None
    config: dict | None = None


def wf_out(w: AutomationWorkflow, stats: dict | None = None) -> dict:
    t = TEMPLATES.get(w.template_key, {})
    perms = t.get("permissions", [])
    return {"id": w.id, "template_key": w.template_key, "name": w.name, "description": w.description, "trigger": w.trigger, "config": w.config,
            "requires_approval": w.requires_approval, "is_enabled": w.is_enabled,
            "permissions": [{"action": a, "label": ACTIONS[a]["label"], "sensitive": ACTIONS[a]["sensitive"]} for a in perms],
            "stats": stats or {}}


def run_out(r: AutomationRun, wf_name: str | None = None, patient_name: str | None = None) -> dict:
    return {"id": r.id, "workflow_id": r.workflow_id, "workflow": wf_name, "trigger_event": r.trigger_event, "status": r.status,
            "patient_id": r.patient_id, "patient_name": patient_name, "proposed_actions": r.proposed_actions, "log": r.log, "error": r.error,
            "created_at": r.created_at, "finished_at": r.finished_at, "decided_at": r.decided_at,
            "sensitive": any(ACTIONS.get(a["type"], {}).get("sensitive") for a in r.proposed_actions)}


@router.get("/automation/templates")
def templates(ctx: TenantContext = Depends(require(P.AUTOMATION_MANAGE))):
    return [{"key": k, "name": t["name"], "description": t["description"], "trigger": t["trigger"],
             "permissions": [{"action": a, "label": ACTIONS[a]["label"], "sensitive": ACTIONS[a]["sensitive"]} for a in t["permissions"]]}
            for k, t in TEMPLATES.items()]


@router.get("/automation/workflows")
def workflows(ctx: TenantContext = Depends(require(P.AUTOMATION_MANAGE))):
    rows = ctx.db.scalars(select(AutomationWorkflow).where(AutomationWorkflow.organization_id == ctx.org_id).order_by(AutomationWorkflow.name)).all()
    stats = {}
    for wid, status, n in ctx.db.execute(select(AutomationRun.workflow_id, AutomationRun.status, func.count()).where(
            AutomationRun.organization_id == ctx.org_id, AutomationRun.created_at >= now() - timedelta(days=30)).group_by(AutomationRun.workflow_id, AutomationRun.status)).all():
        stats.setdefault(wid, {})[status] = n
    return [wf_out(w, stats.get(w.id)) for w in rows]


@router.post("/automation/workflows", status_code=201)
def install(template_key: str, ctx: TenantContext = Depends(require(P.AUTOMATION_MANAGE))):
    t = TEMPLATES.get(template_key)
    if not t:
        raise not_found("Template")
    w = AutomationWorkflow(organization_id=ctx.org_id, template_key=template_key, name=t["name"], description=t["description"],
                           trigger=t["trigger"], config=dict(t["config"]), requires_approval=True, is_enabled=False, created_by_id=ctx.user.id)
    ctx.db.add(w)
    ctx.audit("automation.installed", resource_type="workflow", resource_id=None, details={"template": template_key})
    ctx.db.commit()
    return wf_out(w)


@router.patch("/automation/workflows/{wid}")
def update_workflow(wid: uuid.UUID, body: WorkflowPatch, ctx: TenantContext = Depends(require(P.AUTOMATION_MANAGE))):
    w = ctx.db.get(AutomationWorkflow, wid)
    if not w or w.organization_id != ctx.org_id:
        raise not_found("Workflow")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(w, k, v)
    ctx.audit("automation.updated", resource_type="workflow", resource_id=w.id, details=body.model_dump(exclude_unset=True))
    ctx.db.commit()
    return wf_out(w)


@router.get("/automation/runs")
def runs(status: str | None = None, limit: int = Query(100, le=300), ctx: TenantContext = Depends(require(P.MESSAGES))):
    q = select(AutomationRun, AutomationWorkflow.name, Patient.first_name + " " + Patient.last_name).join(
        AutomationWorkflow, AutomationWorkflow.id == AutomationRun.workflow_id).outerjoin(Patient, Patient.id == AutomationRun.patient_id).where(
        AutomationRun.organization_id == ctx.org_id)
    if status:
        q = q.where(AutomationRun.status.in_(status.split(",")))
    return [run_out(r, n, pn) for r, n, pn in ctx.db.execute(q.order_by(AutomationRun.created_at.desc()).limit(limit)).all()]


def _run(ctx: TenantContext, rid: uuid.UUID) -> AutomationRun:
    r = ctx.db.get(AutomationRun, rid)
    if not r or r.organization_id != ctx.org_id:
        raise not_found("Run")
    if r.patient_id:
        get_patient(ctx, r.patient_id)
    return r


@router.post("/automation/runs/{rid}/approve")
def approve(rid: uuid.UUID, ctx: TenantContext = Depends(require(P.MESSAGES))):
    r = _run(ctx, rid)
    if r.status != "pending_approval":
        raise bad_request("Run isn't awaiting approval")
    r.decided_by_id, r.decided_at = ctx.user.id, now()
    r.log = [*r.log, {"at": now().isoformat(), "msg": f"Approved by {ctx.user.full_name}"}]
    execute(ctx.db, r, actor_id=ctx.user.id)
    ctx.audit("automation.approved", resource_type="automation_run", resource_id=r.id, patient_id=r.patient_id)
    ctx.db.commit()
    return run_out(r)


@router.post("/automation/runs/{rid}/reject")
def reject(rid: uuid.UUID, ctx: TenantContext = Depends(require(P.MESSAGES))):
    r = _run(ctx, rid)
    if r.status != "pending_approval":
        raise bad_request("Run isn't awaiting approval")
    r.status, r.decided_by_id, r.decided_at, r.finished_at = "rejected", ctx.user.id, now(), now()
    r.log = [*r.log, {"at": now().isoformat(), "msg": f"Rejected by {ctx.user.full_name}"}]
    ctx.audit("automation.rejected", resource_type="automation_run", resource_id=r.id, patient_id=r.patient_id)
    ctx.db.commit()
    return run_out(r)


@router.post("/automation/runs/{rid}/retry")
def retry(rid: uuid.UUID, ctx: TenantContext = Depends(require(P.AUTOMATION_MANAGE))):
    r = _run(ctx, rid)
    if r.status != "failed" or not r.proposed_actions:
        raise bad_request("Only failed runs with actions can be retried")
    r.log = [*r.log, {"at": now().isoformat(), "msg": f"Retried by {ctx.user.full_name}"}]
    execute(ctx.db, r, actor_id=ctx.user.id)
    ctx.db.commit()
    return run_out(r)


# ======================= Tasks =======================

class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    patient_id: uuid.UUID | None = None
    assigned_role: Literal["clinic_admin", "hospital_admin", "doctor", "nurse", "receptionist", "billing", "insurance_specialist",
                           "pharmacist", "lab_tech", "radiology_tech", "radiologist", "bed_manager"] | None = None
    assigned_user_id: uuid.UUID | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


def task_out(t: Task, pname: str | None = None) -> dict:
    return {"id": t.id, "title": t.title, "description": t.description, "patient_id": t.patient_id, "patient_name": pname,
            "assigned_role": t.assigned_role, "assigned_user_id": t.assigned_user_id, "priority": t.priority, "status": t.status,
            "link": t.link, "source": t.source, "created_at": t.created_at, "completed_at": t.completed_at, "case_id": t.case_id,
            "due_at": t.due_at, "kind": t.kind, "acknowledged_at": t.acknowledged_at, "department_id": t.department_id}


@router.get("/tasks")
def list_tasks(scope: Literal["mine", "all"] = "mine", status: Literal["open", "done"] = "open", ctx: TenantContext = Depends(require(P.PATIENTS_READ))):
    q = select(Task, Patient.first_name + " " + Patient.last_name).outerjoin(Patient, Patient.id == Task.patient_id).where(
        Task.organization_id == ctx.org_id, Task.status.in_(("open", "in_progress") if status == "open" else ("done",)),
        or_(Patient.id.is_(None), Patient.is_restricted.is_(False)))
    if ctx.department_ids is not None:
        q = q.where(or_(Task.department_id.is_(None), Task.department_id.in_(ctx.department_ids)))
    if scope == "mine":
        q = q.where(or_(Task.assigned_user_id == ctx.user.id, (Task.assigned_user_id.is_(None) & Task.assigned_role.in_(ctx.roles))))
    prio = func.array_position(["urgent", "high", "normal", "low"], Task.priority)
    rows = ctx.db.execute(q.order_by(prio, Task.created_at.desc()).limit(200)).all()
    return [task_out(t, n) for t, n in rows]


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, ctx: TenantContext = Depends(require(P.PATIENTS_READ))):
    if body.patient_id:
        get_patient(ctx, body.patient_id)
    if body.assigned_user_id and not ctx.db.scalar(select(Membership.user_id).where(
            Membership.user_id == body.assigned_user_id, Membership.organization_id == ctx.org_id, Membership.is_active.is_(True))):
        raise bad_request("Unknown user")  # only people in this organization can be assigned
    t = Task(organization_id=ctx.org_id, **body.model_dump(), source="manual")
    if not t.assigned_role and not t.assigned_user_id:
        t.assigned_user_id = ctx.user.id
    ctx.db.add(t)
    ctx.db.commit()
    return task_out(t)


@router.post("/tasks/{tid}/{action}")
def task_action(tid: uuid.UUID, action: Literal["complete", "reopen", "acknowledge", "start", "claim"],
                ctx: TenantContext = Depends(require(P.PATIENTS_READ))):
    t = ctx.db.get(Task, tid)
    if not t or t.organization_id != ctx.org_id:
        raise not_found("Task")
    ctx.require_department(t.department_id)
    if action == "complete":
        t.status, t.completed_at, t.completed_by_id = "done", now(), ctx.user.id
    elif action == "reopen":
        t.status, t.completed_at, t.completed_by_id = "open", None, None
    elif action == "acknowledge":
        t.acknowledged_at, t.acknowledged_by_id = t.acknowledged_at or now(), t.acknowledged_by_id or ctx.user.id
    elif action == "start":
        t.status = "in_progress"
        t.acknowledged_at, t.acknowledged_by_id = t.acknowledged_at or now(), t.acknowledged_by_id or ctx.user.id
    elif action == "claim":
        t.assigned_user_id = ctx.user.id
    if t.case_id:
        from app.engine.cases import log_event
        from app.models import Case

        c = ctx.db.get(Case, t.case_id)
        if c:
            log_event(ctx.db, c, "task", f"Task {action}: {t.title[:150]}", actor_id=ctx.user.id, data={"task_id": str(t.id)})
    from app.services.realtime import publish

    publish(ctx.db, ctx.org_id, "tasks", task_id=t.id)
    ctx.audit(f"task.{action}", resource_type="task", resource_id=t.id, patient_id=t.patient_id)
    ctx.db.commit()
    return task_out(t)


@router.get("/tasks-count")
def tasks_count(ctx: TenantContext = Depends(require(P.PATIENTS_READ))):
    return {"open": ctx.db.scalar(select(func.count()).select_from(Task).where(
        Task.organization_id == ctx.org_id, Task.status.in_(("open", "in_progress")),
        or_(Task.assigned_user_id == ctx.user.id, (Task.assigned_user_id.is_(None) & Task.assigned_role.in_(ctx.roles)))))}


# ======================= AI receptionist =======================

class CallStart(BaseModel):
    from_number: str | None = Field(default=None, max_length=40)


class CallMsg(BaseModel):
    text: str = Field(min_length=1, max_length=500)


def call_out(c: VoiceCall, pname: str | None = None) -> dict:
    return {"id": c.id, "from_number": c.from_number, "channel": c.channel, "status": c.status, "consented": c.consented,
            "verified_patient_id": c.verified_patient_id, "patient_name": pname, "transcript": c.transcript, "intent": c.intent,
            "outcome": c.outcome, "summary": c.summary, "created_at": c.created_at, "ended_at": c.ended_at, "stage": (c.state or {}).get("stage")}


def _call(ctx: TenantContext, cid: uuid.UUID) -> VoiceCall:
    c = ctx.db.get(VoiceCall, cid)
    if not c or c.organization_id != ctx.org_id:
        raise not_found("Call")
    return c


@router.post("/receptionist/calls", status_code=201)
def start_call(body: CallStart, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    c = receptionist.start(ctx.db, ctx.db.get(Organization, ctx.org_id), body.from_number, ctx.user.id)
    ctx.audit("receptionist.call_started", resource_type="voice_call", resource_id=None, details={"channel": "sandbox"})
    ctx.db.commit()
    return call_out(c)


@router.post("/receptionist/calls/{cid}/message")
def call_message(cid: uuid.UUID, body: CallMsg, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    c = _call(ctx, cid)
    if c.status != "active":
        raise bad_request("This call has ended")
    receptionist.message(ctx.db, c, body.text)
    ctx.db.commit()
    p = ctx.db.get(Patient, c.verified_patient_id) if c.verified_patient_id else None
    return call_out(c, p.full_name if p else None)


@router.post("/receptionist/calls/{cid}/end")
def end_call(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    c = _call(ctx, cid)
    if c.status == "active":
        c.status = "abandoned" if not c.consented else "completed"
        receptionist.finish(ctx.db, c)
    ctx.db.commit()
    return call_out(c)


@router.get("/receptionist/calls")
def list_calls(ctx: TenantContext = Depends(require(P.SCHEDULE_READ))):
    rows = ctx.db.execute(select(VoiceCall, Patient.first_name + " " + Patient.last_name).outerjoin(Patient, Patient.id == VoiceCall.verified_patient_id)
                          .where(VoiceCall.organization_id == ctx.org_id).order_by(VoiceCall.created_at.desc()).limit(100)).all()
    return [call_out(c, n) for c, n in rows]


class VoiceHook(BaseModel):
    call_sid: str = Field(min_length=4, max_length=80)
    from_number: str | None = None
    speech: str | None = Field(default=None, max_length=500)


@router.post("/integrations/voice/{org_slug}/inbound")
def voice_webhook(org_slug: str, body: VoiceHook, x_voice_secret: str | None = Header(default=None), db=Depends(get_db)):
    """Telephony integration point: the provider posts each recognized utterance; we return what to say.
    Authenticated with a per-org secret. Real deployments need a BAA-covered telephony/ASR vendor."""
    org = db.scalar(select(Organization).where(Organization.slug == org_slug))
    secret = (org.settings or {}).get("voice_webhook_secret") if org else None
    if not org or not secret or not x_voice_secret or not hmac.compare_digest(secret, x_voice_secret):
        raise HTTPException(401, "Invalid voice webhook credentials")
    c = db.scalar(select(VoiceCall).where(VoiceCall.organization_id == org.id, VoiceCall.channel == "phone", VoiceCall.state["call_sid"].astext == body.call_sid))
    if c is None:
        c = receptionist.start(db, org, body.from_number, None, channel="phone")
        c.state = {**c.state, "call_sid": body.call_sid}
        db.flush()
        say = c.transcript[-1]["text"]
    elif c.status != "active":
        say, c = "This call has ended. Goodbye.", c
    else:
        say = receptionist.message(db, c, body.speech or "")
        c.state = {**c.state, "call_sid": body.call_sid}
    db.commit()
    return {"say": say, "hangup": c.status != "active", "transfer": c.status == "transferred"}


# ======================= AI monitoring =======================

@router.get("/ai/jobs")
def ai_jobs(kind: str | None = None, status: str | None = None, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    q = select(AIJob).where(AIJob.organization_id == ctx.org_id)
    if kind:
        q = q.where(AIJob.kind == kind)
    if status:
        q = q.where(AIJob.status == status)
    rows = ctx.db.scalars(q.order_by(AIJob.created_at.desc()).limit(200)).all()
    agg = ctx.db.execute(select(AIJob.kind, AIJob.status, func.count(), func.avg(AIJob.latency_ms))
                         .where(AIJob.organization_id == ctx.org_id, AIJob.created_at >= now() - timedelta(days=30)).group_by(AIJob.kind, AIJob.status)).all()
    summary: dict = {}
    for k, s, n, lat in agg:
        d = summary.setdefault(k, {"total": 0, "succeeded": 0, "failed": 0, "avg_latency_ms": None})
        d["total"] += n
        d[s] = d.get(s, 0) + n
        if s == "succeeded" and lat is not None:
            d["avg_latency_ms"] = round(float(lat))
    phi_external = ctx.db.scalar(select(func.count()).select_from(AIJob).where(AIJob.organization_id == ctx.org_id, AIJob.phi_sent_externally.is_(True)))
    return {"provider": active_provider(), "phi_allowed": settings.ai_phi_allowed, "phi_sent_externally_total": phi_external, "summary": summary,
            "jobs": [{"id": j.id, "kind": j.kind, "status": j.status, "provider": j.provider, "model": j.model, "latency_ms": j.latency_ms,
                      "input_tokens": j.input_tokens, "output_tokens": j.output_tokens, "phi_sent_externally": j.phi_sent_externally,
                      "error": j.error, "created_at": j.created_at, "subject_type": j.subject_type,
                      "cost_usd": float(j.cost_usd) if j.cost_usd is not None else None} for j in rows],
            "cost_30d_usd": float(ctx.db.scalar(select(func.coalesce(func.sum(AIJob.cost_usd), 0)).where(
                AIJob.organization_id == ctx.org_id, AIJob.created_at >= now() - timedelta(days=30))) or 0),
            "cost_tracking": bool(settings.ai_prices)}


# ======================= Provider status (no secrets ever returned) =======================

@router.get("/ai/provider")
def ai_provider_status(ctx: TenantContext = Depends(require(P.AI_USE))):
    from app.ai.policy import contains_phi, provider_label

    lab = provider_label()
    e = effective()
    return {**lab, "openai_key_configured": bool(e.api_key), "key_source": e.source, "models": {
        "text": e.text_model or None, "vision": e.vision_model or None, "transcription": e.transcription_model or None,
        "realtime": e.realtime_model or None},
        "phi_allowed": settings.ai_phi_allowed, "org_is_synthetic": not contains_phi(ctx.db, ctx.org_id),
        "cost_tracking": bool(settings.ai_prices), "live_validation": "pending" if lab["active"] == "simulated" else "see health check"}


@router.post("/ai/provider/health")
def ai_provider_health(ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    from app.ai.openai_provider import OpenAICore, available

    if effective().provider != "openai":
        return {"ok": None, "detail": f"Active provider is {effective().provider}; nothing to check."}
    if not available():
        return {"ok": False, "detail": "OPENAI_API_KEY or AI_TEXT_MODEL not configured — simulation is in use."}
    r = OpenAICore().health()
    ctx.audit("ai.provider_health", details={"ok": r.get("ok")})
    ctx.db.commit()
    return r


# ---------------------------------------------------------------------------------------------- Realtime Voice


@router.get("/ai/realtime/status")
def realtime_status(ctx: TenantContext = Depends(require(P.AI_USE))):
    from app.ai.realtime import realtime_status as status

    return status()


class RealtimeIn(BaseModel):
    purpose: Literal["receptionist_practice"] = "receptionist_practice"
    voice: Literal["marin", "cedar", "alloy", "verse"] = "marin"


@router.post("/ai/realtime/session")
def realtime_session(body: RealtimeIn, ctx: TenantContext = Depends(require(P.AI_USE))):
    """Mint a short-lived browser credential for one voice session. The permanent key is never returned."""
    from app.ai.policy import contains_phi
    from app.ai.provider import AIPolicyError
    from app.ai.realtime import mint_client_secret
    from app.ai.realtime import realtime_status as status

    ctx.require(P.SCHEDULE_WRITE)  # front-desk feature
    st = status()
    if st["mode"] != "openai":
        return {"mode": "simulated", "reason": st["reason"], "model": st["model"]}
    job = AIJob(organization_id=ctx.org_id, kind="realtime_session", provider="openai", model=st["model"], status="running",
                created_by_id=ctx.user.id)
    ctx.db.add(job)
    try:
        out = mint_client_secret(org_id=ctx.org_id, user_id=ctx.user.id, contains_phi=contains_phi(ctx.db, ctx.org_id), voice=body.voice)
        job.status = "succeeded"
    except AIPolicyError as e:
        job.status, job.error, job.finished_at = "failed", "policy", now()
        ctx.audit("ai.realtime_session", outcome="denied", details={"reason": "phi_policy"})
        ctx.db.commit()
        raise HTTPException(403, str(e)) from None
    except AIError as e:
        job.status, job.error, job.finished_at = "failed", str(e)[:300], now()
        ctx.audit("ai.realtime_session", outcome="error", details={"model": st["model"]})
        ctx.db.commit()
        raise HTTPException(502, str(e)) from None
    job.finished_at = now()
    ctx.audit("ai.realtime_session", details={"model": out["model"], "purpose": body.purpose})
    ctx.db.commit()
    return {"mode": "openai", **out}


class CallbackArgs(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    caller_first_name: str | None = Field(default=None, max_length=60)
    preferred_time: str | None = Field(default=None, max_length=60)


@router.post("/ai/realtime/tools/{name}")
def realtime_tool(name: str, args: dict, ctx: TenantContext = Depends(require(P.AI_USE))):
    """Execute one function call requested by the voice model. Only the allow-listed tools exist; every argument is
    validated here; nothing reads patient records, books appointments or changes clinical data."""
    from pydantic import ValidationError

    from app.ai import usage
    from app.ai.realtime import CALLBACKS_PER_USER_PER_DAY, TOOL_NAMES
    from app.engine.cases import add_task
    from app.models import Clinic, Department

    ctx.require(P.SCHEDULE_WRITE)
    if name not in TOOL_NAMES:
        ctx.audit("ai.realtime_tool", outcome="denied", details={"tool": name[:60]})
        ctx.db.commit()
        raise HTTPException(404, "Unknown voice tool")
    if name == "get_clinic_information":
        clinics = ctx.db.scalars(select(Clinic).where(Clinic.organization_id == ctx.org_id, Clinic.is_active.is_(True)).order_by(Clinic.name).limit(10)).all()
        depts = ctx.db.scalars(select(Department.name).where(Department.organization_id == ctx.org_id, Department.is_active.is_(True))
                               .order_by(Department.name).limit(30)).all()
        return {"facilities": [{"name": c.name, "phone": c.phone, "address": ", ".join(x for x in (c.address_line1, c.city, c.state) if x)}
                               for c in clinics], "departments": sorted(set(depts))}
    try:
        a = CallbackArgs.model_validate(args)
    except ValidationError:
        raise HTTPException(422, "Invalid callback request") from None
    if not usage.take_request(f"voice:callback:{ctx.user.id}:{usage.day_key()}", CALLBACKS_PER_USER_PER_DAY):
        raise HTTPException(429, "Callback request limit reached for today")
    who = a.caller_first_name or "Caller"
    t = add_task(ctx.db, None, org_id=ctx.org_id, title=f"Voice assistant callback: {who} — {a.topic}"[:200], role="receptionist",
                 kind="callback", source="voice_ai", priority="normal", due_minutes=240,
                 description=f"Requested during a voice-assistant session by the caller. Preferred time: {a.preferred_time or 'not stated'}. "
                             "Administrative callback only — nothing was booked or changed.")
    ctx.audit("ai.realtime_tool", resource_type="task", resource_id=t.id if t else None, details={"tool": name})
    ctx.db.commit()
    return {"ok": True, "message": "A front-desk team member will call back. Nothing has been booked."}
