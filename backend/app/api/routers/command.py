"""Hospital Command Center API. Every number is computed from live rows (no hardcoded metrics) and carries a drill-down
link to the records behind it. Facility filter respects the caller's facility scope. Milestone B/C add capacity tiles."""

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, literal_column, or_, select

from app.api.deps import TenantContext, require
from app.core.errors import forbidden
from app.core.permissions import P
from app.core.security import now
from app.models import (
    Appointment,
    ApprovalRequest,
    Case,
    Clinic,
    ClinicalNote,
    Department,
    MonitorRun,
    NotificationDelivery,
    Task,
)
from app.models.engine import CASE_OPEN

router = APIRouter(tags=["command"])


def _scope(ctx: TenantContext, facility_id: uuid.UUID | None) -> list[uuid.UUID] | None:
    if facility_id:
        ctx.require_facility(facility_id)
        return [facility_id]
    return ctx.facility_ids


def _tile(key, label, value, *, link=None, tone="neutral", sub=None, source=None):
    return {"key": key, "label": label, "value": value, "link": link, "tone": tone, "sub": sub, "source": source}


@router.get("/command/summary")
def command_summary(facility_id: uuid.UUID | None = None, ctx: TenantContext = Depends(require(P.CASES_READ))):
    if not (ctx.can(P.COMMAND_CENTER) or ctx.can(P.AUTOMATION_MANAGE)):
        raise forbidden("The Command Center is available to administrators and operations roles")
    db, org = ctx.db, ctx.org_id
    fids = _scope(ctx, facility_id)
    clinic = db.get(Clinic, fids[0]) if fids and len(fids) == 1 else None
    tz = ZoneInfo(clinic.timezone if clinic else "America/New_York")
    today = now().astimezone(tz).date()
    day_start = datetime.combine(today, time.min, tz)
    day_end = day_start + timedelta(days=1)

    def fac(col):
        return col.in_(fids) if fids is not None else True

    # --- Appointments today ---
    appt_rows = dict(db.execute(select(Appointment.status, func.count()).where(
        Appointment.organization_id == org, Appointment.start_at >= day_start, Appointment.start_at < day_end, fac(Appointment.clinic_id))
        .group_by(Appointment.status)).all())
    total_appts = sum(v for k, v in appt_rows.items() if k not in ("cancelled",))
    waiting = db.execute(select(func.count(), func.avg(func.extract("epoch", now() - Appointment.checked_in_at))).where(
        Appointment.organization_id == org, Appointment.status == "checked_in", fac(Appointment.clinic_id))).one()
    unsigned = db.scalar(select(func.count()).select_from(ClinicalNote).where(ClinicalNote.organization_id == org, ClinicalNote.status == "draft",
                                                                              ClinicalNote.created_at < now() - timedelta(hours=24)))

    # --- Cases ---
    case_base = select(Case).where(Case.organization_id == org, Case.status.in_(CASE_OPEN),
                                   or_(Case.facility_id.is_(None), fac(Case.facility_id)))
    if ctx.department_ids is not None:
        case_base = case_base.where(or_(Case.department_id.is_(None), Case.department_id.in_(ctx.department_ids)))
    sub = case_base.subquery()
    by_cat_sev = db.execute(select(sub.c.category, sub.c.severity, func.count()).group_by(sub.c.category, sub.c.severity)).all()
    overdue = db.scalar(select(func.count()).select_from(sub).where(sub.c.due_at < now(), sub.c.status != "snoozed"))
    escalated = db.scalar(select(func.count()).select_from(sub).where(sub.c.escalation_level > 0))
    crit = db.scalar(select(func.count()).select_from(sub).where(sub.c.severity.in_(("critical", "high"))))
    ins_open = sum(n for c, _, n in by_cat_sev if c == "insurance")
    ins_high = sum(n for c, s, n in by_cat_sev if c == "insurance" and s in ("high", "critical"))
    top = db.scalars(case_base.order_by(func.array_position(["critical", "high", "medium", "low", "info"], Case.severity),
                                        Case.due_at.asc().nulls_last()).limit(12)).all()

    # --- Approvals / tasks / automation ---
    approvals = db.scalar(select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.organization_id == org,
                                                                                  ApprovalRequest.status == "pending"))
    queue = func.coalesce(Department.name, Task.assigned_role, literal_column("'unassigned'"))
    task_rows = db.execute(select(queue, func.count(),
                                  func.count().filter(Task.due_at < now()))
                           .select_from(Task).outerjoin(Department, Department.id == Task.department_id)
                           .where(Task.organization_id == org, Task.status.in_(("open", "in_progress")))
                           .group_by(queue)).all()
    notif_fail = db.scalar(select(func.count()).select_from(NotificationDelivery).where(
        NotificationDelivery.organization_id == org, NotificationDelivery.status == "failed",
        NotificationDelivery.created_at > now() - timedelta(hours=24)))
    from app.api.routers.operations import engine_health

    eng = engine_health(ctx=ctx)
    last_runs = db.execute(select(MonitorRun.monitor_key, func.max(MonitorRun.started_at)).where(MonitorRun.organization_id == org)
                           .group_by(MonitorRun.monitor_key)).all()

    tiles = [
        _tile("appointments", "Appointments today", total_appts, link="/schedule", sub=f"{appt_rows.get('completed', 0) + appt_rows.get('checked_out', 0)} done · {appt_rows.get('no_show', 0)} no-show",
              source="appointments"),
        _tile("waiting", "Waiting room", waiting[0], link="/front-desk", tone="warning" if (waiting[1] or 0) > 1200 else "neutral",
              sub=f"avg wait {round((waiting[1] or 0) / 60)} min" if waiting[0] else "nobody waiting", source="appointments.checked_in_at"),
        _tile("insurance", "Insurance issues", ins_open, link="/insurance", tone="danger" if ins_high else "warning" if ins_open else "success",
              sub=f"{ins_high} need action within 48 h", source="cases(category=insurance)"),
        _tile("critical", "High-severity cases", crit, link="/command?severity=high", tone="danger" if crit else "success", sub=f"{escalated} escalated",
              source="cases"),
        _tile("overdue", "Past SLA", overdue, link="/command?overdue=1", tone="danger" if overdue else "success", source="cases.due_at"),
        _tile("approvals", "Awaiting approval", approvals, link="/worklist", tone="warning" if approvals else "neutral", source="approval_requests"),
        _tile("unsigned", "Unsigned notes > 24 h", unsigned, link="/encounters", tone="warning" if unsigned else "success", source="clinical_notes"),
        _tile("automation", "Automation health", eng["status"], link="/automation/monitors", tone="success" if eng["status"] == "healthy" else "warning",
              sub=f"{eng['pending_events']} queued · {notif_fail} notification failures (24 h)", source="domain_events, monitor_runs"),
    ]
    from app.api.routers.operations import case_out

    return {
        "generated_at": now(), "facility_id": facility_id, "date": today.isoformat(), "tiles": tiles,
        "cases_by_category": [{"category": c, "severity": s, "count": n} for c, s, n in by_cat_sev],
        "top_cases": case_out(ctx, list(top)),
        "worklists": sorted([{"queue": q, "open": n, "overdue": od} for q, n, od in task_rows], key=lambda r: -r["open"]),
        "appointments_by_status": appt_rows,
        "monitors": [{"key": k, "last_run": t} for k, t in last_runs],
        "engine": {k: eng[k] for k in ("status", "pending_events", "retrying_events", "processed_24h", "monitor_failures_24h",
                                       "notification_failures_24h")},
    }
