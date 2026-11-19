"""Operations API over the automation engine: cases, worklist, monitors, approvals, notifications, engine health."""

import uuid
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select

from app.api.deps import TenantContext, require
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.core.security import now
from app.engine import approvals as A
from app.engine import cases as C
from app.engine.events import retry_dead
from app.engine.monitors import REGISTRY, get_config, run_monitor
from app.models import (
    ApprovalRequest,
    Case,
    CaseEvent,
    DomainEvent,
    EventHandling,
    MonitorConfig,
    MonitorRun,
    NotificationDelivery,
    NotificationPreference,
    Patient,
    Task,
    User,
)
from app.models.engine import CASE_CATEGORIES, CASE_OPEN, SEVERITIES

router = APIRouter(tags=["operations"])


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CaseOut(ORM):
    id: uuid.UUID
    number: int
    category: str
    kind: str
    title: str
    summary: str | None
    severity: str
    status: str
    patient_id: uuid.UUID | None
    patient_name: str | None = None
    facility_id: uuid.UUID | None
    department_id: uuid.UUID | None
    subject_type: str | None
    subject_id: str | None
    link: str | None
    assigned_role: str | None
    assigned_user_id: uuid.UUID | None
    assigned_user_name: str | None = None
    due_at: datetime | None
    overdue: bool = False
    escalation_level: int
    snoozed_until: datetime | None
    snooze_reason: str | None
    resolved_at: datetime | None
    resolution_code: str | None
    resolution: str | None
    source: str
    rule_key: str | None
    rule_version: int | None
    evidence: dict
    created_at: datetime
    last_detected_at: datetime


class CaseEventOut(ORM):
    id: uuid.UUID
    at: datetime
    actor_id: uuid.UUID | None
    actor_name: str | None = None
    actor_kind: str
    kind: str
    message: str
    data: dict


class DeliveryOut(ORM):
    id: uuid.UUID
    case_id: uuid.UUID | None
    channel: str
    category: str
    recipient_user_id: uuid.UUID | None
    recipient_patient_id: uuid.UUID | None
    subject: str
    status: str
    status_reason: str | None
    created_at: datetime
    sent_at: datetime | None


class ApprovalOut(ORM):
    id: uuid.UUID
    kind: str
    title: str
    summary: str | None
    case_id: uuid.UUID | None
    patient_id: uuid.UUID | None
    requested_by_user_id: uuid.UUID | None
    requested_by_agent: str | None
    required_permission: str
    payload: dict
    status: str
    decided_by_id: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    executed_at: datetime | None
    result: dict
    error: str | None
    created_at: datetime
    can_decide: bool = False


class CaseDetail(BaseModel):
    case: CaseOut
    events: list[CaseEventOut]
    tasks: list[dict]
    deliveries: list[DeliveryOut]
    approvals: list[ApprovalOut]


def _names(ctx: TenantContext, ids: set) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.display_name for u in ctx.db.scalars(select(User).where(User.id.in_(ids)))}


def _visible(ctx: TenantContext, q):
    q = q.where(Case.organization_id == ctx.org_id)
    if ctx.facility_ids is not None:
        q = q.where(or_(Case.facility_id.is_(None), Case.facility_id.in_(ctx.facility_ids)))
    if ctx.department_ids is not None:
        q = q.where(or_(Case.department_id.is_(None), Case.department_id.in_(ctx.department_ids)))
    # Restricted (VIP) charts never leak through operational queues.
    return q.outerjoin(Patient, Patient.id == Case.patient_id).where(or_(Patient.id.is_(None), Patient.is_restricted.is_(False)))


def case_out(ctx: TenantContext, cases: list[Case]) -> list[CaseOut]:
    pids = {c.patient_id for c in cases if c.patient_id}
    pnames = {p.id: p.full_name for p in ctx.db.scalars(select(Patient).where(Patient.id.in_(pids)))} if pids else {}
    unames = _names(ctx, {c.assigned_user_id for c in cases})
    out = []
    for c in cases:
        o = CaseOut.model_validate(c)
        o.patient_name = pnames.get(c.patient_id)
        o.assigned_user_name = unames.get(c.assigned_user_id)
        o.overdue = bool(c.due_at and c.status in ("open", "in_progress", "waiting", "escalated") and c.due_at < now())
        out.append(o)
    return out


