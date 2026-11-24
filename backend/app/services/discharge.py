"""Discharge coordination (Milestone B5) — the closed loop from discharge order to departure.

Deterministic by design: readiness is computed from data, not from an LLM.
- `documentation` (auto): a signed discharge-summary note exists on the stay's inpatient encounter.
- `follow_up` (auto): a future appointment is booked for the patient after the discharge order.
- `instructions` (auto): clinician-approved patient instructions are on the plan.
- `med_rec`, `transport`, `equipment`, `education` (manual): the owning role marks them done (attested, audited) or N/A.
The Discharge Coordination agent's job is fan-out (one task per item to its owner), reminders via the engine, and an
optional AI *draft* of patient-friendly instructions that a clinician must approve before it is used.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import now
from app.engine.cases import add_task
from app.engine.events import handler
from app.models import (
    Appointment,
    ClinicalNote,
    DischargePlan,
    DischargePlanItem,
    DomainEvent,
    InpatientStay,
    Task,
)
from app.services import audit
from app.services.realtime import publish

ITEMS = [
    # key, label, owner role, verification, required
    ("documentation", "Discharge summary signed", "doctor", "auto", True),
    ("med_rec", "Medication reconciliation completed", "pharmacist", "manual", True),
    ("instructions", "Patient instructions approved by a clinician", "doctor", "auto", True),
    ("follow_up", "Follow-up appointment booked", "receptionist", "auto", True),
    ("transport", "Transportation arranged", "nurse", "manual", True),
    ("education", "Patient/caregiver education completed", "nurse", "manual", True),
    ("equipment", "Home equipment / services arranged", "nurse", "manual", False),
]


class DischargeError(ValueError):
    pass


def get_plan(db: Session, stay_id: uuid.UUID) -> DischargePlan | None:
    return db.scalar(select(DischargePlan).where(DischargePlan.stay_id == stay_id))


def ensure_plan(db: Session, stay: InpatientStay, *, actor_id: uuid.UUID | None = None) -> DischargePlan:
    plan = get_plan(db, stay.id)
    if plan:
        return plan
    plan = DischargePlan(organization_id=stay.organization_id, stay_id=stay.id)
    db.add(plan)
    db.flush()
    for i, (key, label, role, verification, required) in enumerate(ITEMS):
        db.add(DischargePlanItem(organization_id=stay.organization_id, plan_id=plan.id, key=key, label=label, owner_role=role,
                                 verification=verification, required=required, sort_order=i))
    db.flush()
    db.refresh(plan)
    audit.record(db, "discharge.plan_created", org_id=stay.organization_id, actor_id=actor_id, resource_type="inpatient_stay",
                 resource_id=stay.id, patient_id=stay.patient_id)
    return plan


def _auto_status(db: Session, stay: InpatientStay, plan: DischargePlan, key: str) -> tuple[bool, dict]:
    if key == "documentation":
        n = db.scalar(select(ClinicalNote).where(ClinicalNote.encounter_id == stay.encounter_id, ClinicalNote.note_type == "discharge_summary",
                                                 ClinicalNote.status == "signed").limit(1)) if stay.encounter_id else None
        return bool(n), ({"note_id": str(n.id), "signed_at": n.signed_at.isoformat() if getattr(n, "signed_at", None) else None} if n else {})
    if key == "follow_up":
        since = stay.discharge_ordered_at or stay.admitted_at or stay.requested_at
        a = db.scalar(select(Appointment).where(Appointment.patient_id == stay.patient_id, Appointment.start_at > now(),
                                                Appointment.created_at >= since, Appointment.status.in_(("scheduled", "confirmed")))
                      .order_by(Appointment.start_at).limit(1))
        return bool(a), ({"appointment_id": str(a.id), "at": a.start_at.isoformat()} if a else {})
    if key == "instructions":
        ok = bool(plan.instructions_text and plan.instructions_approved_at)
        return ok, ({"approved_at": plan.instructions_approved_at.isoformat()} if ok else {})
    return False, {}


def sync(db: Session, stay: InpatientStay, plan: DischargePlan) -> None:
    """Recompute auto items from data and close their tasks — the Verify step."""
    for it in plan.items:
        if it.verification != "auto" or it.status == "not_applicable":
            continue
        ok, ev = _auto_status(db, stay, plan, it.key)
        if ok and it.status != "done":
            it.status, it.evidence, it.completed_at = "done", ev, now()
            _close_task(db, it)
        elif not ok and it.status == "done":
            it.status, it.evidence, it.completed_at = "pending", {}, None


def _close_task(db: Session, it: DischargePlanItem, actor_id: uuid.UUID | None = None) -> None:
    if it.task_id:
        t = db.get(Task, it.task_id)
        if t and t.status in ("open", "in_progress"):
            t.status, t.completed_at, t.completed_by_id = "done", now(), actor_id


def readiness(db: Session, stay: InpatientStay) -> dict | None:
    plan = get_plan(db, stay.id)
    if plan is None:
        return None
    sync(db, stay, plan)
    blocking = [it.label for it in plan.items if it.required and it.status not in ("done", "not_applicable")]
    done = sum(1 for it in plan.items if it.status in ("done", "not_applicable"))
    return {"ready": not blocking, "blocking": blocking, "done": done, "total": len(plan.items),
            "items": [{"id": it.id, "key": it.key, "label": it.label, "required": it.required, "owner_role": it.owner_role,
                       "verification": it.verification, "status": it.status, "note": it.note, "evidence": it.evidence,
                       "task_id": it.task_id, "completed_at": it.completed_at} for it in plan.items],
            "instructions": {"text": plan.instructions_text, "source": plan.instructions_source, "approved_at": plan.instructions_approved_at},
            "plan_status": plan.status}


def fan_out(db: Session, stay: InpatientStay, plan: DischargePlan) -> int:
    """Create one task per open item for its owner (deduplicated)."""
    n = 0
    who = stay.patient.full_name
    for it in plan.items:
        if it.status in ("done", "not_applicable") or it.task_id:
            continue
        t = add_task(db, None, org_id=stay.organization_id, title=f"Discharge: {it.label.lower()} — {who}", role=it.owner_role,
                     dedupe_key=f"dc:{stay.id}:{it.key}", priority="high", kind=f"discharge.{it.key}", link=f"/inpatients/{stay.id}",
                     patient_id=stay.patient_id, department_id=stay.department_id, due_minutes=120)
        if t:
            it.task_id = t.id
            n += 1
    return n


def complete_item(db: Session, stay: InpatientStay, key: str, *, actor_id: uuid.UUID, status: str, note: str | None,
                  actor_roles: list[str]) -> DischargePlanItem:
    plan = get_plan(db, stay.id)
    if not plan:
        raise DischargeError("No discharge plan yet")
    it = next((x for x in plan.items if x.key == key), None)
    if not it:
        raise DischargeError("Unknown checklist item")
    if it.verification == "auto" and status == "done":
        raise DischargeError("This item completes automatically when the underlying record exists")
    if status == "not_applicable" and it.required and not (note and len(note.strip()) >= 5):
        raise DischargeError("Explain why a required item doesn't apply")
    if it.owner_role not in actor_roles and not {"doctor", "hospital_admin", "super_admin"} & set(actor_roles):
        raise DischargeError(f"Only the owning role ({it.owner_role.replace('_', ' ')}) or the attending team can complete this item")
    if key == "med_rec" and status == "done":
        # Closed loop: reconciliation can't be signed off while inpatient medication orders are still unresolved.
        from app.models import Order

        pending = db.scalars(select(Order.title).where(Order.patient_id == stay.patient_id, Order.order_type == "medication",
                                                       Order.status.in_(("pending_verification", "clarification_needed")))).all()
        if pending:
            raise DischargeError("Resolve medication orders still awaiting the pharmacist first: " + "; ".join(pending[:5]))
    it.status, it.note, it.completed_by_id, it.completed_at = status, note, actor_id, now() if status in ("done", "not_applicable") else None
    if status in ("done", "not_applicable"):
        _close_task(db, it, actor_id)
    audit.record(db, "discharge.item_updated", org_id=stay.organization_id, actor_id=actor_id, resource_type="inpatient_stay",
                 resource_id=stay.id, patient_id=stay.patient_id, details={"item": key, "status": status})
    publish(db, stay.organization_id, "discharge", stay_id=stay.id)
    return it


def draft_instructions(db: Session, stay: InpatientStay) -> tuple[str, str]:
    """Plain-language instructions DRAFT from the signed discharge summary + plan facts. Returns (text, source)."""
    from app.models import ClinicalNote

    note = db.scalar(select(ClinicalNote).where(ClinicalNote.encounter_id == stay.encounter_id, ClinicalNote.note_type == "discharge_summary",
                                                ClinicalNote.status == "signed").limit(1)) if stay.encounter_id else None
    content = (note.content if note else {}) or {}
    plan_text = content.get("plan") or "Follow the plan your care team reviewed with you."
    fu = _auto_status(db, stay, get_plan(db, stay.id), "follow_up")[1] if get_plan(db, stay.id) else {}
    when = f" on {datetime.fromisoformat(fu['at']):%A, %B %d}" if fu.get("at") else ""
    text = (f"You were in the hospital for: {stay.reason}.\n\n"
            f"What to do at home:\n{plan_text}\n\n"
            f"Follow-up: please keep your follow-up appointment{when}.\n\n"
            "Call your care team or return to the emergency department if you have trouble breathing, chest pain, a fever over "
            "101°F (38.3°C), confusion, or symptoms that get worse.")
    return text, "template_from_signed_summary"


@handler("discharge_coordinator", "adt.discharge_ordered", "adt.discharged", "adt.discharge_order_cancelled")
def on_discharge_event(db: Session, ev: DomainEvent) -> None:
    stay = db.get(InpatientStay, uuid.UUID(ev.subject_id)) if ev.subject_id else None
    if not stay:
        return
    if ev.event_type == "adt.discharge_ordered":
        plan = ensure_plan(db, stay)
        plan.status = "active"
        sync(db, stay, plan)
        fan_out(db, stay, plan)
    elif ev.event_type == "adt.discharged":
        plan = get_plan(db, stay.id)
        if plan:
            plan.status = "complete"
            for it in plan.items:
                if it.task_id:
                    t = db.get(Task, it.task_id)
                    if t and t.status in ("open", "in_progress"):
                        t.status, t.completed_at = "cancelled", now()
    elif ev.event_type == "adt.discharge_order_cancelled":
        plan = get_plan(db, stay.id)
        if plan:
            for it in plan.items:
                _close_task(db, it)
    publish(db, stay.organization_id, "discharge", stay_id=stay.id)
