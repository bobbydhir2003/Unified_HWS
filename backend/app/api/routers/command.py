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
def command_summary(facility_id: uuid.UUID | None = None, department_id: uuid.UUID | None = None,
                    ctx: TenantContext = Depends(require(P.CASES_READ))):
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
    if department_id:
        ctx.require_department(department_id)
        case_base = case_base.where(Case.department_id == department_id)
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

    hospital = hospital_section(ctx, fids)
    return {
        "hospital": hospital,
        "generated_at": now(), "facility_id": facility_id, "date": today.isoformat(), "tiles": tiles,
        "cases_by_category": [{"category": c, "severity": s, "count": n} for c, s, n in by_cat_sev],
        "top_cases": case_out(ctx, list(top)),
        "worklists": sorted([{"queue": q, "open": n, "overdue": od} for q, n, od in task_rows], key=lambda r: -r["open"]),
        "appointments_by_status": appt_rows,
        "monitors": [{"key": k, "last_run": t} for k, t in last_runs],
        "engine": {k: eng[k] for k in ("status", "pending_events", "retrying_events", "processed_24h", "monitor_failures_24h",
                                       "notification_failures_24h")},
    }


# ======================= Hospital section (Milestone C1) =======================

def hospital_section(ctx: TenantContext, fids) -> dict:
    """Live hospital operations numbers, each with its source. Empty when the scope has no hospital facility."""
    from app.models import (
        AIJob,
        Claim,
        ClaimFinding,
        EdVisit,
        InpatientStay,
        Location,
        PriorAuthorization,
        SurgicalCase,
    )

    db, org = ctx.db, ctx.org_id
    hq = select(Clinic).where(Clinic.organization_id == org, Clinic.facility_type == "hospital")
    if fids is not None:
        hq = hq.where(Clinic.id.in_(fids))
    hosp_ids = [h.id for h in db.scalars(hq)]
    if not hosp_ids:
        return {"available": False}
    beds = db.execute(select(Department.name, Department.kind, Location.bed_status, func.count()).join(Department, Department.id == Location.department_id)
                      .where(Location.facility_id.in_(hosp_ids), Location.kind == "bed", Location.is_active.is_(True))
                      .group_by(Department.name, Department.kind, Location.bed_status)).all()
    by_dept: dict[str, dict] = {}
    for name, kind, st, n in beds:
        d = by_dept.setdefault(name, {"department": name, "kind": kind, "available": 0, "occupied": 0, "cleaning": 0, "blocked": 0, "reserved": 0})
        d[st] += n
    for d in by_dept.values():
        staffed = sum(d[k] for k in ("available", "occupied", "cleaning", "reserved"))
        d["occupancy_pct"] = round(100 * d["occupied"] / staffed) if staffed else None
    tot = {k: sum(d[k] for d in by_dept.values() if d["kind"] != "emergency") for k in ("available", "occupied", "cleaning", "blocked")}  # inpatient beds
    stays = dict(db.execute(select(InpatientStay.status, func.count()).where(InpatientStay.facility_id.in_(hosp_ids),
                                                                             InpatientStay.status.in_(("pending", "admitted", "discharge_ordered")))
                            .group_by(InpatientStay.status)).all())
    ed = dict(db.execute(select(EdVisit.status, func.count()).where(EdVisit.facility_id.in_(hosp_ids), EdVisit.status != "departed")
                         .group_by(EdVisit.status)).all())
    open_cases = dict(db.execute(select(Case.category, func.count()).where(Case.organization_id == org, Case.status.in_(CASE_OPEN))
                                 .group_by(Case.category)).all())
    today0 = datetime.combine(now().date(), time.min).astimezone()
    or_today = db.scalar(select(func.count()).select_from(SurgicalCase).where(SurgicalCase.facility_id.in_(hosp_ids), SurgicalCase.status != "cancelled",
                                                                              SurgicalCase.start_at >= today0, SurgicalCase.start_at < today0 + timedelta(days=1)))
    draft_claims = db.scalar(select(func.count()).select_from(Claim).where(Claim.organization_id == org, Claim.status.in_(("draft", "denied"))))
    blockers = db.scalar(select(func.count()).select_from(ClaimFinding).where(ClaimFinding.organization_id == org, ClaimFinding.status == "open",
                                                                              ClaimFinding.severity == "blocker"))
    pa_pending = db.scalar(select(func.count()).select_from(PriorAuthorization).where(PriorAuthorization.organization_id == org,
                                                                                      PriorAuthorization.status.in_(("draft", "submitted", "pended"))))
    ai = dict(db.execute(select(AIJob.status, func.count()).where(AIJob.organization_id == org, AIJob.created_at > now() - timedelta(hours=24))
                         .group_by(AIJob.status)).all())
    staffed = tot["available"] + tot["occupied"] + tot["cleaning"]
    T = _tile
    tiles = [
        T("inpatients", "Current inpatients", stays.get("admitted", 0) + stays.get("discharge_ordered", 0), link="/inpatients", source="inpatient_stays"),
        T("beds", "Available beds", tot["available"], link="/beds", tone="danger" if tot["available"] < 3 else "neutral",
          sub=f"{round(100 * tot['occupied'] / staffed) if staffed else 0}% occupied · {tot['cleaning']} cleaning · {tot['blocked']} blocked", source="locations.bed_status"),
        T("ed", "ED in department", sum(ed.values()), link="/ed", tone="warning" if ed.get("boarding") else "neutral",
          sub=f"{ed.get('waiting', 0) + ed.get('triaged', 0)} waiting · {ed.get('boarding', 0)} boarding", source="ed_visits"),
        T("pending_admits", "Awaiting a bed", stays.get("pending", 0), link="/beds", tone="warning" if stays.get("pending") else "success", source="inpatient_stays(pending)"),
        T("discharges", "Discharges ordered", stays.get("discharge_ordered", 0), link="/inpatients", source="inpatient_stays(discharge_ordered)"),
        T("pharmacy", "Pharmacy & supply alerts", open_cases.get("pharmacy", 0) + open_cases.get("inventory", 0), link="/pharmacy?tab=watchdog",
          tone="warning" if open_cases.get("pharmacy") else "neutral", source="cases(pharmacy|inventory)"),
        T("lab", "Lab & imaging alerts", open_cases.get("lab", 0) + open_cases.get("radiology", 0), link="/lab", tone="danger" if open_cases.get("lab") else "neutral",
          source="cases(lab|radiology)"),
        T("staffing", "Staffing gaps", open_cases.get("staffing", 0), link="/roster", tone="warning" if open_cases.get("staffing") else "success", source="cases(staffing)"),
        T("or", "OR cases today", or_today, link="/or", source="surgical_cases"),
        T("revenue", "Claims held / denied", draft_claims, link="/revenue?tab=review", sub=f"{blockers} review blockers · {pa_pending} prior auths open",
          tone="warning" if draft_claims else "neutral", source="claims, claim_findings, prior_authorizations"),
        T("equipment", "Equipment maintenance", open_cases.get("equipment", 0), link="/equipment", source="cases(equipment)"),
        T("ai", "AI activity (24 h)", sum(ai.values()), link="/admin/ai-governance", sub=f"{ai.get('failed', 0)} failed", tone="danger" if ai.get("failed") else "neutral",
          source="ai_jobs"),
    ]
    return {"available": True, "tiles": tiles, "occupancy_by_department": sorted(by_dept.values(), key=lambda d: d["department"])}