def _case(ctx: TenantContext, cid: uuid.UUID) -> Case:
    c = ctx.db.scalars(_visible(ctx, select(Case).where(Case.id == cid))).first()
    if not c:
        raise not_found("Case")
    return c


SEV_ORDER = func.array_position(list(reversed(SEVERITIES)), Case.severity)


@router.get("/cases", response_model=list[CaseOut])
def list_cases(status: Literal["open", "closed", "all"] = "open", category: str | None = None, severity: str | None = None,
               facility_id: uuid.UUID | None = None, department_id: uuid.UUID | None = None, mine: bool = False,
               patient_id: uuid.UUID | None = None, q: str | None = None, overdue: bool = False, limit: int = 200,
               ctx: TenantContext = Depends(require(P.CASES_READ))):
    stmt = _visible(ctx, select(Case))
    if status == "open":
        stmt = stmt.where(Case.status.in_(CASE_OPEN))
    elif status == "closed":
        stmt = stmt.where(Case.status.in_(("resolved", "cancelled")))
    if category:
        stmt = stmt.where(Case.category == category)
    if severity:
        stmt = stmt.where(Case.severity == severity)
    if facility_id:
        stmt = stmt.where(Case.facility_id == facility_id)
    if department_id:
        stmt = stmt.where(Case.department_id == department_id)
    if patient_id:
        stmt = stmt.where(Case.patient_id == patient_id)
    if mine:
        stmt = stmt.where(or_(Case.assigned_user_id == ctx.user.id, (Case.assigned_user_id.is_(None) & Case.assigned_role.in_(ctx.roles))))
    if overdue:
        stmt = stmt.where(Case.due_at < now(), Case.status.in_(("open", "in_progress", "waiting", "escalated")))
    if q:
        like = f"%{q.lower()}%"
        conds = [func.lower(Case.title).like(like), func.lower(Case.kind).like(like)]
        if q.lstrip("#").isdigit():
            conds.append(Case.number == int(q.lstrip("#")))
        stmt = stmt.where(or_(*conds))
    order = (SEV_ORDER, Case.due_at.asc().nulls_last()) if status == "open" else (Case.updated_at.desc(),)
    return case_out(ctx, list(ctx.db.scalars(stmt.order_by(*order).limit(min(limit, 500))).all()))


@router.get("/cases/summary")
def cases_summary(ctx: TenantContext = Depends(require(P.CASES_READ))):
    base = _visible(ctx, select(Case.category, Case.severity, func.count()).where(Case.status.in_(CASE_OPEN)))
    rows = ctx.db.execute(base.group_by(Case.category, Case.severity)).all()
    overdue = ctx.db.scalar(_visible(ctx, select(func.count()).select_from(Case).where(
        Case.status.in_(("open", "in_progress", "waiting", "escalated")), Case.due_at < now())))
    by_cat: dict[str, dict[str, int]] = {}
    for cat, sev, n in rows:
        by_cat.setdefault(cat, {})[sev] = n
    return {"by_category": by_cat, "total_open": sum(n for *_, n in rows), "overdue": overdue}


@router.get("/cases/{cid}", response_model=CaseDetail)
def get_case(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.CASES_READ))):
    c = _case(ctx, cid)
    events = ctx.db.scalars(select(CaseEvent).where(CaseEvent.case_id == c.id).order_by(CaseEvent.at, CaseEvent.id)).all()
    names = _names(ctx, {e.actor_id for e in events})
    ev_out = []
    for e in events:
        o = CaseEventOut.model_validate(e)
        o.actor_name = names.get(e.actor_id)
        ev_out.append(o)
    from app.api.routers.ai import task_out

    tasks = [task_out(t) for t in ctx.db.scalars(select(Task).where(Task.case_id == c.id).order_by(Task.created_at))]
    deliveries = ctx.db.scalars(select(NotificationDelivery).where(NotificationDelivery.case_id == c.id)
                                .order_by(NotificationDelivery.created_at)).all()
    approvals = [_approval_out(ctx, a) for a in ctx.db.scalars(select(ApprovalRequest).where(ApprovalRequest.case_id == c.id))]
    ctx.audit("case.viewed", resource_type="case", resource_id=c.id, patient_id=c.patient_id)
    ctx.db.commit()
    return CaseDetail(case=case_out(ctx, [c])[0], events=ev_out, tasks=tasks,
                      deliveries=[DeliveryOut.model_validate(d) for d in deliveries], approvals=approvals)


