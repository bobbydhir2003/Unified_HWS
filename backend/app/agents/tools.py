"""Backend-defined agent tools. Agents never get database access: each tool validates its arguments (Pydantic), checks the
*invoking user's* permission (and facility/patient access through the usual helpers), and returns minimal data.
'propose_*' tools only create approval requests — a permitted human executes them."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.core.permissions import P
from app.core.security import now
from app.engine import approvals as AP
from app.models import Case, Claim, ClaimFinding, InpatientStay, InventoryItem, Patient


@dataclass
class Tool:
    name: str
    description: str
    params: type[BaseModel]
    permission: str
    kind: str  # read | propose
    fn: Callable[..., dict]


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, params: type[BaseModel], permission: str, kind: str = "read"):
    def deco(fn):
        REGISTRY[name] = Tool(name, description, params, permission, kind, fn)
        return fn

    return deco


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown arguments are rejected, never ignored


class _None(_Args):
    pass


class _Cases(_Args):
    category: str | None = Field(default=None, description="insurance, pharmacy, inventory, lab, bed, ed, discharge, billing, staffing, equipment …")
    limit: int = Field(default=10, ge=1, le=25)


def _case_brief(c: Case) -> dict:
    return {"ref": f"C{c.number}", "title": c.title, "severity": c.severity, "status": c.status, "owner_role": c.assigned_role,
            "overdue": bool(c.due_at and c.due_at < now()), "category": c.category}


@tool("list_open_cases", "List open operational cases (most severe first).", _Cases, P.CASES_READ)
def list_open_cases(ctx, a: _Cases) -> dict:
    from app.api.routers.operations import list_cases

    rows = list_cases(status="open", category=a.category, limit=a.limit, ctx=ctx)
    return {"cases": [{"ref": f"C{c.number}", "title": c.title, "severity": c.severity, "status": c.status, "owner_role": c.assigned_role,
                       "overdue": c.overdue, "category": c.category} for c in rows]}


class _CaseRef(_Args):
    ref: str = Field(description="Case reference such as C1042")


def _find_case(ctx, ref: str) -> Case | None:
    num = ref.upper().lstrip("C")
    if not num.isdigit():
        return None
    from app.api.routers.operations import _visible

    return ctx.db.scalars(_visible(ctx, select(Case).where(Case.number == int(num)))).first()


@tool("get_case", "Get one case with its evidence and recent timeline.", _CaseRef, P.CASES_READ)
def get_case(ctx, a: _CaseRef) -> dict:
    c = _find_case(ctx, a.ref)
    if not c:
        return {"error": "case not found or not accessible"}
    from app.models import CaseEvent

    ev = ctx.db.scalars(select(CaseEvent).where(CaseEvent.case_id == c.id).order_by(CaseEvent.at.desc()).limit(6)).all()
    return {**_case_brief(c), "summary": c.summary, "evidence": c.evidence, "recent_events": [e.message for e in ev]}


class _Worklist(_Args):
    limit: int = Field(default=10, ge=1, le=15)


@tool("get_insurance_worklist", "Open insurance cases with each patient's current coverage state in ONE call (use this first).", _Worklist, P.CASES_READ)
def get_insurance_worklist(ctx, a: _Worklist) -> dict:
    """Bounded retrieval: replaces 1 + 2N calls (list, then get_case + get_patient_coverage per case)."""
    from app.api.routers.operations import _visible
    from app.services.insurance import coverage_state

    rows = ctx.db.scalars(_visible(ctx, select(Case).where(Case.status.in_(("open", "in_progress", "waiting", "escalated")), Case.category == "insurance"))
                          .order_by(Case.due_at.asc().nulls_last()).limit(a.limit)).all()
    can_pt = ctx.can(P.PATIENTS_READ)
    out = []
    for c in rows:
        item = {**_case_brief(c), "summary": (c.summary or "")[:200], "patient_id": str(c.patient_id) if c.patient_id and can_pt else None}
        if c.patient_id and can_pt:
            try:
                st = coverage_state(ctx.db, c.patient_id, now().date())
                item.update(coverage=st.state, coverage_reason=st.reason, payer=st.insurance.payer_name if st.insurance else None)
            except Exception:  # noqa: BLE001
                item["coverage"] = None
        out.append(item)
    return {"worklist": out, "note": "Payer checks are simulated in this environment (no live payer connection)."}


class _PatientRef(_Args):
    patient_id: str


def _patient(ctx, pid: str) -> Patient | None:
    from app.services.patients import get_patient

    try:
        return get_patient(ctx, uuid.UUID(pid))
    except Exception:  # noqa: BLE001 — not found / forbidden → hidden from the agent
        return None


@tool("get_patient_coverage", "Insurance coverage state for a patient's next visit (payer-verified, not stored dates).", _PatientRef, P.PATIENTS_READ)
def get_patient_coverage(ctx, a: _PatientRef) -> dict:
    p = _patient(ctx, a.patient_id)
    if not p:
        return {"error": "patient not found or not accessible"}
    from app.services.insurance import coverage_state

    st = coverage_state(ctx.db, p.id, now().date())
    return {"state": st.state, "reason": st.reason, "payer": st.insurance.payer_name if st.insurance else None}


class _StayRef(_Args):
    stay_id: str


@tool("get_discharge_status", "Discharge checklist status (blocking items and owners) for an inpatient stay.", _StayRef, P.ADT_READ)
def get_discharge_status(ctx, a: _StayRef) -> dict:
    try:
        s = ctx.db.get(InpatientStay, uuid.UUID(a.stay_id))
    except ValueError:
        s = None
    if not s or s.organization_id != ctx.org_id or not ctx.facility_allowed(s.facility_id):
        return {"error": "stay not found or not accessible"}
    from app.services.discharge import readiness

    r = readiness(ctx.db, s)
    if not r:
        return {"status": s.status, "plan": None}
    return {"status": s.status, "ready": r["ready"], "blocking": r["blocking"],
            "items": [{"label": i["label"], "status": i["status"], "owner": i["owner_role"]} for i in r["items"]]}


class _Item(_Args):
    name: str


@tool("get_inventory_item", "Stock on hand, consumption and reorder recommendation for an inventory item (by name).", _Item, P.INVENTORY_READ)
def get_inventory_item(ctx, a: _Item) -> dict:
    it = ctx.db.scalar(select(InventoryItem).where(InventoryItem.organization_id == ctx.org_id, func.lower(InventoryItem.name).like(f"%{a.name.lower()[:60]}%")).limit(1))
    if not it:
        return {"error": "item not found"}
    from app.services.inventory import recommend_reorder

    return {"item": it.name, "unit": it.unit, "reorder_point": it.reorder_point, **recommend_reorder(ctx.db, it)}


class _Claim(_Args):
    claim_number: str


@tool("get_claim_findings", "Open review findings and scrub errors for a claim (advisory).", _Claim, P.BILLING_READ)
def get_claim_findings(ctx, a: _Claim) -> dict:
    c = ctx.db.scalar(select(Claim).where(Claim.organization_id == ctx.org_id, Claim.claim_number == a.claim_number))
    if not c:
        return {"error": "claim not found"}
    f = ctx.db.scalars(select(ClaimFinding).where(ClaimFinding.claim_id == c.id, ClaimFinding.status == "open")).all()
    return {"status": c.status, "scrub_errors": c.scrub_errors, "findings": [{"severity": x.severity, "message": x.message} for x in f]}


@tool("get_staffing_gaps", "Departments below minimum staffing in the next 48 hours.", _None, P.ROSTER_MANAGE)
def get_staffing_gaps(ctx, a: _None) -> dict:
    from app.services.rostering import gaps

    return {"gaps": [{"department": g["department"], "role": g["role"], "window": g["window"], "start": g["start"].isoformat(), "short": g["short"]}
                     for g in gaps(ctx.db, ctx.org_id)]}


@tool("get_operations_summary", "Hospital operations numbers (beds, ED, discharges, alerts) with their sources.", _None, P.COMMAND_CENTER)
def get_operations_summary(ctx, a: _None) -> dict:
    from app.api.routers.command import hospital_section

    h = hospital_section(ctx, ctx.facility_ids)
    return {"tiles": [{"metric": t["label"], "value": t["value"], "detail": t["sub"], "source": t["source"]} for t in h.get("tiles", [])]}


@tool("get_recent_volume", "Counts of admissions, discharges and ED arrivals over the last N days (for trend questions).", _None, P.ADT_READ)
def get_recent_volume(ctx, a: _None) -> dict:
    from app.models import EdVisit

    since = now() - timedelta(days=7)
    return {"window_days": 7,
            "admissions": ctx.db.scalar(select(func.count()).select_from(InpatientStay).where(InpatientStay.organization_id == ctx.org_id, InpatientStay.admitted_at > since)),
            "discharges": ctx.db.scalar(select(func.count()).select_from(InpatientStay).where(InpatientStay.organization_id == ctx.org_id, InpatientStay.discharged_at > since)),
            "ed_arrivals": ctx.db.scalar(select(func.count()).select_from(EdVisit).where(EdVisit.organization_id == ctx.org_id, EdVisit.arrival_at > since))}


# ---------- proposals (approval required) ----------

class _ProposeTask(_Args):
    title: str = Field(min_length=3, max_length=200)
    role: str = Field(description="Role to assign, e.g. nurse, pharmacist, insurance_specialist")
    case_ref: str | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")


@tool("propose_task", "Propose a staff task (a person must approve before it is created).", _ProposeTask, P.CASES_WORK, kind="propose")
def propose_task(ctx, a: _ProposeTask, *, agent: str) -> dict:
    case = _find_case(ctx, a.case_ref) if a.case_ref else None
    req = AP.request_approval(ctx.db, ctx.org_id, kind="agent.create_task", title=f"{agent}: create task — {a.title}", summary=f"Assign to {a.role}",
                              payload={"title": a.title, "role": a.role, "priority": a.priority, "case_id": str(case.id) if case else None},
                              required_permission=P.CASES_WORK, case=case, requested_by_agent=agent)
    return {"proposal": "pending approval", "approval_id": str(req.id)}


class _ProposeMsg(_Args):
    patient_id: str
    subject: str = Field(min_length=3, max_length=150)
    body: str = Field(min_length=10, max_length=1500)


@tool("propose_patient_message", "Draft a routine administrative portal message to a patient (staff approve and send). No clinical advice.",
      _ProposeMsg, P.MESSAGES, kind="propose")
def propose_patient_message(ctx, a: _ProposeMsg, *, agent: str) -> dict:
    p = _patient(ctx, a.patient_id)
    if not p:
        return {"error": "patient not found or not accessible"}
    req = AP.request_approval(ctx.db, ctx.org_id, kind="agent.patient_message", title=f"{agent}: message {p.full_name} — {a.subject}", summary=a.body,
                              payload={"patient_id": str(p.id), "subject": a.subject, "body": a.body}, required_permission=P.MESSAGES,
                              patient_id=p.id, requested_by_agent=agent)
    return {"proposal": "pending approval", "approval_id": str(req.id)}


@AP.executor("agent.create_task")
def _exec_task(db, req, actor_id) -> dict:
    from app.engine.cases import add_task

    case = db.get(Case, uuid.UUID(req.payload["case_id"])) if req.payload.get("case_id") else None
    t = add_task(db, case, org_id=req.organization_id, title=req.payload["title"], role=req.payload["role"], priority=req.payload["priority"],
                 kind="agent.task", source="automation")
    return {"task_id": str(t.id) if t else None}


@AP.executor("agent.patient_message")
def _exec_msg(db, req, actor_id) -> dict:
    """Approved administrative message: a portal thread (sender = the approving staff member), then the portal notification
    goes through notifications.deliver so the patient's channel preferences and the daily patient cap apply."""
    from app.engine.notifications import deliver
    from app.models import MessageThread, SecureMessage

    p = db.get(Patient, uuid.UUID(req.payload["patient_id"]))
    if not p or p.organization_id != req.organization_id:
        raise ValueError("patient not found")
    th = MessageThread(organization_id=req.organization_id, patient_id=p.id, subject=req.payload["subject"][:200], category="general",
                       assigned_provider_id=p.primary_provider_id, patient_unread=1, last_message_at=now())
    db.add(th)
    db.flush()
    db.add(SecureMessage(organization_id=req.organization_id, thread_id=th.id, sender_id=actor_id, sender_is_patient=False, body=req.payload["body"]))
    case = db.get(Case, req.case_id) if req.case_id else None
    d = deliver(db, req.organization_id, channel="portal", dedupe=f"approval:{req.id}:portal", subject="New message from your care team",
                body=req.payload["subject"][:200], category="general", link=f"/portal/messages/{th.id}", case=case, patient_id=p.id)
    return {"thread_id": str(th.id), "notification": d.status if d else "already_sent", "notification_reason": d.status_reason if d else None}


