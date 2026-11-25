"""Backend-defined agent tools. Agents never get database access: each tool validates its arguments (Pydantic), checks the
*invoking user's* permission (and facility/patient access through the usual helpers), and returns minimal data.

Kinds:
  read     — returns data the user could already see in the application (facility- and patient-scoped).
  propose  — creates an ApprovalRequest; a DIFFERENT authorized person approves, then a registered executor acts.
             The requesting user, facility, conversation and agent run are recorded (separation of duties is enforced
             in engine/approvals.decide — the requester can never approve, whatever workspace they switch to).
  prepare  — creates a confirm-in-chat draft (HMS Assist conversations only); it executes only when the same user
             confirms, through the existing service and under that user's own permissions.

Record binding ("pins"): in a conversation bound to a record, a tool argument that names a record (case ref, patient,
stay, claim, item, thread, document, scribe session) is filled from the binding and may not name a different record —
text inside records or tool results can't steer the agent to other patients or cases.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.core.permissions import P, Role
from app.core.security import now
from app.engine import approvals as AP
from app.models import Case, Claim, ClaimFinding, InpatientStay, InventoryItem, Patient

# Roles a task may be assigned to (the role registry minus the platform owner and patients). Never created on the fly.
ASSIGNABLE_ROLES = {r.value for r in Role} - {Role.SUPER_ADMIN.value, Role.PATIENT.value}
# Narrower per-agent task-role allow-lists (an agent can only route work inside its department's reach).
AGENT_TASK_ROLES: dict[str, set[str]] = {
    "insurance_guardian": {"insurance_specialist", "receptionist", "billing"},
    "pharmacy_watchdog": {"pharmacist", "hospital_admin"},
    "discharge_coordination": {"nurse", "bed_manager", "doctor", "pharmacist", "clinic_admin"},
    "claims_review": {"billing", "insurance_specialist"},
    "staff_scheduling": {"hospital_admin", "clinic_admin"},
    "document_intelligence": {"receptionist", "nurse", "doctor", "clinic_admin", "insurance_specialist"},
}


@dataclass
class Scope:
    """Who/what a tool call runs for. `bound` holds the conversation's record binding (see module docstring)."""
    agent: str
    conversation_id: uuid.UUID | None = None
    agent_run_id: uuid.UUID | None = None
    facility_id: uuid.UUID | None = None
    bound: dict = field(default_factory=dict)


@dataclass
class Tool:
    name: str
    description: str
    params: type[BaseModel]
    permission: str
    kind: str  # read | propose | prepare
    fn: Callable[..., dict]
    pins: dict[str, str]


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, params: type[BaseModel], permission: str, kind: str = "read", pins: dict | None = None):
    def deco(fn):
        REGISTRY[name] = Tool(name, description, params, permission, kind, fn, pins or {})
        return fn

    return deco


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown arguments are rejected, never ignored


class _None(_Args):
    pass


def _fac_ok(ctx, facility_id) -> bool:
    ids = getattr(ctx, "facility_ids", None)
    return facility_id is None or ids is None or facility_id in ids


def _norm(v) -> str:
    s = str(v or "").strip().upper()
    return s[1:] if s.startswith("C") and s[1:].isdigit() else s


# ---------------------------------------------------------------------------------------------- cases

class _Cases(_Args):
    category: str | None = Field(default=None, description="insurance, pharmacy, inventory, lab, bed, ed, discharge, billing, staffing, equipment …")
    limit: int = Field(default=10, ge=1, le=25)


def _case_brief(c: Case) -> dict:
    return {"ref": f"C{c.number}", "title": c.title, "severity": c.severity, "status": c.status, "owner_role": c.assigned_role,
            "overdue": bool(c.due_at and c.due_at < now()), "category": c.category}


@tool("list_open_cases", "List open operational cases you can see (most severe first).", _Cases, P.CASES_READ)
def list_open_cases(ctx, a: _Cases, s: Scope) -> dict:
    from app.api.routers.operations import list_cases

    rows = list_cases(status="open", category=a.category, limit=a.limit, ctx=ctx)
    return {"cases": [{"ref": f"C{c.number}", "title": c.title, "severity": c.severity, "status": c.status, "owner_role": c.assigned_role,
                       "overdue": c.overdue, "category": c.category} for c in rows]}


class _CaseRef(_Args):
    ref: str | None = Field(default=None, description="Case reference such as C1042 (omit in a case conversation)")


def _find_case(ctx, ref: str | None) -> Case | None:
    num = _norm(ref)
    if not num.isdigit():
        return None
    from app.api.routers.operations import _visible

    return ctx.db.scalars(_visible(ctx, select(Case).where(Case.number == int(num)))).first()


