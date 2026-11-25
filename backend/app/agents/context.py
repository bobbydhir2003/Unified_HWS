"""Server-side record context for HMS Assist conversations.

The browser sends only `{type, id}`. `resolve()` loads the real record through the SAME access helpers the application
uses (case visibility incl. facility/department/restricted filters, get_patient with restricted-chart/break-the-glass
rules, facility checks) on EVERY turn, and returns:
  * a short label for the UI,
  * minimal facts for the model (no free text the client supplied),
  * `bound` — record ids the tool layer pins tool arguments to (app/agents/tools.py).
Anything not found or not accessible raises ContextError, indistinguishable from "does not exist".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select

from app.core.permissions import P

# Which record types each assistant can be opened on ("workspace" = no specific record).
AGENT_CONTEXTS: dict[str, set[str]] = {
    "insurance_guardian": {"workspace", "case", "patient"},
    "pharmacy_watchdog": {"workspace", "case", "inventory_item"},
    "discharge_coordination": {"workspace", "case", "stay"},
    "hospital_operations": {"workspace", "case"},
    "claims_review": {"workspace", "case", "claim"},
    "patient_communication": {"workspace", "message_thread", "patient", "case"},
    "staff_scheduling": {"workspace", "case"},
    "doctor_assistant": {"patient"},
    "medical_scribe": {"scribe_session"},
    "document_intelligence": {"document"},
}


class ContextError(Exception):
    pass


@dataclass
class Bundle:
    type: str
    id: str | None
    label: str
    patient_id: uuid.UUID | None = None
    facility_id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None
    link: str | None = None
    bound: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)


def _uuid(v) -> uuid.UUID:
    try:
        return uuid.UUID(str(v))
    except (ValueError, TypeError):
        raise ContextError("not found") from None


def _patient(ctx, pid, perm=P.PATIENTS_READ):
    from app.services.patients import get_patient

    try:
        return get_patient(ctx, pid, perm)
    except Exception:  # noqa: BLE001 — forbidden / restricted / missing all look the same
        raise ContextError("not found") from None


def _short(p) -> str:
    return f"{p.first_name} {p.last_name[:1]}. ({p.mrn})"


def resolve(ctx, agent: str, ctype: str, cid: str | None) -> Bundle:
    if ctype not in AGENT_CONTEXTS.get(agent, set()):
        raise ContextError(f"this assistant can't be opened on a {ctype.replace('_', ' ')}")
    if ctype == "workspace":
        return Bundle("workspace", None, "Your workspace")
    if not cid:
        raise ContextError("a record is required")
    return {"case": _case, "patient": _patient_ctx, "stay": _stay, "claim": _claim, "inventory_item": _item,
            "message_thread": _thread, "scribe_session": _scribe, "document": _document}[ctype](ctx, cid, agent)


def _case(ctx, cid, agent) -> Bundle:
    from app.api.routers.operations import _visible
    from app.models import Case

    q = select(Case)
    s = str(cid).strip().upper()
    q = q.where(Case.number == int(s.lstrip("C"))) if s.lstrip("C").isdigit() else q.where(Case.id == _uuid(cid))
    c = ctx.db.scalars(_visible(ctx, q)).first()
    if not c or not ctx.can(P.CASES_READ):
        raise ContextError("not found")
    b = Bundle("case", str(c.id), f"Case C{c.number} — {c.title}"[:240], facility_id=c.facility_id, case_id=c.id, link=None,
               bound={"case_ref": f"C{c.number}"},
               facts={"case_ref": f"C{c.number}", "title": c.title, "category": c.category, "status": c.status, "severity": c.severity,
                      "owner_role": c.assigned_role})
    if c.patient_id and ctx.can(P.PATIENTS_READ):
        p = _patient(ctx, c.patient_id)
        b.patient_id = p.id
        b.bound["patient_id"] = str(p.id)
        b.facts["patient"] = _short(p)
    st, sid = c.subject_type, c.subject_id
    if st == "inventory_item" and sid:
        b.bound["item_id"] = sid
    elif (c.data or {}).get("item_id"):
        b.bound["item_id"] = c.data["item_id"]
    if st == "inpatient_stay" and sid:
        b.bound["stay_id"] = sid
    if st == "claim" and sid:
        from app.models import Claim

        cl = ctx.db.get(Claim, _uuid(sid))
        if cl and cl.organization_id == ctx.org_id:
            b.bound["claim_number"] = cl.claim_number
    return b


def _patient_ctx(ctx, cid, agent) -> Bundle:
    perm = P.CLINICAL_READ if agent == "doctor_assistant" else P.PATIENTS_READ
    p = _patient(ctx, _uuid(cid), perm)
    return Bundle("patient", str(p.id), f"Patient {_short(p)}", patient_id=p.id, link=f"/patients/{p.id}",
                  bound={"patient_id": str(p.id)}, facts={"patient": _short(p)})


def _stay(ctx, cid, agent) -> Bundle:
    from app.models import InpatientStay

    s = ctx.db.get(InpatientStay, _uuid(cid))
    if not s or s.organization_id != ctx.org_id or not ctx.facility_allowed(s.facility_id):
        raise ContextError("not found")
    p = _patient(ctx, s.patient_id)
    return Bundle("stay", str(s.id), f"Inpatient stay — {_short(p)} · {s.status.replace('_', ' ')}", patient_id=p.id,
                  facility_id=s.facility_id, link=f"/patients/{p.id}", bound={"stay_id": str(s.id), "patient_id": str(p.id)},
                  facts={"stay_status": s.status, "patient": _short(p), "level_of_care": s.level_of_care})


def _claim(ctx, cid, agent) -> Bundle:
    from app.agents.tools import _claim as find
    from app.models import Claim

    number = cid
    if "-" in str(cid) and len(str(cid)) == 36:
        c = ctx.db.get(Claim, _uuid(cid))
        number = c.claim_number if c and c.organization_id == ctx.org_id else None
    c = find(ctx, number)
    if not c:
        raise ContextError("not found")
    return Bundle("claim", str(c.id), f"Claim {c.claim_number} · {c.status}", patient_id=c.patient_id, link=f"/billing?claim={c.id}",
                  bound={"claim_number": c.claim_number, "patient_id": str(c.patient_id)},
                  facts={"claim_number": c.claim_number, "status": c.status, "payer": c.payer_name})


def _item(ctx, cid, agent) -> Bundle:
    from app.models import InventoryItem

    it = ctx.db.get(InventoryItem, _uuid(cid))
    if not it or it.organization_id != ctx.org_id or not ctx.can(P.INVENTORY_READ):
        raise ContextError("not found")
    return Bundle("inventory_item", str(it.id), f"Item — {it.name}", link=f"/pharmacy?item={it.id}", bound={"item_id": str(it.id)},
                  facts={"item": it.name, "unit": it.unit})


def _thread(ctx, cid, agent) -> Bundle:
    from app.agents.tools import _thread as find

    t = find(ctx, cid)
    if not t:
        raise ContextError("not found")
    p = _patient(ctx, t.patient_id)
    return Bundle("message_thread", str(t.id), f"Messages — {t.subject[:120]}", patient_id=p.id, link=f"/messages?thread={t.id}",
                  bound={"thread_id": str(t.id), "patient_id": str(p.id)}, facts={"subject": t.subject, "patient": _short(p)})


def _scribe(ctx, cid, agent) -> Bundle:
    from app.agents.tools import _scribe as find

    ss = find(ctx, cid)
    if not ss:
        raise ContextError("not found")
    from app.models import Encounter

    enc = ctx.db.get(Encounter, ss.encounter_id)
    return Bundle("scribe_session", str(ss.id), f"Scribe draft — visit {enc.started_at:%b %d}" if enc else "Scribe draft",
                  patient_id=ss.patient_id, facility_id=enc.clinic_id if enc else None, link=f"/encounters/{ss.encounter_id}",
                  bound={"scribe_session_id": str(ss.id), "patient_id": str(ss.patient_id)}, facts={"status": ss.status})


def _document(ctx, cid, agent) -> Bundle:
    from app.agents.tools import _document as find

    d = find(ctx, cid)
    if not d:
        raise ContextError("not found")
    b = Bundle("document", str(d.id), f"Document — {d.title or d.filename}"[:240], patient_id=d.patient_id, facility_id=d.clinic_id,
               link=f"/documents/{d.id}", bound={"document_id": str(d.id)}, facts={"status": d.status, "doc_type": d.doc_type})
    if d.patient_id:
        b.bound["patient_id"] = str(d.patient_id)
    return b