@AP.executor("inventory.adjust_purchase_request")
def _exec_pr_qty(db, req, actor_id) -> dict:
    """Change the quantity of a still-submitted purchase request (bounded at proposal time; re-checked here). Approving
    the purchase itself remains a separate procurement decision."""
    from app.models import PurchaseRequest

    pr = db.get(PurchaseRequest, uuid.UUID(req.payload["purchase_request_id"]))
    q = int(req.payload["quantity"])
    if not pr or pr.organization_id != req.organization_id:
        raise ValueError("purchase request not found")
    if pr.status != "submitted":
        raise ValueError(f"purchase request is already {pr.status}")
    if not 1 <= q <= 100000:
        raise ValueError("quantity out of range")
    old, pr.quantity = pr.quantity, q
    return {"purchase_request_id": str(pr.id), "from": old, "to": q}


@AP.executor("insurance.request_update")
def _exec_ins_update(db, req, actor_id) -> dict:
    """Ask the patient (portal) to confirm/update insurance. Idempotent: reuses an open request."""
    from app.monitors.insurance import ensure_update_request

    case = db.get(Case, uuid.UUID(req.payload["case_id"]))
    if not case or case.organization_id != req.organization_id or not case.patient_id:
        raise ValueError("case not found")
    appt = (case.data or {}).get("appointment_id")
    r = ensure_update_request(db, case, case.patient_id, req.payload.get("reason") or "Please confirm your insurance before your visit.",
                              uuid.UUID(appt) if appt else None)
    return {"coverage_update_request_id": str(r.id), "status": r.status}


def openai_tool_specs(names: list[str]) -> list[dict]:
    from app.ai.openai_provider import strict_schema

    return [{"type": "function", "name": t.name, "description": t.description, "parameters": strict_schema(t.params), "strict": True}
            for n in names if (t := REGISTRY.get(n))]


def execute(ctx, agent_key: str, allowed: list[str], name: str, args: dict[str, Any]) -> dict:
    """Server-side gate for every tool call: allow-list → user permission → argument validation → run."""
    t = REGISTRY.get(name)
    if not t or name not in allowed:
        return {"error": f"tool '{name}' is not allowed for this agent"}
    if not ctx.can(t.permission):
        return {"error": f"permission denied: you lack {t.permission}"}
    try:
        parsed = t.params.model_validate(args or {})
    except Exception as e:  # noqa: BLE001
        return {"error": f"invalid arguments: {str(e)[:200]}"}
    try:
        return t.fn(ctx, parsed, agent=agent_key) if t.kind == "propose" else t.fn(ctx, parsed)
    except Exception as e:  # noqa: BLE001
        return {"error": f"tool failed: {type(e).__name__}"}