class CaseIn(BaseModel):
    title: str = Field(min_length=3, max_length=250)
    summary: str | None = Field(default=None, max_length=4000)
    category: Literal[CASE_CATEGORIES] = "operations"  # type: ignore[valid-type]
    severity: Literal[SEVERITIES] = "medium"  # type: ignore[valid-type]
    patient_id: uuid.UUID | None = None
    facility_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    assigned_role: str | None = Field(default=None, max_length=30)
    assigned_user_id: uuid.UUID | None = None


@router.post("/cases", response_model=CaseOut, status_code=201)
def create_case(body: CaseIn, ctx: TenantContext = Depends(require(P.CASES_WORK))):
    if body.patient_id:
        from app.services.patients import get_patient

        get_patient(ctx, body.patient_id)
    ctx.require_facility(body.facility_id)
    f = C.Finding(dedupe_key=f"manual:{uuid.uuid4()}", title=body.title, summary=body.summary, category=body.category,
                  kind=f"manual.{body.category}", severity=body.severity, patient_id=body.patient_id, facility_id=body.facility_id,
                  department_id=body.department_id, assign_role=body.assigned_role,
                  assign_user_id=body.assigned_user_id or (None if body.assigned_role else ctx.user.id))
    c, _ = C.open_case(ctx.db, ctx.org_id, f, source="manual", actor_id=ctx.user.id)
    ctx.db.commit()
    return case_out(ctx, [c])[0]


class AssignIn(BaseModel):
    role: str | None = Field(default=None, max_length=30)
    user_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=300)


class TransitionIn(BaseModel):
    to: Literal["open", "in_progress", "waiting", "resolved", "cancelled"]
    note: str | None = Field(default=None, max_length=2000)
    resolution_code: str | None = Field(default=None, max_length=40)


class SnoozeIn(BaseModel):
    until: datetime | None = None
    hours: int | None = Field(default=None, ge=1, le=720)
    reason: str = Field(min_length=5, max_length=300)


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


def _act(ctx: TenantContext, fn):
    try:
        fn()
    except C.CaseError as e:
        ctx.db.rollback()
        raise bad_request(str(e)) from None


@router.post("/cases/{cid}/assign", response_model=CaseOut)
def assign_case(cid: uuid.UUID, body: AssignIn, ctx: TenantContext = Depends(require(P.CASES_WORK))):
    c = _case(ctx, cid)
    if not body.role and not body.user_id:
        body.user_id = ctx.user.id  # "assign to me"
    if body.user_id and not ctx.db.scalar(select(User.id).where(User.id == body.user_id)):
        raise bad_request("Unknown user")
    C.assign(ctx.db, c, role=body.role, user_id=body.user_id, actor_id=ctx.user.id, note=body.note)
    ctx.audit("case.assigned", resource_type="case", resource_id=c.id, patient_id=c.patient_id,
              details={"role": body.role, "user_id": str(body.user_id) if body.user_id else None})
    ctx.db.commit()
    return case_out(ctx, [c])[0]


@router.post("/cases/{cid}/transition", response_model=CaseOut)
def transition_case(cid: uuid.UUID, body: TransitionIn, ctx: TenantContext = Depends(require(P.CASES_WORK))):
    c = _case(ctx, cid)
    if body.to in ("resolved", "cancelled") and not (body.note and body.note.strip()):
        raise bad_request("Explain how the case was resolved (note required)")
    _act(ctx, lambda: C.transition(ctx.db, c, body.to, actor_id=ctx.user.id, note=body.note,
                                   resolution_code=body.resolution_code or ("staff_resolved" if body.to == "resolved" else None)))
    ctx.db.commit()
    return case_out(ctx, [c])[0]