@tool("get_case", "Get one case with its evidence, recent timeline and linked approvals.", _CaseRef, P.CASES_READ, pins={"ref": "case_ref"})
def get_case(ctx, a: _CaseRef, s: Scope) -> dict:
    c = _find_case(ctx, a.ref)
    if not c:
        return {"error": "case not found or not accessible"}
    from app.models import ApprovalRequest, CaseEvent

    ev = ctx.db.scalars(select(CaseEvent).where(CaseEvent.case_id == c.id).order_by(CaseEvent.at.desc()).limit(8)).all()
    ap = ctx.db.scalars(select(ApprovalRequest).where(ApprovalRequest.case_id == c.id).order_by(ApprovalRequest.created_at.desc()).limit(5)).all()
    return {**_case_brief(c), "summary": c.summary, "evidence": c.evidence, "detected_at": c.first_detected_at.isoformat() if c.first_detected_at else None,
            "patient_id": str(c.patient_id) if c.patient_id and ctx.can(P.PATIENTS_READ) else None,
            "recent_events": [{"at": e.at.isoformat(), "kind": e.kind, "message": e.message} for e in ev],
            "approvals": [{"id": str(x.id), "title": x.title, "status": x.status} for x in ap]}


class _Worklist(_Args):
    limit: int = Field(default=10, ge=1, le=15)


@tool("get_insurance_worklist", "Open insurance cases with each patient's current coverage state in ONE call.", _Worklist, P.CASES_READ)
def get_insurance_worklist(ctx, a: _Worklist, s: Scope) -> dict:
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


# ---------------------------------------------------------------------------------------------- patients / coverage

class _PatientRef(_Args):
    patient_id: str | None = Field(default=None, description="Patient id (omit in a patient- or case-bound conversation)")


def _patient(ctx, pid: str | None) -> Patient | None:
    from app.services.patients import get_patient

    try:
        return get_patient(ctx, uuid.UUID(str(pid)))
    except Exception:  # noqa: BLE001 — not found / forbidden / restricted → hidden from the agent
        return None


@tool("get_patient_coverage", "Insurance coverage state for a patient's next visit (payer-verified, not stored dates).", _PatientRef,
      P.PATIENTS_READ, pins={"patient_id": "patient_id"})
def get_patient_coverage(ctx, a: _PatientRef, s: Scope) -> dict:
    p = _patient(ctx, a.patient_id)
    if not p:
        return {"error": "patient not found or not accessible"}
    from app.services.insurance import coverage_state

    st = coverage_state(ctx.db, p.id, now().date())
    return {"state": st.state, "reason": st.reason, "payer": st.insurance.payer_name if st.insurance else None,
            "note": "Payer checks are simulated in this environment."}


@tool("get_eligibility_history", "The patient's most recent payer eligibility checks (result, payer message, trace). Simulated payer.",
      _PatientRef, P.PATIENTS_READ, pins={"patient_id": "patient_id"})
def get_eligibility_history(ctx, a: _PatientRef, s: Scope) -> dict:
    p = _patient(ctx, a.patient_id)
    if not p:
        return {"error": "patient not found or not accessible"}
    from app.models import EligibilityCheck

    rows = ctx.db.scalars(select(EligibilityCheck).where(EligibilityCheck.patient_id == p.id).order_by(EligibilityCheck.checked_at.desc()).limit(5)).all()
    return {"checks": [{"checked_at": r.checked_at.isoformat(), "result": r.result, "message": r.message, "source": r.source,
                        "trigger": r.trigger, "payer_trace": r.payer_trace, "date_of_service": r.date_of_service.isoformat(),
                        "plan": r.plan_description} for r in rows],
            "note": "Eligibility responses come from a SIMULATED payer gateway, not a live payer."}


@tool("get_coverage_requests", "Requests asking the patient to confirm/update insurance (status, reason, review outcome).", _PatientRef,
      P.PATIENTS_READ, pins={"patient_id": "patient_id"})