@router.get("/command/handoff")
def shift_handoff(facility_id: uuid.UUID | None = None, ctx: TenantContext = Depends(require(P.CASES_READ))):
    """Shift handoff: deterministic sections built from open cases; every line cites its case number. An optional AI
    narrative (Hospital Operations agent) may only restate these items and must cite them; uncited claims are dropped."""
    if not (ctx.can(P.COMMAND_CENTER) or ctx.can(P.AUTOMATION_MANAGE)):
        raise forbidden()
    fids = _scope(ctx, facility_id)
    q = select(Case).where(Case.organization_id == ctx.org_id, Case.status.in_(CASE_OPEN),
                           or_(Case.facility_id.is_(None), Case.facility_id.in_(fids) if fids is not None else True))
    cases = ctx.db.scalars(q.order_by(func.array_position(["critical", "high", "medium", "low", "info"], Case.severity), Case.due_at.asc().nulls_last())).all()
    sections = {}
    for c in cases:
        if c.severity in ("critical", "high") or c.escalation_level or (c.due_at and c.due_at < now()):
            sections.setdefault(c.category, []).append({"ref": f"C{c.number}", "case_id": c.id, "title": c.title, "severity": c.severity,
                                                        "owner": c.assigned_role, "overdue": bool(c.due_at and c.due_at < now()), "escalated": c.escalation_level > 0})
    lines = [f"{len(cases)} open operational cases; {sum(len(v) for v in sections.values())} need attention this shift."]
    for cat, items in sections.items():
        lines.append(f"{cat.replace('_', ' ').title()}: " + "; ".join(f"{i['title']} [{i['ref']}]" for i in items[:4]) + (f" (+{len(items) - 4} more)" if len(items) > 4 else ""))
    narrative, source = "\n".join(lines), "deterministic"
    from app.ai.openai_provider import available

    if available() and sections:
        import re

        from pydantic import BaseModel as _B

        from app.ai.config import effective
        from app.ai.openai_provider import OpenAICore
        from app.ai.policy import contains_phi
        from app.ai.provider import AIError

        class _Out(_B):
            narrative: str

        facts = "\n".join(f"[{i['ref']}] {cat}: {i['title']} (severity {i['severity']}, owner {i['owner']}{', OVERDUE' if i['overdue'] else ''})"
                           for cat, items in sections.items() for i in items)
        try:
            out, _ = OpenAICore().structured(
                system=("Write a concise shift handoff for hospital operations leaders from the numbered facts only. Cite every statement with the "
                        "bracketed reference, e.g. [C1042]. Do not add facts, numbers or recommendations not present."),
                content=[{"type": "input_text", "text": f"<sources>{facts}</sources>"}], schema=_Out, contains_phi=contains_phi(ctx.db, ctx.org_id),
                model=effective().model_for("hospital_operations"), max_output_tokens=1200, name="handoff")
            valid = {i["ref"] for items in sections.values() for i in items}
            sentences = [x for x in re.split(r"(?<=[.!?])\s+", out.narrative) if x.strip()]
            kept = [x for x in sentences if (refs := set(re.findall(r"\[(C\d+)\]", x))) and refs <= valid]
            if kept:
                narrative, source = " ".join(kept), "ai_cited"
        except AIError:
            pass
    ctx.audit("command.handoff_generated", details={"source": source, "items": sum(len(v) for v in sections.values())})
    ctx.db.commit()
    return {"generated_at": now(), "narrative": narrative, "narrative_source": source, "sections": sections, "open_cases": len(cases)}