@router.post("/cases/{cid}/snooze", response_model=CaseOut)
def snooze_case(cid: uuid.UUID, body: SnoozeIn, ctx: TenantContext = Depends(require(P.CASES_WORK))):
    c = _case(ctx, cid)
    until = body.until or (now() + timedelta(hours=body.hours or 4))
    _act(ctx, lambda: C.snooze(ctx.db, c, until, body.reason, actor_id=ctx.user.id))
    ctx.db.commit()
    return case_out(ctx, [c])[0]


@router.post("/cases/{cid}/comment", response_model=CaseOut)
def comment_case(cid: uuid.UUID, body: CommentIn, ctx: TenantContext = Depends(require(P.CASES_WORK))):
    c = _case(ctx, cid)
    C.comment(ctx.db, c, body.text, actor_id=ctx.user.id)
    ctx.db.commit()
    return case_out(ctx, [c])[0]


# ---------- Worklist ----------

@router.get("/worklist")
def worklist(ctx: TenantContext = Depends(require(P.CASES_READ))):
    """Everything waiting on me or my roles: open cases and tasks, ordered by urgency."""
    cases = list_cases(status="open", mine=True, limit=200, ctx=ctx)
    from app.api.routers.ai import list_tasks

    tasks = list_tasks(scope="mine", status="open", ctx=ctx)
    approvals = [a for a in list_approvals(status="pending", ctx=ctx) if a.can_decide]
    return {"cases": cases, "tasks": tasks, "approvals": approvals,
            "counts": {"cases": len(cases), "tasks": len(tasks), "approvals": len(approvals),
                       "overdue": sum(1 for c in cases if c.overdue)}}


# ---------- Approvals ----------

def _approval_out(ctx: TenantContext, a: ApprovalRequest) -> ApprovalOut:
    o = ApprovalOut.model_validate(a)
    o.can_decide = a.status == "pending" and ctx.can(a.required_permission) and a.requested_by_user_id != ctx.user.id
    return o


@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(status: Literal["pending", "decided", "all"] = "pending", ctx: TenantContext = Depends(require(P.CASES_READ))):
    q = select(ApprovalRequest).where(ApprovalRequest.organization_id == ctx.org_id)
    if status == "pending":
        q = q.where(ApprovalRequest.status == "pending")
    elif status == "decided":
        q = q.where(ApprovalRequest.status != "pending")
    if ctx.facility_ids is not None:
        q = q.where(or_(ApprovalRequest.facility_id.is_(None), ApprovalRequest.facility_id.in_(ctx.facility_ids)))
    rows = ctx.db.scalars(q.order_by(ApprovalRequest.created_at.desc()).limit(200)).all()
    return [_approval_out(ctx, a) for a in rows if a.status != "pending" or ctx.can(a.required_permission) or status != "pending"]


class DecideIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


@router.post("/approvals/{aid}/decide", response_model=ApprovalOut)
def decide_approval(aid: uuid.UUID, body: DecideIn, ctx: TenantContext = Depends(require(P.CASES_WORK))):
    a = ctx.db.get(ApprovalRequest, aid)
    if not a or a.organization_id != ctx.org_id:
        raise not_found("Approval request")
    ctx.require_facility(a.facility_id)
    try:
        A.decide(ctx.db, a, approve=body.approve, actor_id=ctx.user.id, actor_permissions=ctx.permissions, note=body.note)
    except A.ApprovalError as e:
        ctx.db.rollback()
        raise bad_request(str(e)) from None
    ctx.db.commit()
    return _approval_out(ctx, a)


# ---------- Monitors ----------

class MonitorOut(BaseModel):
    key: str
    name: str
    description: str
    category: str
    is_enabled: bool
    config: dict
    config_help: dict
    version: int
    open_cases: int
    last_run: dict | None