def get_coverage_requests(ctx, a: _PatientRef, s: Scope) -> dict:
    p = _patient(ctx, a.patient_id)
    if not p:
        return {"error": "patient not found or not accessible"}
    from app.models import CoverageUpdateRequest

    rows = ctx.db.scalars(select(CoverageUpdateRequest).where(CoverageUpdateRequest.patient_id == p.id)
                          .order_by(CoverageUpdateRequest.created_at.desc()).limit(5)).all()
    return {"requests": [{"status": r.status, "reason": r.reason, "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                          "review_note": r.review_note} for r in rows]}


# ---------------------------------------------------------------------------------------------- inpatient

class _StayRef(_Args):
    stay_id: str | None = Field(default=None, description="Inpatient stay id (omit in a stay-bound conversation)")


def _stay(ctx, sid) -> InpatientStay | None:
    try:
        s = ctx.db.get(InpatientStay, uuid.UUID(str(sid)))
    except (ValueError, TypeError):
        return None
    if not s or s.organization_id != ctx.org_id or not ctx.facility_allowed(s.facility_id) or not _patient(ctx, s.patient_id):
        return None
    return s


@tool("get_discharge_status", "Discharge checklist status (blocking items and owners) for an inpatient stay.", _StayRef, P.ADT_READ,
      pins={"stay_id": "stay_id"})
def get_discharge_status(ctx, a: _StayRef, s: Scope) -> dict:
    st = _stay(ctx, a.stay_id)
    if not st:
        return {"error": "stay not found or not accessible"}
    from app.services.discharge import readiness

    r = readiness(ctx.db, st)
    if not r:
        return {"status": st.status, "plan": None, "note": "No discharge plan has been started for this stay."}
    return {"status": st.status, "ready": r["ready"], "blocking": r["blocking"],
            "items": [{"label": i["label"], "status": i["status"], "owner": i["owner_role"]} for i in r["items"]]}


@tool("get_stay_summary", "Operational summary of an inpatient stay (status, level of care, length of stay, discharge order time, open "
      "tasks, medication orders awaiting pharmacy). No clinical notes.", _StayRef, P.ADT_READ, pins={"stay_id": "stay_id"})
def get_stay_summary(ctx, a: _StayRef, s: Scope) -> dict:
    st = _stay(ctx, a.stay_id)
    if not st:
        return {"error": "stay not found or not accessible"}
    from app.models import Order, Task

    tasks = ctx.db.scalars(select(Task).where(Task.organization_id == ctx.org_id, Task.patient_id == st.patient_id,
                                              Task.status.in_(("open", "in_progress"))).limit(10)).all()
    pending_rx = ctx.db.scalar(select(func.count()).select_from(Order).where(Order.patient_id == st.patient_id, Order.order_type == "medication",
                                                                             Order.status == "pending_verification")) or 0
    los = round((now() - st.admitted_at).total_seconds() / 3600, 1) if st.admitted_at else None
    return {"status": st.status, "level_of_care": st.level_of_care, "admitted_at": st.admitted_at.isoformat() if st.admitted_at else None,
            "length_of_stay_hours": los, "expected_discharge_date": st.expected_discharge_date.isoformat() if st.expected_discharge_date else None,
            "discharge_ordered_at": st.discharge_ordered_at.isoformat() if st.discharge_ordered_at else None,
            "open_tasks": [{"title": t.title, "role": t.assigned_role, "status": t.status} for t in tasks],
            "medication_orders_awaiting_pharmacy": pending_rx}


# ---------------------------------------------------------------------------------------------- inventory

class _Item(_Args):
    item_id: str | None = Field(default=None, description="Inventory item id (preferred)")
    name: str | None = Field(default=None, max_length=80, description="Item name if the id is unknown")


def _item(ctx, a: _Item) -> InventoryItem | None:
    if a.item_id:
        try:
            it = ctx.db.get(InventoryItem, uuid.UUID(str(a.item_id)))
        except (ValueError, TypeError):
            return None
        return it if it and it.organization_id == ctx.org_id else None
    if a.name:
        return ctx.db.scalar(select(InventoryItem).where(InventoryItem.organization_id == ctx.org_id,
                                                         func.lower(InventoryItem.name).like(f"%{a.name.lower()[:60]}%")).limit(1))
    return None


def _scoped_on_hand(ctx, item_id) -> int:
    from app.services.inventory import on_hand

    if ctx.facility_ids is None:
        return on_hand(ctx.db, item_id)
    return sum(on_hand(ctx.db, item_id, f) for f in ctx.facility_ids)


@tool("get_inventory_item", "Stock on hand (in your facilities), consumption and reorder recommendation for an inventory item.", _Item,
      P.INVENTORY_READ, pins={"item_id": "item_id"})
def get_inventory_item(ctx, a: _Item, s: Scope) -> dict:
    it = _item(ctx, a)
    if not it:
        return {"error": "item not found"}
    from app.models import Supplier
    from app.services.inventory import avg_daily_use

    oh = _scoped_on_hand(ctx, it.id)
    use = avg_daily_use(ctx.db, it.id)
    sup = ctx.db.get(Supplier, it.preferred_supplier_id) if it.preferred_supplier_id else None
    lead = sup.lead_time_days if sup else 3
    qty = max(it.reorder_qty, math.ceil(use * (lead + 14)) - oh, 1)
    return {"item_id": str(it.id), "item": it.name, "unit": it.unit, "reorder_point": it.reorder_point, "on_hand": oh,
            "avg_daily_use": round(use, 2), "days_of_supply": round(oh / use, 1) if use else None, "lead_time_days": lead,
            "recommended_qty": qty, "scope": "your facilities" if ctx.facility_ids is not None else "all facilities",
            "method": "28-day moving average × (lead time + 14 days) − on hand; floor = reorder quantity"}


@tool("get_purchase_requests", "Recent purchase requests for an item in your facilities (number, quantity, status).", _Item,
      P.INVENTORY_READ, pins={"item_id": "item_id"})
def get_purchase_requests(ctx, a: _Item, s: Scope) -> dict:
    it = _item(ctx, a)
    if not it:
        return {"error": "item not found"}
    from app.models import PurchaseRequest

    q = select(PurchaseRequest).where(PurchaseRequest.organization_id == ctx.org_id, PurchaseRequest.item_id == it.id)
    if ctx.facility_ids is not None:
        q = q.where(PurchaseRequest.facility_id.in_(ctx.facility_ids))
    rows = ctx.db.scalars(q.order_by(PurchaseRequest.created_at.desc()).limit(5)).all()
    return {"purchase_requests": [{"number": r.number, "quantity": r.quantity, "status": r.status, "source": r.source,
                                   "created_at": r.created_at.isoformat()} for r in rows]}


# ---------------------------------------------------------------------------------------------- claims

class _Claim(_Args):
    claim_number: str | None = Field(default=None, description="Claim number (omit in a claim-bound conversation)")


def _claim(ctx, number) -> Claim | None:
    if not number:
        return None
    c = ctx.db.scalar(select(Claim).where(Claim.organization_id == ctx.org_id, Claim.claim_number == str(number)))
    if not c:
        return None
    from app.models import Encounter

    enc = ctx.db.get(Encounter, c.encounter_id) if c.encounter_id else None
    if (enc and not ctx.facility_allowed(enc.clinic_id)) or not _patient(ctx, c.patient_id):
        return None
    return c


@tool("get_claim_findings", "Open review findings and scrub errors for a claim (advisory).", _Claim, P.BILLING_READ,
      pins={"claim_number": "claim_number"})
def get_claim_findings(ctx, a: _Claim, s: Scope) -> dict:
    c = _claim(ctx, a.claim_number)
    if not c:
        return {"error": "claim not found or not accessible"}
    f = ctx.db.scalars(select(ClaimFinding).where(ClaimFinding.claim_id == c.id, ClaimFinding.status == "open")).all()
    return {"status": c.status, "scrub_errors": c.scrub_errors, "findings": [{"severity": x.severity, "message": x.message} for x in f]}


@tool("get_claim_summary", "Claim status, payer, service date, amounts, scrub errors, denial code/reason and submission count.", _Claim,
      P.BILLING_READ, pins={"claim_number": "claim_number"})
def get_claim_summary(ctx, a: _Claim, s: Scope) -> dict:
    c = _claim(ctx, a.claim_number)
    if not c:
        return {"error": "claim not found or not accessible"}
    open_f = ctx.db.scalar(select(func.count()).select_from(ClaimFinding).where(ClaimFinding.claim_id == c.id, ClaimFinding.status == "open")) or 0
    return {"claim_number": c.claim_number, "status": c.status, "payer": c.payer_name, "service_date": c.service_date.isoformat(),
            "total_charge": round(c.total_charge_cents / 100, 2), "paid": round(c.paid_cents / 100, 2), "scrub_errors": c.scrub_errors,
            "denial_code": c.denial_code, "denial_reason": c.denial_reason, "submission_count": c.submission_count, "open_findings": open_f,
            "note": "Clearinghouse and payer adjudication are simulated in this environment."}


# ---------------------------------------------------------------------------------------------- staffing / operations

def _gaps(ctx) -> list[dict]:
    from app.services.rostering import gaps

    return [g for g in gaps(ctx.db, ctx.org_id) if _fac_ok(ctx, g["facility_id"]) and ctx.department_allowed(g["department_id"])]


@tool("get_staffing_gaps", "Departments (in your facilities) below minimum staffing in the next 48 hours.", _None, P.ROSTER_MANAGE)
def get_staffing_gaps(ctx, a: _None, s: Scope) -> dict:
    return {"gaps": [{"department_id": str(g["department_id"]), "department": g["department"], "role": g["role"], "window": g["window"],
                      "start": g["start"].isoformat(), "short": g["short"]} for g in _gaps(ctx)]}


class _Cover(_Args):
    department_id: str
    role: str
    start: str = Field(description="Gap start exactly as returned by get_staffing_gaps")


@tool("get_cover_candidates", "Eligible staff for one staffing gap (hard rules: role, overlap, time off, rest, weekly hours, credentials), "
      "ranked by fewest hours. Managers decide; nothing is changed.", _Cover, P.ROSTER_MANAGE)
def get_cover_candidates(ctx, a: _Cover, s: Scope) -> dict:
    from app.models import Department
    from app.services.rostering import suggest

    g = next((x for x in _gaps(ctx) if str(x["department_id"]) == a.department_id and x["role"] == a.role and x["start"].isoformat() == a.start), None)
    if not g:
        return {"error": "no such staffing gap in your facilities (use get_staffing_gaps first)"}
    dept = ctx.db.get(Department, g["department_id"])
    c = suggest(ctx.db, ctx.org_id, dept, a.role, g["start"], g["end"])
    return {"gap": {"department": g["department"], "role": a.role, "window": g["window"], "short": g["short"]},
            "candidates": [{"name": x["name"], "reasons": x["reasons"]} for x in c],
            "method": "hard-rule filter then fewest hours this week; a manager assigns shifts in the roster"}


@tool("get_operations_summary", "Hospital operations numbers (beds, ED, discharges, alerts) with their sources.", _None, P.COMMAND_CENTER)
def get_operations_summary(ctx, a: _None, s: Scope) -> dict:
    from app.api.routers.command import hospital_section

    h = hospital_section(ctx, ctx.facility_ids)
    return {"tiles": [{"metric": t["label"], "value": t["value"], "detail": t["sub"], "source": t["source"]} for t in h.get("tiles", [])]}


@tool("get_recent_volume", "Counts of admissions, discharges and ED arrivals over the last 7 days (your facilities).", _None, P.ADT_READ)
def get_recent_volume(ctx, a: _None, s: Scope) -> dict:
    from app.models import EdVisit

    since = now() - timedelta(days=7)

    def cnt(model, col):
        q = select(func.count()).select_from(model).where(model.organization_id == ctx.org_id, col > since)
        if ctx.facility_ids is not None:
            q = q.where(model.facility_id.in_(ctx.facility_ids))
        return ctx.db.scalar(q)

    return {"window_days": 7, "admissions": cnt(InpatientStay, InpatientStay.admitted_at),
            "discharges": cnt(InpatientStay, InpatientStay.discharged_at), "ed_arrivals": cnt(EdVisit, EdVisit.arrival_at)}


# ---------------------------------------------------------------------------------------------- messages / scribe / documents

class _Thread(_Args):
    thread_id: str | None = Field(default=None, description="Message thread id (omit in a thread-bound conversation)")


def _thread(ctx, tid):
    from app.models import MessageThread

    try:
        t = ctx.db.get(MessageThread, uuid.UUID(str(tid)))
    except (ValueError, TypeError):
        return None
    if not t or t.organization_id != ctx.org_id or not _patient(ctx, t.patient_id):
        return None
    return t


@tool("get_message_thread", "Subject, status and the most recent messages of one patient message thread.", _Thread, P.MESSAGES,
      pins={"thread_id": "thread_id"})
def get_message_thread(ctx, a: _Thread, s: Scope) -> dict:
    t = _thread(ctx, a.thread_id)
    if not t:
        return {"error": "thread not found or not accessible"}
    from app.models import SecureMessage

    msgs = ctx.db.scalars(select(SecureMessage).where(SecureMessage.thread_id == t.id).order_by(SecureMessage.created_at.desc()).limit(8)).all()
    return {"subject": t.subject, "status": t.status, "category": t.category, "patient_id": str(t.patient_id),
            "messages": [{"from": "patient" if m.sender_is_patient else "staff", "at": m.created_at.isoformat(), "text": m.body[:600]}
                         for m in reversed(msgs)]}


class _Scribe(_Args):
    session_id: str | None = Field(default=None, description="Scribe session id (omit in a scribe-bound conversation)")


def _scribe(ctx, sid):
    from app.models import Encounter, ScribeSession
    from app.services.patients import get_patient

    try:
        ss = ctx.db.get(ScribeSession, uuid.UUID(str(sid)))
    except (ValueError, TypeError):
        return None
    if not ss or ss.organization_id != ctx.org_id:
        return None
    enc = ctx.db.get(Encounter, ss.encounter_id)
    try:
        get_patient(ctx, ss.patient_id, P.CLINICAL_WRITE)
    except Exception:  # noqa: BLE001
        return None
    if not enc or not ctx.clinic_allowed(enc.clinic_id):
        return None
    return ss


@tool("get_scribe_session", "The consented visit transcript (numbered segments) and the current SOAP draft of a scribe session.", _Scribe,
      P.CLINICAL_WRITE, pins={"session_id": "scribe_session_id"})
def get_scribe_session(ctx, a: _Scribe, s: Scope) -> dict:
    ss = _scribe(ctx, a.session_id)
    if not ss:
        return {"error": "scribe session not found or not accessible"}
    segs = [{"n": i + 1, "speaker": x.get("speaker"), "text": (x.get("text") or "")[:400]} for i, x in enumerate((ss.transcript or [])[:120])]
    d = ss.draft or {}
    return {"status": ss.status, "consent": ss.consent_method, "transcript": segs,
            "draft": {k: d.get(k) for k in ("subjective", "objective", "assessment", "plan") if k in d}, "draft_provider": d.get("provider")}


class _Doc(_Args):
    document_id: str | None = Field(default=None, description="Document id (omit in a document-bound conversation)")


def _document(ctx, did):
    from app.models import Document

    try:
        d = ctx.db.get(Document, uuid.UUID(str(did)))
    except (ValueError, TypeError):
        return None
    if not d or d.organization_id != ctx.org_id or not ctx.clinic_allowed(d.clinic_id):
        return None
    if d.patient_id and not _patient(ctx, d.patient_id):
        return None
    return d


@tool("get_document_review", "Classification, summary, extracted identifiers/findings, uncertainties and patient-match candidates of one "
      "document in the review queue.", _Doc, P.DOCUMENTS_REVIEW, pins={"document_id": "document_id"})
def get_document_review(ctx, a: _Doc, s: Scope) -> dict:
    d = _document(ctx, a.document_id)
    if not d:
        return {"error": "document not found or not accessible"}
    ai = d.ai_output or {}
    return {"status": d.status, "doc_type": d.doc_type, "title": d.title, "summary": d.summary, "confidence": d.ai_confidence,
            "document_date": d.document_date.isoformat() if d.document_date else None, "sender": d.sender,
            "identifiers_on_document": ai.get("patient"), "key_findings": (ai.get("key_findings") or [])[:15],
            "uncertainties": ai.get("uncertainties") or [], "processing_error": d.processing_error,
            "match_candidates": [{k: c.get(k) for k in ("name", "mrn", "date_of_birth", "score", "reasons")} for c in (d.match_candidates or [])[:5]],
            "note": "Extraction is a draft. Staff confirm identity and details before anything is filed."}


# ---------------------------------------------------------------------------------------------- proposal status

class _Prop(_Args):
    approval_id: str | None = Field(default=None, description="Omit to list this conversation's proposals")


@tool("get_proposal_status", "Current status of proposals made in this conversation (or by you): pending, executed, rejected (with "
      "reason) or failed, and the resulting task/record.", _Prop, P.AI_USE)
def get_proposal_status(ctx, a: _Prop, s: Scope) -> dict:
    from app.models import ApprovalRequest

    q = select(ApprovalRequest).where(ApprovalRequest.organization_id == ctx.org_id)
    if s.conversation_id:
        q = q.where(ApprovalRequest.conversation_id == s.conversation_id)
    else:
        q = q.where(ApprovalRequest.requested_by_user_id == ctx.user.id)
    if a.approval_id:
        try:
            q = q.where(ApprovalRequest.id == uuid.UUID(a.approval_id))
        except ValueError:
            return {"error": "invalid approval id"}
    rows = ctx.db.scalars(q.order_by(ApprovalRequest.created_at.desc()).limit(10)).all()
    return {"proposals": [{"approval_id": str(r.id), "title": r.title, "status": r.status, "decision_note": r.decision_note,
                           "result": r.result or {}, "error": r.error} for r in rows]}


# ---------------------------------------------------------------------------------------------- proposals (approval required)

def _request(ctx, s: Scope, *, kind: str, title: str, payload: dict, required_permission: str, summary: str | None = None,
             case: Case | None = None, patient_id=None, dedupe: str | None = None) -> dict:
    """Create (or return the already-pending) approval request with full provenance."""
    from app.models import ApprovalRequest

    key = f"{kind}:{dedupe}"[:200] if dedupe else None
    if key:
        prior = ctx.db.scalar(select(ApprovalRequest).where(ApprovalRequest.organization_id == ctx.org_id, ApprovalRequest.dedupe_key == key,
                                                            ApprovalRequest.status == "pending"))
        if prior:
            return {"proposal": "already pending approval", "approval_id": str(prior.id), "status": "pending", "duplicate": True}
    req = AP.request_approval(ctx.db, ctx.org_id, kind=kind, title=title, summary=summary, payload=payload,
                              required_permission=required_permission, case=case, patient_id=patient_id,
                              facility_id=(case.facility_id if case and case.facility_id else s.facility_id),
                              requested_by_user_id=getattr(ctx.user, "id", None), requested_by_agent=s.agent,
                              conversation_id=s.conversation_id, agent_run_id=s.agent_run_id, dedupe_key=key)
    return {"proposal": "pending approval", "approval_id": str(req.id), "status": "pending",
            "note": "Waiting for a different authorized person to approve in My Work. Nothing has been done yet."}


class _ProposeTask(_Args):
    title: str = Field(min_length=3, max_length=200)
    role: str = Field(description="Role to assign, e.g. nurse, pharmacist, insurance_specialist")
    case_ref: str | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")


def validate_role(agent: str | None, role: str) -> str | None:
    """None if `role` may receive a task proposed by `agent`, else the reason."""
    if role not in ASSIGNABLE_ROLES:
        return f"'{role}' is not a valid staff role"
    allowed = AGENT_TASK_ROLES.get(agent or "")
    if allowed and role not in allowed:
        return f"this assistant can route tasks only to: {', '.join(sorted(allowed))}"
    return None


@tool("propose_task", "Propose a staff task (a different authorized person must approve before it is created).", _ProposeTask, P.CASES_WORK,
      kind="propose", pins={"case_ref": "case_ref"})
def propose_task(ctx, a: _ProposeTask, s: Scope) -> dict:
    why = validate_role(s.agent, a.role)
    if why:
        return {"error": why}
    case = _find_case(ctx, a.case_ref) if a.case_ref else None
    if a.case_ref and not case:
        return {"error": "case not found or not accessible"}
    anchor = str(case.id) if case else str(s.conversation_id or getattr(ctx.user, "id", ""))
    return _request(ctx, s, kind="agent.create_task", title=f"Task proposal: {a.title}", summary=f"Assign to {a.role.replace('_', ' ')}",
                    payload={"title": a.title, "role": a.role, "priority": a.priority, "case_id": str(case.id) if case else None},
                    required_permission=P.CASES_WORK, case=case, dedupe=f"{anchor}:{a.role}:{a.title.strip().lower()[:80]}")


class _ProposeMsg(_Args):
    patient_id: str | None = None
    subject: str = Field(min_length=3, max_length=150)
    body: str = Field(min_length=10, max_length=1500)
    thread_id: str | None = Field(default=None, description="Reply in this existing thread instead of starting a new one")


@tool("propose_patient_message", "Draft a routine administrative portal message to a patient (a staff member approves and it is then "
      "posted). No clinical advice.", _ProposeMsg, P.MESSAGES, kind="propose", pins={"patient_id": "patient_id", "thread_id": "thread_id"})
def propose_patient_message(ctx, a: _ProposeMsg, s: Scope) -> dict:
    t = _thread(ctx, a.thread_id) if a.thread_id else None
    if a.thread_id and not t:
        return {"error": "thread not found or not accessible"}
    p = _patient(ctx, a.patient_id or (t.patient_id if t else None))
    if not p or (t and t.patient_id != p.id):
        return {"error": "patient not found or not accessible"}
    case = _find_case(ctx, s.bound.get("case_ref")) if s.bound.get("case_ref") else None
    # No patient name in the title: approval lists are seen by every approver with the permission.
    return _request(ctx, s, kind="agent.patient_message", title=f"Patient message proposal — {a.subject}", summary=a.body,
                    payload={"patient_id": str(p.id), "subject": a.subject, "body": a.body, "thread_id": str(t.id) if t else None},
                    required_permission=P.MESSAGES, patient_id=p.id, case=case, dedupe=f"{p.id}:{a.subject.strip().lower()[:80]}")


class _InsUpdate(_Args):
    case_ref: str | None = None
    reason: str = Field(min_length=5, max_length=300, description="Plain administrative reason shown to the patient")


@tool("propose_insurance_update", "Propose asking the patient (portal) to confirm or update their insurance for this case. An insurance "
      "staff member approves; an open request is reused.", _InsUpdate, P.CASES_READ, kind="propose", pins={"case_ref": "case_ref"})
def propose_insurance_update(ctx, a: _InsUpdate, s: Scope) -> dict:
    case = _find_case(ctx, a.case_ref)
    if not case or not case.patient_id:
        return {"error": "insurance case with a patient not found"}
    return _request(ctx, s, kind="insurance.request_update", title=f"Insurance update request — C{case.number}", summary=a.reason,
                    payload={"case_id": str(case.id), "reason": a.reason}, required_permission=P.INSURANCE_WRITE, case=case,
                    dedupe=f"{case.id}")


class _PrQty(_Args):
    purchase_request_number: int
    quantity: int = Field(ge=1, le=100000)


@tool("propose_purchase_quantity", "Propose changing the quantity of a still-submitted purchase request (50–200% of the recommendation). "
      "A procurement approver decides.", _PrQty, P.INVENTORY_READ, kind="propose")
def propose_purchase_quantity(ctx, a: _PrQty, s: Scope) -> dict:
    from app.models import PurchaseRequest

    pr = ctx.db.scalar(select(PurchaseRequest).where(PurchaseRequest.organization_id == ctx.org_id, PurchaseRequest.number == a.purchase_request_number))
    if not pr or not _fac_ok(ctx, pr.facility_id):
        return {"error": "purchase request not found or not accessible"}
    if pr.status != "submitted":
        return {"error": f"purchase request is already {pr.status}"}
    rec = int((pr.recommendation or {}).get("recommended_qty") or 0)
    if not rec:
        from app.services.inventory import recommend_reorder

        rec = int(recommend_reorder(ctx.db, ctx.db.get(InventoryItem, pr.item_id))["recommended_qty"])
    if not (rec * 0.5 <= a.quantity <= rec * 2) or a.quantity == pr.quantity:
        return {"error": f"quantity must differ from {pr.quantity} and lie between {math.ceil(rec * 0.5)} and {rec * 2}"}
    case = ctx.db.get(Case, pr.case_id) if pr.case_id else None
    return _request(ctx, s, kind="inventory.adjust_purchase_request", title=f"Change purchase request #{pr.number} to {a.quantity}",
                    summary=f"From {pr.quantity}; recommendation {rec}",
                    payload={"purchase_request_id": str(pr.id), "quantity": a.quantity, "from": pr.quantity},
                    required_permission=P.PROCUREMENT_APPROVE, case=case, dedupe=f"{pr.id}:{a.quantity}")


# ---------------------------------------------------------------------------------------------- prepare (confirm in chat)

def _draft(ctx, s: Scope, *, kind: str, title: str, payload: dict, required_permission: str) -> dict:
    if not s.conversation_id:
        return {"error": "confirm-in-chat actions are only available inside an HMS Assist conversation"}
    from app.models import AssistActionDraft

    d = AssistActionDraft(organization_id=ctx.org_id, conversation_id=s.conversation_id, kind=kind, title=title[:250], payload=payload,
                          required_permission=required_permission, created_by_agent=s.agent, expires_at=now() + timedelta(hours=24))
    ctx.db.add(d)
    ctx.db.flush()
    return {"draft_id": str(d.id), "status": "awaiting_user_confirmation",
            "note": "Shown to the employee as a confirmation card. Nothing happens unless they press Confirm."}


class _CaseNote(_Args):
    case_ref: str | None = None
    note: str = Field(min_length=3, max_length=1000)


@tool("prepare_case_note", "Prepare a note for the case timeline; the employee confirms it.", _CaseNote, P.CASES_WORK, kind="prepare",
      pins={"case_ref": "case_ref"})
def prepare_case_note(ctx, a: _CaseNote, s: Scope) -> dict:
    case = _find_case(ctx, a.case_ref)
    if not case:
        return {"error": "case not found or not accessible"}
    return _draft(ctx, s, kind="case_note", title=f"Add note to case C{case.number}", payload={"case_id": str(case.id), "note": a.note},
                  required_permission=P.CASES_WORK)


@tool("prepare_eligibility_check", "Prepare a fresh (simulated) payer eligibility check for the patient's primary insurance; the employee "
      "confirms it.", _PatientRef, P.INSURANCE_WRITE, kind="prepare", pins={"patient_id": "patient_id"})
def prepare_eligibility_check(ctx, a: _PatientRef, s: Scope) -> dict:
    p = _patient(ctx, a.patient_id)
    if not p:
        return {"error": "patient not found or not accessible"}
    from app.services.insurance import primary_insurance

    ins = primary_insurance(ctx.db, p.id)
    if not ins:
        return {"error": "no active primary insurance on file to check"}
    return _draft(ctx, s, kind="eligibility_check", title=f"Re-check eligibility with {ins.payer_name} (simulated payer)",
                  payload={"patient_id": str(p.id), "insurance_id": str(ins.id)}, required_permission=P.INSURANCE_WRITE)


@tool("prepare_claim_rescrub", "Prepare a re-scrub of an unsubmitted, rejected or denied claim; the employee confirms it.", _Claim,
      P.BILLING_WRITE, kind="prepare", pins={"claim_number": "claim_number"})
def prepare_claim_rescrub(ctx, a: _Claim, s: Scope) -> dict:
    c = _claim(ctx, a.claim_number)
    if not c:
        return {"error": "claim not found or not accessible"}
    if c.status not in ("draft", "ready", "rejected", "denied"):
        return {"error": f"a {c.status} claim can't be re-scrubbed"}
    return _draft(ctx, s, kind="claim_rescrub", title=f"Re-scrub claim {c.claim_number}", payload={"claim_id": str(c.id)},
                  required_permission=P.BILLING_WRITE)


class _ScribeEdit(_Args):
    session_id: str | None = None
    section: str = Field(pattern="^(subjective|objective|assessment|plan)$")
    text: str = Field(min_length=1, max_length=6000)


@tool("prepare_scribe_edit", "Prepare a revision of ONE section of the scribe DRAFT (not the note); the clinician confirms. Applying the "
      "draft to the note and signing stay with the clinician.", _ScribeEdit, P.CLINICAL_WRITE, kind="prepare",
      pins={"session_id": "scribe_session_id"})
def prepare_scribe_edit(ctx, a: _ScribeEdit, s: Scope) -> dict:
    ss = _scribe(ctx, a.session_id)
    if not ss or ss.status != "ready":
        return {"error": "the scribe draft is not ready for edits"}
    return _draft(ctx, s, kind="scribe_edit", title=f"Revise the draft {a.section} section",
                  payload={"session_id": str(ss.id), "section": a.section, "text": a.text}, required_permission=P.CLINICAL_WRITE)


# ---------------------------------------------------------------------------------------------- executors (run on approval)

@AP.executor("agent.create_task")
def _exec_task(db, req, actor_id) -> dict:
    from app.engine.cases import add_task

    role = req.payload.get("role")
    if role not in ASSIGNABLE_ROLES:  # re-validated at execution, whatever was stored
        raise ValueError(f"'{role}' is not a valid staff role")
    case = db.get(Case, uuid.UUID(req.payload["case_id"])) if req.payload.get("case_id") else None
    t = add_task(db, case, org_id=req.organization_id, title=req.payload["title"], role=role, priority=req.payload["priority"],
                 kind="agent.task", source="automation", dedupe_key=f"approval:{req.id}")
    return {"task_id": str(t.id) if t else None}


@AP.executor("agent.patient_message")
def _exec_msg(db, req, actor_id) -> dict:
    """Approved administrative message: posted in the portal (sender = the approving staff member); the portal notification
    goes through notifications.deliver so the patient's channel preferences and the daily patient cap apply."""
    from app.engine.notifications import deliver
    from app.models import MessageThread, SecureMessage

    p = db.get(Patient, uuid.UUID(req.payload["patient_id"]))
    if not p or p.organization_id != req.organization_id:
        raise ValueError("patient not found")
    th = db.get(MessageThread, uuid.UUID(req.payload["thread_id"])) if req.payload.get("thread_id") else None
    if th and th.patient_id != p.id:
        raise ValueError("thread does not belong to the patient")
    if th is None:
        th = MessageThread(organization_id=req.organization_id, patient_id=p.id, subject=req.payload["subject"][:200], category="general",
                           assigned_provider_id=p.primary_provider_id, patient_unread=0, last_message_at=now())
        db.add(th)
        db.flush()
    th.patient_unread = (th.patient_unread or 0) + 1
    th.status, th.last_message_at = "open", now()
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
    return {"purchase_request_id": str(pr.id), "purchase_request_number": pr.number, "from": old, "to": q}


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


# ---------------------------------------------------------------------------------------------- gate

def openai_tool_specs(names: list[str], *, conversation: bool = False) -> list[dict]:
    from app.ai.openai_provider import strict_schema

    return [{"type": "function", "name": t.name, "description": t.description, "parameters": strict_schema(t.params), "strict": True}
            for n in names if (t := REGISTRY.get(n)) and (conversation or t.kind != "prepare")]


def execute(ctx, agent_key: str, allowed: list[str], name: str, args: dict[str, Any], scope: Scope | None = None) -> dict:
    """Server-side gate for every tool call: allow-list → user permission → argument validation → record binding → run."""
    s = scope or Scope(agent=agent_key)
    t = REGISTRY.get(name)
    if not t or name not in allowed:
        return {"error": f"tool '{name}' is not allowed for this agent"}
    if not ctx.can(t.permission):
        return {"error": f"permission denied: you lack {t.permission}"}
    try:
        parsed = t.params.model_validate(args or {})
    except Exception as e:  # noqa: BLE001
        return {"error": f"invalid arguments: {str(e)[:200]}"}
    for arg, key in t.pins.items():
        bound = s.bound.get(key)
        if not bound:
            continue
        val = getattr(parsed, arg, None)
        if val in (None, ""):
            setattr(parsed, arg, bound)
        elif _norm(val) != _norm(bound):
            return {"error": f"outside this conversation's record: {arg} must be the record this conversation is about"}
    try:
        return t.fn(ctx, parsed, s)
    except Exception as e:  # noqa: BLE001
        return {"error": f"tool failed: {type(e).__name__}"}
