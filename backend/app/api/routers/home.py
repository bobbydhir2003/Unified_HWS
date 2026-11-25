"""Role-based Home (UX simplification): one call returning what needs the signed-in user's attention now.

* `priorities` — at most 5 items merged from the existing worklist (cases + tasks + approvals) and unacknowledged
  critical results, ranked by clinical severity first, then overdue before on-time within the same severity, then due
  time — so a routine overdue task never outranks a critical clinical item. Each item says what it is (rule alert, task, approval,
  critical result), who owns it, its status and the next action.
* `today` — a few role-relevant counts computed by the SAME functions the department screens use, so the numbers
  always match what the user sees when they click through.
Nothing here is invented: every value comes from live records the user is already allowed to read.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import TenantContext, get_ctx
from app.core.permissions import ROLE_LABELS, P, Role
from app.core.security import now

router = APIRouter(tags=["home"])

# First matching role decides the Home profile (a user can hold several roles).
PROFILE_ORDER = ["super_admin", "hospital_admin", "clinic_admin", "doctor", "nurse", "pharmacist", "lab_tech", "radiologist",
                 "radiology_tech", "bed_manager", "billing", "insurance_specialist", "receptionist"]
SEVERITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}
TASK_PRIORITY = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


def profile_for(roles: list[str]) -> str:
    for r in PROFILE_ORDER:
        if r in roles:
            return {"radiology_tech": "radiologist"}.get(r, r)
    return roles[0] if roles else "staff"


def _role_label(role: str | None) -> str | None:
    if not role:
        return None
    try:
        return ROLE_LABELS[Role(role)]
    except ValueError:
        return role.replace("_", " ").title()


def _safe(fn, default):
    try:
        return fn()
    except Exception:  # noqa: BLE001 — a section the user can't read is simply omitted
        return default


def _priorities(ctx: TenantContext) -> tuple[list[dict], dict]:
    from app.api.routers.operations import worklist

    items: list[dict] = []
    counts = {"cases": 0, "tasks": 0, "approvals": 0, "critical_results": 0}
    if ctx.can(P.CASES_READ):
        w = worklist(ctx=ctx)
        counts.update({k: w["counts"][k] for k in ("cases", "tasks", "approvals")})
        for c in w["cases"]:
            items.append({
                "id": str(c.id), "kind": "case", "kind_label": "Rule alert", "title": c.title, "severity": c.severity,
                "status": c.status, "overdue": c.overdue, "due_at": c.due_at, "owner": _role_label(c.assigned_role) or "Unassigned",
                "patient_name": c.patient_name, "link": f"/worklist?case={c.id}", "action": "Open case",
                "escalated": c.escalation_level > 0})
        for t in w["tasks"]:
            due = t.get("due_at")
            items.append({
                "id": str(t["id"]), "kind": "task", "kind_label": "Task", "title": t["title"],
                "severity": {"urgent": "critical", "high": "high", "normal": "medium", "low": "low"}.get(t.get("priority") or "normal", "medium"),
                "status": t["status"], "overdue": bool(due and due < now()), "due_at": due, "owner": _role_label(t.get("assigned_role")) or "You",
                "patient_name": t.get("patient_name"), "link": t.get("link") or "/worklist?tab=tasks", "action": "Open task"})
        for a in w["approvals"]:
            items.append({
                "id": str(a.id), "kind": "approval", "kind_label": "Needs approval", "title": a.title, "severity": "high",
                "status": "waiting", "overdue": False, "due_at": None, "owner": "You (approver)", "patient_name": None,
                "link": "/worklist?tab=approvals", "action": "Review",
                "requested_by_agent": a.requested_by_agent})
    if ctx.can(P.ORDERS_SIGN) or ctx.can(P.LAB_VERIFY):
        from app.models import CriticalResultAlert, Patient

        q = select(CriticalResultAlert, Patient).join(Patient, Patient.id == CriticalResultAlert.patient_id).where(
            CriticalResultAlert.organization_id == ctx.org_id, CriticalResultAlert.acknowledged_at.is_(None), Patient.is_restricted.is_(False))
        if not ctx.can(P.LAB_VERIFY):  # clinicians: alerts for their own orders
            q = q.where(CriticalResultAlert.clinician_user_id == ctx.user.id)
        rows = ctx.db.execute(q.order_by(CriticalResultAlert.created_at)).all()
        counts["critical_results"] = len(rows)
        for a, p in rows:
            items.append({
                "id": str(a.id), "kind": "critical_result", "kind_label": "Critical result", "title": f"{a.summary} — acknowledge",
                "severity": "critical", "status": "waiting", "overdue": True, "due_at": a.created_at, "owner": "Ordering clinician",
                "patient_name": p.full_name, "link": "/lab", "action": "Acknowledge"})

    def rank(i: dict):
        due = i.get("due_at")
        return (SEVERITY.get(i["severity"], 2), 0 if i["overdue"] else 1, due.timestamp() if isinstance(due, datetime) else float("inf"))

    items.sort(key=rank)
    return items[:5], counts


def _today(ctx: TenantContext, profile: str) -> dict:
    """{ 'metrics': [{label, value, link, hint?}], 'list': {title, items:[{title, detail, link}]} | None }"""
    m: list[dict] = []
    lst: dict | None = None
    if profile in ("doctor", "receptionist", "clinic_admin"):
        from app.api.routers.workspace import dashboard

        d = _safe(lambda: dashboard(clinic_id=None, ctx=ctx), {})
        ap = d.get("appointments") or {}
        bs = ap.get("by_status") or {}
        if ap:
            m.append({"label": "Appointments today", "value": ap.get("total", 0), "link": "/schedule"})
            m.append({"label": "Checked in or roomed", "value": len(ap.get("waiting") or []), "link": "/front-desk"})
            m.append({"label": "Completed", "value": bs.get("checked_out", 0) + bs.get("completed", 0), "link": "/schedule"})
            lst = {"title": "Up next", "items": [
                {"title": a["patient"], "at": a["start_at"], "detail": " · ".join(x for x in (a.get("type"), a.get("reason")) if x),
                 "link": f"/patients/{a['patient_id']}"} for a in (ap.get("next") or [])[:5]]}
        if profile == "doctor":
            from app.models import Encounter

            if ctx.provider:
                n = ctx.db.scalar(select(func.count()).select_from(Encounter).where(
                    Encounter.organization_id == ctx.org_id, Encounter.provider_id == ctx.provider.id, Encounter.status == "in_progress")) or 0
                m.append({"label": "Open visits to document", "value": n, "link": "/encounters"})
        if profile in ("receptionist", "clinic_admin"):
            from app.models import Case
            from app.models.engine import CASE_OPEN

            n = ctx.db.scalar(select(func.count()).select_from(Case).where(
                Case.organization_id == ctx.org_id, Case.category == "insurance", Case.status.in_(CASE_OPEN))) or 0
            m.append({"label": "Insurance issues", "value": n, "link": "/insurance"})
    elif profile == "nurse":
        from app.api.routers.inpatient_care import nursing_patients

        rows = _safe(lambda: nursing_patients(department_id=None, mine=False, ctx=ctx), [])
        overdue = [r for r in rows if r.get("vitals_overdue")]
        m += [{"label": "Patients on my units", "value": len(rows), "link": "/nursing"},
              {"label": "Vitals overdue", "value": len(overdue), "link": "/nursing"}]
        lst = {"title": "Vitals overdue", "items": [
            {"title": f"{(r.get('bed') or {}).get('code') or '—'} · {(r.get('patient') or {}).get('name')}", "detail": "Vitals due",
             "link": f"/inpatients/{r.get('stay_id') or r.get('id')}"} for r in overdue[:5]]}
    elif profile == "pharmacist":
        from app.api.routers.pharmacy import verification_queue
        from app.models import Case, PurchaseRequest
        from app.models.engine import CASE_OPEN

        q = _safe(lambda: verification_queue(ctx=ctx), [])
        stock = ctx.db.scalar(select(func.count()).select_from(Case).where(
            Case.organization_id == ctx.org_id, Case.category.in_(("pharmacy", "inventory")), Case.status.in_(CASE_OPEN))) or 0
        prs = ctx.db.scalar(select(func.count()).select_from(PurchaseRequest).where(
            PurchaseRequest.organization_id == ctx.org_id, PurchaseRequest.status == "submitted")) or 0
        m += [{"label": "Orders to verify", "value": len(q), "link": "/pharmacy"},
              {"label": "Stock alerts", "value": stock, "link": "/pharmacy"},
              {"label": "Purchase requests waiting", "value": prs, "link": "/pharmacy"}]
        lst = {"title": "Verification queue", "items": [
            {"title": str(v.get("title") or v.get("medication") or "Medication order"), "detail": (v.get("patient") or {}).get("name") or "",
             "link": "/pharmacy"} for v in q[:5]]}
    elif profile == "lab_tech":
        from app.api.routers.lab import worklist as lab_worklist

        w = _safe(lambda: lab_worklist(ctx=ctx), {})
        specs = w.get("specimens") or []
        m += [{"label": "Specimens to collect", "value": len(w.get("to_collect") or []), "link": "/lab"},
              {"label": "In the lab", "value": len(specs), "link": "/lab"},
              {"label": "Critical results unacknowledged", "value": len(w.get("critical_unacknowledged") or []), "link": "/lab"}]
        lst = {"title": "To collect", "items": [{"title": o["title"], "detail": o["patient"]["name"], "link": "/lab"} for o in (w.get("to_collect") or [])[:5]]}
    elif profile == "radiologist":
        from app.api.routers.radiology import worklist as rad_worklist

        w = _safe(lambda: rad_worklist(ctx=ctx), {})
        studies = w.get("studies") or []
        to_read = [s for s in studies if s.get("status") in ("completed", "preliminary")]
        m += [{"label": "Orders to schedule", "value": len(w.get("to_schedule") or []), "link": "/radiology"},
              {"label": "Exams in progress", "value": sum(1 for s in studies if s.get("status") in ("scheduled", "arrived", "in_progress")), "link": "/radiology"},
              {"label": "Reports to finish", "value": len(to_read), "link": "/radiology"}]
        lst = {"title": "Reports to finish", "items": [
            {"title": str(s.get("title") or s.get("modality")), "detail": (s.get("patient") or {}).get("name") or "", "link": "/radiology"} for s in to_read[:5]]}
    elif profile == "bed_manager":
        from app.api.routers.adt import bed_board

        b = _safe(lambda: bed_board(facility_id=None, ctx=ctx), {})
        t = b.get("totals") or {}
        pend = b.get("pending_admissions") or []
        m += [{"label": "Free beds", "value": t.get("available", 0), "link": "/beds"},
              {"label": "Waiting for a bed", "value": len(pend), "link": "/beds"},
              {"label": "Beds being cleaned", "value": t.get("cleaning", 0), "link": "/beds"}]
        lst = {"title": "Waiting for a bed", "items": [
            {"title": (p.get("patient") or {}).get("name") or "Patient", "detail": p.get("reason") or "", "link": "/beds"} for p in pend[:5]]}
    elif profile in ("billing", "insurance_specialist"):
        from app.models import Case, Claim, PriorAuthorization
        from app.models.engine import CASE_OPEN

        held = ctx.db.scalar(select(func.count()).select_from(Claim).where(Claim.organization_id == ctx.org_id, Claim.status.in_(("held", "on_hold")))) or 0
        denied = ctx.db.scalar(select(func.count()).select_from(Claim).where(Claim.organization_id == ctx.org_id, Claim.status == "denied")) or 0
        pa = ctx.db.scalar(select(func.count()).select_from(PriorAuthorization).where(
            PriorAuthorization.organization_id == ctx.org_id, PriorAuthorization.status.in_(("draft", "submitted", "pended")))) or 0
        ins = ctx.db.scalar(select(func.count()).select_from(Case).where(
            Case.organization_id == ctx.org_id, Case.category == "insurance", Case.status.in_(CASE_OPEN))) or 0
        if profile == "billing":
            m += [{"label": "Claims on hold", "value": held, "link": "/billing"}, {"label": "Denied claims", "value": denied, "link": "/revenue"},
                  {"label": "Prior authorizations open", "value": pa, "link": "/revenue"}]
        else:
            m += [{"label": "Insurance issues", "value": ins, "link": "/insurance"}, {"label": "Prior authorizations open", "value": pa, "link": "/revenue"},
                  {"label": "Claims on hold", "value": held, "link": "/billing"}]
    elif profile == "hospital_admin":
        from app.api.routers.command import hospital_section

        h = _safe(lambda: hospital_section(ctx, ctx.facility_ids), {})
        tiles = {t["key"]: t for t in h.get("tiles", [])}
        for key in ("inpatients", "beds", "ed", "discharges", "staffing"):
            if key in tiles:
                t = tiles[key]
                m.append({"label": t["label"], "value": t["value"], "link": t.get("link") or "/command", "hint": t.get("sub")})
    elif profile == "super_admin":
        from app.ai.policy import provider_label
        from app.api.routers.operations import engine_health
        from app.models import Membership

        eh = _safe(lambda: engine_health(ctx=ctx), {})
        lab = _safe(provider_label, {})
        from datetime import timedelta

        from app.models import AuditEvent

        staff = ctx.db.scalar(select(func.count()).select_from(Membership).where(Membership.organization_id == ctx.org_id, Membership.is_active.is_(True))) or 0
        members = select(Membership.user_id).where(Membership.organization_id == ctx.org_id)
        failed = ctx.db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == "auth.login", AuditEvent.outcome == "failure", AuditEvent.actor_user_id.in_(members),
            AuditEvent.created_at >= now() - timedelta(hours=24))) or 0
        m += [{"label": "Automation health", "value": (eh.get("status") or "unknown").title(), "link": "/automation/monitors"},
              {"label": "AI provider", "value": "Live" if lab.get("live") else "Simulated", "link": "/admin/ai-settings"},
              {"label": "Active staff accounts", "value": staff, "link": "/admin/staff"},
              {"label": "Failed sign-ins (24 h)", "value": failed, "link": "/admin/audit"}]
    return {"metrics": m, "list": lst if lst and lst["items"] else None}


@router.get("/home")
def home(ctx: TenantContext = Depends(get_ctx)):
    profile = profile_for(list(ctx.roles))
    priorities, counts = _priorities(ctx)
    from app.api.routers.home_dashboard import build

    roles = list(ctx.roles)
    dash_profile = "radiology_tech" if profile == "radiologist" and "radiologist" not in roles else profile
    return {"profile": profile, "dashboard_profile": dash_profile, "role_label": _role_label(dash_profile),
            "priorities": priorities, "counts": counts, "today": _today(ctx, profile), "dashboard": build(ctx, dash_profile, counts),
            "identity": {"name": ctx.user.display_name, "first_name": ctx.user.first_name, "title": ctx.user.title,
                         "is_platform_admin": bool(ctx.user.is_superadmin), "has_provider_profile": bool(ctx.provider),
                         "acting_role": getattr(ctx.request.state, "acting_role", None)}}
