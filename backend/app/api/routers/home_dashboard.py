"""Role dashboards (Home): live, scoped figures and worklists for each workspace.

Every number comes from the same functions/queries the department screens use (or a small aggregate with the same
filters: organization, allowed facilities/departments, restricted charts excluded). Sections a role can't read are
omitted, never filled with placeholders. Times are in the facility's timezone.

Shape:
  header   {title, subtitle}
  metrics  [{key, label, value, sub?, tone?, link}]                              (4–5)
  queue    {title, link, kind: schedule|list, items:[{at?, title, detail?, status?, tone?, link, patient_id?}]} | None
  extra    {title, link, items:[…]} | None                                       (second department list)
  agents   {primary, secondary:[…]}                                             (agent keys; availability from /assist/agents)
  ai_recent [{agent_key, summary, at, link?, context_type?, context_id?}]
  automation {monitors, enabled, ai_enabled, safety_rule_only, open_cases, last_run_at, link}
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select

from app.api.deps import TenantContext
from app.core.permissions import P
from app.core.security import now

HEADERS = {
    "doctor": ("Your Clinical Command Center", "Patients, tasks, results and AI support — all in one place."),
    "nurse": ("Your Nursing Station", "Patients on your units, medications due, documentation and handoffs."),
    "receptionist": ("Your Front Desk", "Today's arrivals, check-ins, registration and insurance readiness."),
    "clinic_admin": ("Your Clinic Operations", "Today's schedule, front-desk flow, patient messages and staff."),
    "pharmacist": ("Your Pharmacy Workspace", "Medication verification, stock risks and replenishment."),
    "lab_tech": ("Your Laboratory Worklist", "Specimens to collect, tests in progress and critical results."),
    "radiologist": ("Your Radiology Reading Room", "Studies to read, reports to finish and critical findings."),
    "radiology_tech": ("Your Imaging Worklist", "Exams to schedule and perform, and studies waiting for a report."),
    "bed_manager": ("Your Patient Flow Center", "Beds, admissions waiting, discharges and turnover."),
    "billing": ("Your Revenue Workspace", "Claims to review, holds, denials and authorizations."),
    "insurance_specialist": ("Your Coverage Desk", "Insurance cases, upcoming visits at risk and payer-check outcomes."),
    "hospital_admin": ("Your Hospital Operations Center", "Capacity, flow, staffing and the work waiting on each team."),
    "super_admin": ("Your Platform Overview", "Organization health, accounts, automation and AI activity."),
}
AGENTS = {
    "doctor": ("doctor_assistant", ["medical_scribe", "discharge_coordination", "document_intelligence"]),
    "nurse": ("discharge_coordination", ["doctor_assistant", "document_intelligence"]),
    "receptionist": ("insurance_guardian", ["patient_communication", "document_intelligence"]),
    "clinic_admin": ("patient_communication", ["insurance_guardian", "document_intelligence", "staff_scheduling"]),
    "pharmacist": ("pharmacy_watchdog", ["doctor_assistant"]),
    "lab_tech": ("doctor_assistant", ["pharmacy_watchdog"]),
    "radiologist": ("doctor_assistant", []),
    "radiology_tech": ("doctor_assistant", []),
    "bed_manager": ("discharge_coordination", ["hospital_operations"]),
    "billing": ("claims_review", ["insurance_guardian", "document_intelligence"]),
    "insurance_specialist": ("insurance_guardian", ["claims_review", "patient_communication", "document_intelligence"]),
    "hospital_admin": ("hospital_operations", ["staff_scheduling", "discharge_coordination", "pharmacy_watchdog", "claims_review"]),
    "super_admin": ("hospital_operations", ["insurance_guardian", "pharmacy_watchdog", "discharge_coordination", "claims_review",
                                            "patient_communication", "staff_scheduling", "doctor_assistant", "medical_scribe", "document_intelligence"]),
}


def _safe(fn, default):
    try:
        return fn()
    except Exception:  # noqa: BLE001 — a section the user can't read is omitted
        return default


def _tz(ctx: TenantContext) -> ZoneInfo:
    from app.models import Clinic

    q = select(Clinic.timezone).where(Clinic.organization_id == ctx.org_id, Clinic.is_active.is_(True))
    if ctx.facility_ids is not None:
        q = q.where(Clinic.id.in_(ctx.facility_ids))
    return ZoneInfo(ctx.db.scalar(q.limit(1)) or "America/New_York")


def _day(ctx: TenantContext) -> tuple[datetime, datetime]:
    tz = _tz(ctx)
    start = datetime.combine(now().astimezone(tz).date(), time(0), tz)
    return start, start + timedelta(days=1)


def _m(key, label, value, link, sub=None, tone=None) -> dict:
    return {"key": key, "label": label, "value": value, "link": link, "sub": sub, "tone": tone}


def _fac(q, col, ctx):
    return q.where(col.in_(ctx.facility_ids)) if ctx.facility_ids is not None else q


def _open_cases(ctx, *categories) -> int:
    from app.api.routers.operations import _visible
    from app.models import Case
    from app.models.engine import CASE_OPEN

    q = select(func.count()).select_from(Case).where(Case.status.in_(CASE_OPEN))
    if categories:
        q = q.where(Case.category.in_(categories))
    return ctx.db.scalar(_visible(ctx, q)) or 0


def _case_items(ctx, categories, limit=6) -> list[dict]:
    from app.api.routers.operations import list_cases

    rows = _safe(lambda: [c for cat in categories for c in list_cases(status="open", category=cat, limit=limit, ctx=ctx)], [])
    sev = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows.sort(key=lambda c: (sev.get(c.severity, 2), 0 if c.overdue else 1))
    return [{"title": f"C{c.number} · {c.patient_name or c.title}", "detail": c.title if c.patient_name else c.kind.replace("_", " ").replace(".", " · "),
             "status": "overdue" if c.overdue else c.status.replace("_", " "), "tone": "danger" if c.severity in ("critical", "high") else "warning",
             "link": f"/worklist?case={c.id}", "patient_id": str(c.patient_id) if c.patient_id else None} for c in rows[:limit]]


# ---------------------------------------------------------------------------------------------- shared sections

def _appointments(ctx: TenantContext, provider_only: bool):
    from app.models import Appointment, Patient

    start, end = _day(ctx)
    q = (select(Appointment, Patient).join(Patient, Patient.id == Appointment.patient_id)
         .where(Appointment.organization_id == ctx.org_id, Appointment.start_at >= start, Appointment.start_at < end,
                Patient.is_restricted.is_(False)))
    q = _fac(q, Appointment.clinic_id, ctx)
    if provider_only and ctx.provider:
        q = q.where(Appointment.provider_id == ctx.provider.id)
    return ctx.db.execute(q.order_by(Appointment.start_at)).all()


APPT_TONE = {"scheduled": "neutral", "confirmed": "neutral", "checked_in": "info", "roomed": "info", "in_progress": "primary",
             "completed": "success", "checked_out": "success", "no_show": "danger", "cancelled": "neutral"}


def _schedule(rows, title: str, link: str) -> dict:
    items = [{"at": a.start_at, "title": p.full_name, "detail": a.reason or (a.appointment_type.name if a.appointment_type else "Visit"),
              "status": a.status.replace("_", " "), "tone": APPT_TONE.get(a.status, "neutral"), "link": f"/patients/{p.id}",
              "patient_id": str(p.id)} for a, p in rows if a.status != "cancelled"]
    return {"title": title, "link": link, "kind": "schedule", "items": items[:8], "more": max(0, len(items) - 8)}


def _ed(ctx: TenantContext) -> dict | None:
    if not ctx.can(P.ADT_READ):
        return None
    from app.models import EdVisit, Patient

    q = (select(EdVisit, Patient).join(Patient, Patient.id == EdVisit.patient_id)
         .where(EdVisit.organization_id == ctx.org_id, EdVisit.status != "departed", Patient.is_restricted.is_(False)))
    rows = ctx.db.execute(_fac(q, EdVisit.facility_id, ctx).order_by(EdVisit.esi_level.asc().nulls_first(), EdVisit.arrival_at)).all()
    items = [{"at": v.arrival_at, "title": p.full_name, "detail": f"ESI {v.esi_level}" + f" · {v.chief_complaint}" if v.esi_level else f"Not triaged · {v.chief_complaint}",
              "status": v.status, "tone": "danger" if (v.esi_level or 9) <= 2 or v.status == "waiting" else "info", "link": "/ed",
              "patient_id": str(p.id)} for v, p in rows]
    return {"title": "Emergency department now", "link": "/ed", "kind": "list", "items": items[:6], "more": max(0, len(items) - 6),
            "summary": {"in_department": len(rows), "waiting_triage": sum(1 for v, _ in rows if v.status == "waiting"),
                        "boarding": sum(1 for v, _ in rows if v.status == "boarding")}}


def _results_to_review(ctx: TenantContext) -> int:
    from app.models import Order, Patient

    return ctx.db.scalar(select(func.count()).select_from(Order).join(Patient, Patient.id == Order.patient_id).where(
        Order.organization_id == ctx.org_id, Order.ordered_by_id == ctx.user.id, Order.resulted_at.is_not(None),
        Order.results_reviewed_at.is_(None), Patient.is_restricted.is_(False))) or 0


def _stays(ctx: TenantContext, attending_only: bool):
    from app.models import InpatientStay, Patient

    q = (select(InpatientStay, Patient).join(Patient, Patient.id == InpatientStay.patient_id)
         .where(InpatientStay.organization_id == ctx.org_id, InpatientStay.status.in_(("admitted", "discharge_ordered")), Patient.is_restricted.is_(False)))
    q = _fac(q, InpatientStay.facility_id, ctx)
    if attending_only and ctx.provider:
        q = q.where(InpatientStay.attending_provider_id == ctx.provider.id)
    return ctx.db.execute(q).all()


def ai_recent(ctx: TenantContext, limit: int = 5) -> list[dict]:
    """This user's own agent turns, plus automatic assistance on cases this user can see — never other people's chats."""
    from app.api.routers.operations import _visible
    from app.models import AgentRun, Case

    own = ctx.db.scalars(select(AgentRun).where(AgentRun.organization_id == ctx.org_id, AgentRun.user_id == ctx.user.id)
                         .order_by(AgentRun.started_at.desc()).limit(limit)).all()
    visible = select(Case.id)
    from sqlalchemy import String

    auto = ctx.db.execute(select(AgentRun, Case).join(Case, Case.id.cast(String) == AgentRun.subject_id)
                          .where(AgentRun.organization_id == ctx.org_id, AgentRun.user_id.is_(None), AgentRun.subject_type == "case",
                                 AgentRun.status == "succeeded", Case.id.in_(_visible(ctx, visible)))
                          .order_by(AgentRun.started_at.desc()).limit(limit)).all() if ctx.can(P.CASES_READ) else []
    out = []
    for r in own:
        proposals = len(r.approvals or [])
        what = {"conversation": "Answered a question", "manual": "Test run"}.get(r.trigger, "Ran")
        ctxt = {"workspace": "your workspace", "patient": "a patient chart", "case": "a case", "stay": "an inpatient stay", "claim": "a claim",
                "inventory_item": "an inventory item", "message_thread": "a message thread", "scribe_session": "a scribe draft",
                "document": "a document"}.get(r.context_type or "workspace", "a record")
        out.append({"agent_key": r.agent_key, "at": r.started_at, "status": r.status,
                    "summary": f"{what} about {ctxt}" + (f" · {proposals} proposal{'s' if proposals != 1 else ''}" if proposals else ""),
                    "context_type": r.context_type, "context_id": r.context_id,
                    "link": f"/worklist?case={r.subject_id}" if r.context_type == "case" else (f"/patients/{r.context_id}" if r.context_type == "patient" else None)})
    for r, c in auto:
        out.append({"agent_key": r.agent_key, "at": r.started_at, "status": r.status, "context_type": "case", "context_id": str(c.id),
                    "summary": f"Assisted case C{c.number} automatically" + (" · proposed a next step" if r.approvals else ""),
                    "link": f"/worklist?case={c.id}"})
    out.sort(key=lambda x: x["at"], reverse=True)
    return out[:limit]


def automation(ctx: TenantContext) -> dict | None:
    if not ctx.can(P.CASES_READ):
        return None
    import app.monitors  # noqa: F401
    from app.agents.case_assist import SAFETY_RULE_ONLY, ai_enabled_for
    from app.engine.monitors import REGISTRY, get_config
    from app.models import MonitorRun

    keys = [k for k in REGISTRY if not k.startswith("test.")]
    enabled = sum(1 for k in keys if get_config(ctx.db, ctx.org_id, k)[0])
    last = ctx.db.scalar(select(func.max(MonitorRun.started_at)).where(MonitorRun.organization_id == ctx.org_id))
    return {"monitors": len(keys), "enabled": enabled, "ai_enabled": sum(1 for k in keys if ai_enabled_for(ctx.db, ctx.org_id, k)),
            "safety_rule_only": len(SAFETY_RULE_ONLY), "open_cases": _open_cases(ctx), "last_run_at": last, "link": "/automation/monitors"}


# ---------------------------------------------------------------------------------------------- per role

def build(ctx: TenantContext, profile: str, counts: dict) -> dict:
    title, subtitle = HEADERS.get(profile, ("Your Workspace", "Your tasks, approvals and the agents that can help."))
    primary, secondary = AGENTS.get(profile, ("hospital_operations", []))
    metrics: list[dict] = []
    queue = extra = None
    tasks_open, approvals = counts.get("tasks", 0), counts.get("approvals", 0)
    my_tasks = _m("tasks", "My open tasks", tasks_open, "/worklist?tab=tasks")
    my_approvals = _m("approvals", "Approvals waiting", approvals, "/worklist?tab=approvals", tone="warning" if approvals else None)

    if profile == "doctor":
        appts = _safe(lambda: _appointments(ctx, provider_only=True), [])
        stays = _safe(lambda: _stays(ctx, attending_only=bool(ctx.provider)), [])
        done = sum(1 for a, _ in appts if a.status in ("completed", "checked_out"))
        dc = sum(1 for s, _ in stays if s.status == "discharge_ordered")
        due = sum(1 for s, _ in stays if s.status == "admitted" and s.expected_discharge_date and s.expected_discharge_date <= now().date())
        metrics = [_m("visits", "Today's visits" if ctx.provider else "Clinic visits today", sum(1 for a, _ in appts if a.status != "cancelled"), "/schedule",
                      sub=f"{done} completed"),
                   _m("inpatients", "My inpatients" if ctx.provider else "Inpatients", len(stays), "/inpatients"),
                   {**my_tasks, "sub": f"{counts.get('cases', 0)} open cases" if counts.get("cases") else None},
                   _m("results", "Results to review", _safe(lambda: _results_to_review(ctx), 0), "/orders",
                      sub=f"{counts.get('critical_results', 0)} critical" if counts.get("critical_results") else None,
                      tone="danger" if counts.get("critical_results") else None),
                   _m("discharges", "Discharges in progress", dc, "/discharge", sub=f"{due} more expected today" if due else None)]
        queue = _schedule(appts, "Today's schedule", "/schedule")
        extra = _ed(ctx)
    elif profile == "nurse":
        from app.api.routers.inpatient_care import nursing_patients
        from app.models import HandoffNote, NursingAssessment

        rows = _safe(lambda: nursing_patients(department_id=None, mine=False, ctx=ctx), [])
        stay_ids = [r.get("id") or r.get("stay_id") for r in rows]
        overdue = [r for r in rows if r.get("vitals_overdue")]
        drafts = ctx.db.scalar(select(func.count()).select_from(NursingAssessment).where(
            NursingAssessment.organization_id == ctx.org_id, NursingAssessment.author_id == ctx.user.id, NursingAssessment.status == "draft")) or 0
        handoffs = ctx.db.scalar(select(func.count()).select_from(HandoffNote).where(
            HandoffNote.organization_id == ctx.org_id, HandoffNote.stay_id.in_(stay_ids), HandoffNote.acknowledged_at.is_(None))) or 0 if stay_ids else 0
        meds = _safe(lambda: _meds_due(ctx, stay_ids), [])
        metrics = [_m("patients", "Patients on my units", len(rows), "/nursing"),
                   _m("meds", "Medications due (next 2 h)", len(meds), "/nursing", tone="warning" if meds else None),
                   _m("vitals", "Vitals overdue", len(overdue), "/nursing", tone="warning" if overdue else None),
                   _m("assessments", "Draft assessments", drafts, "/nursing"),
                   _m("handoffs", "Handoffs to acknowledge", handoffs, "/nursing")]
        queue = {"title": "Medications due", "link": "/nursing", "kind": "schedule", "more": max(0, len(meds) - 8), "items": meds[:8]}
        extra = {"title": "Vitals overdue", "link": "/nursing", "kind": "list", "more": max(0, len(overdue) - 6), "items": [
            {"title": (r.get("patient") or {}).get("name") or "Patient", "detail": f"Bed {(r.get('bed') or {}).get('code') or '—'} · vitals over 4 h ago or none",
             "status": "overdue", "tone": "warning", "link": f"/patients/{(r.get('patient') or {}).get('id')}", "patient_id": (r.get("patient") or {}).get("id")}
            for r in overdue[:6]]}
        if not extra["items"]:
            extra = _ed(ctx)
    elif profile in ("receptionist", "clinic_admin"):
        appts = _safe(lambda: _appointments(ctx, provider_only=False), [])
        waiting = sum(1 for a, _ in appts if a.status in ("checked_in", "roomed"))
        to_arrive = sum(1 for a, _ in appts if a.status in ("scheduled", "confirmed"))
        msgs = _safe(lambda: _unread_threads(ctx), 0)
        metrics = [_m("appointments", "Appointments today", sum(1 for a, _ in appts if a.status != "cancelled"), "/schedule"),
                   _m("arriving", "Still to arrive", to_arrive, "/front-desk"),
                   _m("waiting", "Checked in / roomed", waiting, "/front-desk"),
                   _m("insurance", "Insurance issues", _open_cases(ctx, "insurance"), "/insurance", tone="warning"),
                   _m("messages", "Unread patient messages", msgs, "/messages")]
        queue = _schedule(appts, "Today's arrivals", "/front-desk")
        extra = {"title": "Insurance readiness", "link": "/insurance", "kind": "list", "items": _case_items(ctx, ["insurance"], 6)}
    elif profile == "pharmacist":
        from app.api.routers.mar import medication_queue
        from app.models import PurchaseRequest

        q = _safe(lambda: medication_queue(status="pending_verification", ctx=ctx), [])
        clar = _safe(lambda: medication_queue(status="clarification_needed", ctx=ctx), [])
        prs = ctx.db.scalar(_fac(select(func.count()).select_from(PurchaseRequest).where(
            PurchaseRequest.organization_id == ctx.org_id, PurchaseRequest.status == "submitted"), PurchaseRequest.facility_id, ctx)) or 0
        metrics = [_m("verify", "Orders to verify", len(q), "/pharmacy?tab=verify", tone="warning" if q else None),
                   _m("clarify", "Awaiting clarification", len(clar), "/pharmacy?tab=verify"),
                   _m("stock", "Stock & expiry alerts", _open_cases(ctx, "pharmacy", "inventory"), "/pharmacy"),
                   _m("prs", "Purchase requests waiting", prs, "/pharmacy?tab=purchasing"), my_tasks]
        queue = {"title": "Verification queue", "link": "/pharmacy?tab=verify", "kind": "list", "more": max(0, len(q) - 8), "items": [
            {"at": r.get("signed_at"), "title": (r.get("patient") or {}).get("name") or "Patient",
             "detail": " ".join(str(x) for x in ((r.get("details") or {}).get("name"), (r.get("details") or {}).get("dose"), (r.get("details") or {}).get("route")) if x) or r.get("title") or "Medication order",
             "status": r.get("priority") or "routine", "tone": "danger" if r.get("priority") in ("stat", "urgent") else "neutral",
             "link": "/pharmacy?tab=verify", "patient_id": (r.get("patient") or {}).get("id")} for r in q[:8]]}
        extra = {"title": "Stock & expiry alerts", "link": "/pharmacy", "kind": "list", "items": _case_items(ctx, ["pharmacy", "inventory"], 6)}
    elif profile == "lab_tech":
        from app.api.routers.lab import worklist as lab_worklist

        w = _safe(lambda: lab_worklist(ctx=ctx), {})
        specs = w.get("specimens") or []
        crit = w.get("critical_unacknowledged") or []
        verify = [s for s in specs if s.get("status") in ("resulted", "awaiting_verification", "preliminary")]
        metrics = [_m("collect", "Specimens to collect", len(w.get("to_collect") or []), "/lab"),
                   _m("in_lab", "In the lab", len(specs), "/lab"),
                   _m("verify", "Results to verify", len(verify), "/lab", tone="warning" if verify else None),
                   _m("critical", "Critical results unacknowledged", len(crit), "/lab", tone="danger" if crit else None), my_tasks]
        queue = {"title": "To collect", "link": "/lab", "kind": "list", "items": [
            {"title": o["patient"]["name"], "detail": o["title"], "status": o.get("priority") or "routine",
             "tone": "danger" if o.get("priority") in ("stat", "urgent") else "neutral", "link": "/lab", "patient_id": o["patient"].get("id")}
            for o in (w.get("to_collect") or [])[:8]]}
        extra = {"title": "Critical results (rule-based alerts)", "link": "/lab", "kind": "list", "items": [
            {"at": c.get("created_at"), "title": c.get("summary") or "Critical value", "detail": "Waiting for the ordering clinician to acknowledge", "status": "unacknowledged",
             "tone": "danger", "link": "/lab"} for c in crit[:6]]}
    elif profile in ("radiologist", "radiology_tech"):
        from app.api.routers.radiology import worklist as rad_worklist

        w = _safe(lambda: rad_worklist(ctx=ctx), {})
        studies = w.get("studies") or []
        to_read = [s for s in studies if s.get("status") in ("completed", "preliminary")]
        active = [s for s in studies if s.get("status") in ("scheduled", "arrived", "in_progress")]
        metrics = [_m("schedule", "Orders to schedule", len(w.get("to_schedule") or []), "/radiology"),
                   _m("active", "Exams scheduled / in progress", len(active), "/radiology"),
                   _m("read", "Studies awaiting a report", sum(1 for s in to_read if s.get("status") == "completed"), "/radiology",
                      tone="warning" if to_read else None),
                   _m("prelim", "Preliminary reports to finalize", sum(1 for s in to_read if s.get("status") == "preliminary"), "/radiology"), my_tasks]
        rows = to_read if profile == "radiologist" else active
        queue = {"title": "Reading worklist" if profile == "radiologist" else "Exams today", "link": "/radiology", "kind": "list", "items": [
            {"at": s.get("scheduled_at"), "title": (s.get("patient") or {}).get("name") or "Patient", "detail": str(s.get("title") or s.get("modality") or "Study"),
             "status": (s.get("status") or "").replace("_", " "), "tone": "danger" if s.get("priority") in ("stat", "urgent") else "info",
             "link": "/radiology", "patient_id": (s.get("patient") or {}).get("id")} for s in rows[:8]]}
        extra = {"title": "Imaging cases", "link": "/worklist", "kind": "list", "items": _case_items(ctx, ["radiology"], 6)}
    elif profile == "bed_manager":
        from app.api.routers.adt import bed_board

        b = _safe(lambda: bed_board(facility_id=None, ctx=ctx), {})
        t = b.get("totals") or {}
        pend = b.get("pending_admissions") or []
        stays = _safe(lambda: _stays(ctx, attending_only=False), [])
        ordered = [(s, p) for s, p in stays if s.status == "discharge_ordered"]
        metrics = [_m("free", "Free beds", t.get("available", 0), "/beds"),
                   _m("waiting", "Waiting for a bed", len(pend), "/beds", tone="warning" if pend else None),
                   _m("cleaning", "Beds being cleaned", t.get("cleaning", 0), "/beds"),
                   _m("discharging", "Discharge ordered, still in bed", len(ordered), "/discharge"),
                   _m("cases", "Patient-flow cases", _open_cases(ctx, "bed", "discharge"), "/worklist")]
        queue = {"title": "Waiting for a bed", "link": "/beds", "kind": "list", "items": [
            {"at": p.get("requested_at"), "title": (p.get("patient") or {}).get("name") or "Patient", "detail": p.get("reason") or p.get("level_of_care") or "",
             "status": "waiting", "tone": "warning", "link": "/beds", "patient_id": (p.get("patient") or {}).get("id")} for p in pend[:8]]}
        extra = {"title": "Discharges in progress", "link": "/discharge", "kind": "list", "items": [
            {"at": s.discharge_ordered_at, "title": p.full_name, "detail": "Discharge ordered", "status": "awaiting departure", "tone": "info",
             "link": f"/patients/{p.id}", "patient_id": str(p.id)} for s, p in ordered[:6]]}
    elif profile in ("billing", "insurance_specialist"):
        from app.models import Claim, EligibilityCheck, Encounter, Patient, PriorAuthorization

        def claims(*statuses):
            q = (select(func.count()).select_from(Claim).join(Encounter, Encounter.id == Claim.encounter_id)
                 .where(Claim.organization_id == ctx.org_id, Claim.status.in_(statuses)))
            return ctx.db.scalar(_fac(q, Encounter.clinic_id, ctx)) or 0

        pa = ctx.db.scalar(select(func.count()).select_from(PriorAuthorization).where(
            PriorAuthorization.organization_id == ctx.org_id, PriorAuthorization.status.in_(("draft", "submitted", "pended")))) or 0
        if profile == "billing":
            metrics = [_m("review", "Claims ready / draft", claims("draft", "ready"), "/billing"),
                       _m("hold", "Claims with scrub errors", ctx.db.scalar(select(func.count()).select_from(Claim).where(
                           Claim.organization_id == ctx.org_id, Claim.status == "draft", func.jsonb_array_length(Claim.scrub_errors) > 0)) or 0, "/billing", tone="warning"),
                       _m("denied", "Denied claims", claims("denied"), "/revenue", tone="danger"),
                       _m("pa", "Prior authorizations open", pa, "/revenue"), my_tasks]
            from app.api.routers.operations import list_cases

            queue = {"title": "Billing cases", "link": "/revenue", "kind": "list", "items": _case_items(ctx, ["billing"], 8)}
            extra = {"title": "Insurance cases", "link": "/insurance", "kind": "list", "items": _case_items(ctx, ["insurance"], 6)}
            _ = list_cases
        else:
            start, _end = _day(ctx)
            recent = ctx.db.execute(select(EligibilityCheck, Patient).join(Patient, Patient.id == EligibilityCheck.patient_id)
                                    .where(EligibilityCheck.organization_id == ctx.org_id, Patient.is_restricted.is_(False))
                                    .order_by(EligibilityCheck.checked_at.desc()).limit(6)).all()
            escalated = _safe(lambda: _escalated(ctx, "insurance"), 0)
            metrics = [_m("cases", "Open insurance cases", _open_cases(ctx, "insurance"), "/insurance", tone="warning"),
                       _m("escalated", "Escalated", escalated, "/insurance", tone="danger" if escalated else None),
                       _m("checks", "Payer checks today", ctx.db.scalar(select(func.count()).select_from(EligibilityCheck).where(
                           EligibilityCheck.organization_id == ctx.org_id, EligibilityCheck.checked_at >= start)) or 0, "/insurance", sub="simulated payer"),
                       _m("pa", "Prior authorizations open", pa, "/revenue"), my_approvals]
            queue = {"title": "Insurance cases", "link": "/insurance", "kind": "list", "items": _case_items(ctx, ["insurance"], 8)}
            extra = {"title": "Latest payer checks (simulated payer)", "link": "/insurance", "kind": "list", "items": [
                {"at": c.checked_at, "title": p.full_name, "detail": c.message or c.result.replace("_", " "), "status": c.result.replace("_", " "),
                 "tone": "success" if c.result == "active" else "warning", "link": f"/insurance?patient={p.id}", "patient_id": str(p.id)} for c, p in recent]}
    elif profile in ("hospital_admin", "super_admin"):
        from app.api.routers.command import hospital_section

        h = _safe(lambda: hospital_section(ctx, ctx.facility_ids), {})
        tiles = {t["key"]: t for t in h.get("tiles", [])}
        for key in ("inpatients", "beds", "ed", "staffing"):
            if key in tiles:
                t = tiles[key]
                metrics.append(_m(key, t["label"], t["value"], t.get("link") or "/command", sub=t.get("sub"), tone=t.get("tone")))
        metrics.append(_m("cases", "Open cases", _open_cases(ctx), "/worklist"))
        if profile == "super_admin":
            from app.models import AgentRun, Membership

            staff = ctx.db.scalar(select(func.count()).select_from(Membership).where(Membership.organization_id == ctx.org_id, Membership.is_active.is_(True))) or 0
            runs = ctx.db.scalar(select(func.count()).select_from(AgentRun).where(AgentRun.organization_id == ctx.org_id,
                                                                                    AgentRun.started_at >= now() - timedelta(hours=24))) or 0
            metrics = metrics[:3] + [_m("staff", "Active staff accounts", staff, "/admin/staff"), _m("ai_runs", "AI agent runs (24 h)", runs, "/agents")]
        queue = {"title": "Problems by severity", "link": "/command", "kind": "list",
                 "items": _case_items(ctx, ["ed", "bed", "discharge", "staffing", "equipment", "pharmacy", "inventory", "insurance", "billing", "lab", "radiology"], 8)}
        extra = _ed(ctx)
    else:
        metrics = [my_tasks, my_approvals, _m("cases", "Open cases", counts.get("cases", 0), "/worklist")]
    return {"header": {"title": title, "subtitle": subtitle}, "metrics": [m for m in metrics if m][:5], "queue": queue,
            "extra": extra if extra and extra.get("items") else None, "agents": {"primary": primary, "secondary": secondary},
            "ai_recent": _safe(lambda: ai_recent(ctx), []), "automation": _safe(lambda: automation(ctx), None), "generated_at": now(),
            "timezone": str(_safe(lambda: _tz(ctx), "America/New_York"))}


def _meds_due(ctx: TenantContext, stay_ids: list) -> list[dict]:
    """Scheduled administrations in the next 2 hours (and up to 1 hour overdue) for active inpatient medication orders of
    patients on the nurse's units, minus those already documented. Same schedule logic as the eMAR."""
    if not stay_ids:
        return []
    from app.models import InpatientStay, MedicationAdministration, Order, Patient
    from app.services.medication import slots

    pids = [p for (p,) in ctx.db.execute(select(InpatientStay.patient_id).where(InpatientStay.id.in_(stay_ids))).all()]
    start, end = now() - timedelta(hours=1), now() + timedelta(hours=2)
    rows = ctx.db.execute(select(Order, Patient).join(Patient, Patient.id == Order.patient_id).where(
        Order.organization_id == ctx.org_id, Order.order_type == "medication", Order.status == "active", Order.patient_id.in_(pids),
        Patient.is_restricted.is_(False))).all()
    out = []
    for o, p in rows:
        given = {a for (a,) in ctx.db.execute(select(MedicationAdministration.scheduled_for).where(MedicationAdministration.order_id == o.id)).all()}
        for s in slots(ctx.db, o, start, end, None):
            if s not in given:
                d = o.details or {}
                out.append({"at": s, "title": p.full_name, "detail": " ".join(str(x) for x in (d.get("name"), d.get("dose"), d.get("route")) if x) or o.title,
                            "status": "overdue" if s < now() else "due", "tone": "danger" if s < now() else "info",
                            "link": f"/patients/{p.id}/mar", "patient_id": str(p.id)})
    return sorted(out, key=lambda x: x["at"])


def _unread_threads(ctx: TenantContext) -> int:
    from app.models import MessageThread, Patient

    return ctx.db.scalar(select(func.count()).select_from(MessageThread).join(Patient, Patient.id == MessageThread.patient_id).where(
        MessageThread.organization_id == ctx.org_id, MessageThread.status == "open", MessageThread.staff_unread > 0,
        Patient.is_restricted.is_(False))) or 0


def _escalated(ctx: TenantContext, category: str) -> int:
    from app.api.routers.operations import _visible
    from app.models import Case

    return ctx.db.scalar(_visible(ctx, select(func.count()).select_from(Case).where(Case.status == "escalated", Case.category == category))) or 0


_ = or_