@router.get("/monitors", response_model=list[MonitorOut])
def list_monitors(ctx: TenantContext = Depends(require(P.CASES_READ))):
    import app.monitors  # noqa: F401

    counts = dict(ctx.db.execute(select(Case.rule_key, func.count()).where(Case.organization_id == ctx.org_id, Case.status.in_(CASE_OPEN))
                                 .group_by(Case.rule_key)).all())
    out = []
    for key, m in REGISTRY.items():
        enabled, cfg, version = get_config(ctx.db, ctx.org_id, key)
        last = ctx.db.scalar(select(MonitorRun).where(MonitorRun.organization_id == ctx.org_id, MonitorRun.monitor_key == key)
                             .order_by(MonitorRun.started_at.desc()).limit(1))
        out.append(MonitorOut(key=key, name=m.name, description=m.description, category=m.category, is_enabled=enabled, config=cfg,
                              config_help=m.config_help, version=version, open_cases=counts.get(key, 0),
                              last_run={"at": last.started_at, "status": last.status, "found": last.found, "opened": last.opened,
                                        "closed": last.closed, "duration_ms": last.duration_ms, "error": last.error} if last else None))
    return out


class MonitorPatch(BaseModel):
    is_enabled: bool | None = None
    config: dict | None = None


@router.patch("/monitors/{key}", response_model=MonitorOut)
def update_monitor(key: str, body: MonitorPatch, ctx: TenantContext = Depends(require(P.AUTOMATION_MANAGE))):
    import app.monitors  # noqa: F401

    m = REGISTRY.get(key)
    if not m:
        raise not_found("Monitor")
    if body.config:
        unknown = set(body.config) - set(m.default_config)
        if unknown:
            raise bad_request(f"Unknown setting(s): {', '.join(sorted(unknown))}")
        for k, v in body.config.items():
            if not isinstance(v, type(m.default_config[k])) and not (isinstance(v, int) and isinstance(m.default_config[k], float)):
                raise bad_request(f"Setting {k} must be a {type(m.default_config[k]).__name__}")
    row = ctx.db.scalar(select(MonitorConfig).where(MonitorConfig.organization_id == ctx.org_id, MonitorConfig.monitor_key == key,
                                                    MonitorConfig.facility_id.is_(None)))
    if not row:
        row = MonitorConfig(organization_id=ctx.org_id, monitor_key=key, config={}, version=0)
        ctx.db.add(row)
    if body.is_enabled is not None:
        row.is_enabled = body.is_enabled
    if body.config:
        row.config = {**(row.config or {}), **body.config}
    row.version, row.updated_by_id = (row.version or 0) + 1, ctx.user.id
    ctx.audit("monitor.configured", resource_type="monitor", resource_id=key,
              details={"enabled": row.is_enabled, "config": row.config, "version": row.version})
    ctx.db.commit()
    return next(x for x in list_monitors(ctx=ctx) if x.key == key)


@router.post("/monitors/{key}/run")
def run_monitor_now(key: str, ctx: TenantContext = Depends(require(P.AUTOMATION_MANAGE))):
    import app.monitors  # noqa: F401
    from app.core.db import SessionLocal

    if key not in REGISTRY:
        raise not_found("Monitor")
    # Monitors are system processes: run in a system session (not the user's RLS-bound one), scoped to this org.
    db = SessionLocal()
    try:
        run = run_monitor(db, ctx.org_id, key, force=True)
        db.commit()
        result = {"status": run.status, "found": run.found, "opened": run.opened, "updated": run.updated, "closed": run.closed,
                  "error": run.error, "duration_ms": run.duration_ms}
    finally:
        db.close()
    ctx.audit("monitor.run", resource_type="monitor", resource_id=key, details=result)
    ctx.db.commit()
    return result


# ---------- Notifications ----------

@router.get("/notifications/deliveries", response_model=list[DeliveryOut])
def list_deliveries(status: str | None = None, case_id: uuid.UUID | None = None, channel: str | None = None,
                    ctx: TenantContext = Depends(require(P.AUTOMATION_MANAGE))):
    q = select(NotificationDelivery).where(NotificationDelivery.organization_id == ctx.org_id)
    if status:
        q = q.where(NotificationDelivery.status == status)
    if case_id:
        q = q.where(NotificationDelivery.case_id == case_id)
    if channel:
        q = q.where(NotificationDelivery.channel == channel)
    return ctx.db.scalars(q.order_by(NotificationDelivery.created_at.desc()).limit(300)).all()


class PrefIn(BaseModel):
    category: str = Field(default="*", max_length=40)
    in_app: bool = True
    email: bool = True
    sms: bool = False
    portal: bool = True


@router.get("/notification-preferences")
def my_preferences(ctx: TenantContext = Depends(require(P.CASES_READ))):
    rows = ctx.db.scalars(select(NotificationPreference).where(NotificationPreference.organization_id == ctx.org_id,
                                                               NotificationPreference.user_id == ctx.user.id)).all()
    return [{"category": r.category, "in_app": r.in_app, "email": r.email, "sms": r.sms, "portal": r.portal} for r in rows]


@router.put("/notification-preferences")
def set_preference(body: PrefIn, ctx: TenantContext = Depends(require(P.CASES_READ))):
    row = ctx.db.scalar(select(NotificationPreference).where(NotificationPreference.organization_id == ctx.org_id,
                                                             NotificationPreference.user_id == ctx.user.id,
                                                             NotificationPreference.category == body.category))
    if not row:
        row = NotificationPreference(organization_id=ctx.org_id, user_id=ctx.user.id, category=body.category)
        ctx.db.add(row)
    row.in_app, row.email, row.sms, row.portal = body.in_app, body.email, body.sms, body.portal
    ctx.audit("notification_preferences.updated", details=body.model_dump())
    ctx.db.commit()
    return my_preferences(ctx=ctx)


# ---------- Engine health ----------

@router.get("/engine/health")
def engine_health(ctx: TenantContext = Depends(require(P.CASES_READ))):
    org = ctx.org_id
    pending = ctx.db.scalar(select(func.count()).select_from(DomainEvent).where(DomainEvent.organization_id == org, DomainEvent.status == "pending"))
    oldest = ctx.db.scalar(select(func.min(DomainEvent.occurred_at)).where(DomainEvent.organization_id == org, DomainEvent.status == "pending"))
    dead = ctx.db.scalars(select(DomainEvent).where(DomainEvent.organization_id == org, DomainEvent.status == "dead")
                          .order_by(DomainEvent.occurred_at.desc()).limit(20)).all()
    processed_24h = ctx.db.scalar(select(func.count()).select_from(DomainEvent).where(
        DomainEvent.organization_id == org, DomainEvent.status == "done", DomainEvent.dispatched_at > now() - timedelta(hours=24)))
    failed_runs = ctx.db.scalar(select(func.count()).select_from(MonitorRun).where(
        MonitorRun.organization_id == org, MonitorRun.status == "failed", MonitorRun.started_at > now() - timedelta(hours=24)))
    last_run = ctx.db.scalar(select(func.max(MonitorRun.started_at)).where(MonitorRun.organization_id == org))
    from app.engine.notifications import failures

    retrying = ctx.db.scalar(select(func.count()).select_from(DomainEvent).where(
        DomainEvent.organization_id == org, DomainEvent.status == "pending", DomainEvent.attempts > 0))
    handled = ctx.db.scalar(select(func.count()).select_from(EventHandling).join(DomainEvent).where(DomainEvent.organization_id == org))
    lag = (now() - oldest).total_seconds() if oldest else 0
    status = "healthy"
    if dead or failed_runs or lag > 300:
        status = "degraded"
    if last_run is None or (now() - last_run) > timedelta(minutes=30):
        status = "degraded" if status == "healthy" else status
    return {"status": status, "pending_events": pending, "retrying_events": retrying, "oldest_pending_seconds": round(lag),
            "processed_24h": processed_24h, "handler_completions": handled, "dead_events": [
                {"id": e.id, "event_type": e.event_type, "attempts": e.attempts, "last_error": e.last_error, "occurred_at": e.occurred_at}
                for e in dead],
            "monitor_failures_24h": failed_runs, "last_monitor_run": last_run, "notification_failures_24h": failures(ctx.db, org)}


@router.post("/engine/events/{eid}/retry")
def retry_event(eid: uuid.UUID, ctx: TenantContext = Depends(require(P.AUTOMATION_MANAGE))):
    ev = ctx.db.get(DomainEvent, eid)
    if not ev or ev.organization_id != ctx.org_id:
        raise not_found("Event")
    retry_dead(ctx.db, eid)
    ctx.audit("engine.event_retried", resource_type="domain_event", resource_id=eid)
    ctx.db.commit()
    return {"status": "queued"}
