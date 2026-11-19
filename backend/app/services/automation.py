"""Automation Studio engine.

Workflows are installed from templates. Each template declares exactly which actions it may take (`permissions`);
actions marked sensitive (anything that reaches a patient) wait in the approval queue when `requires_approval` is on.
Events are emitted from application code; runs execute inside a savepoint so a failing automation never breaks the
clinical action that triggered it.
"""

import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import now
from app.models import (
    AutomationRun,
    AutomationWorkflow,
    Membership,
    MembershipRole,
    MessageThread,
    Patient,
    ProviderProfile,
    SecureMessage,
    Task,
)
from app.services.notify import notify

log = logging.getLogger("undeclared.automation")

ACTIONS = {
    "create_task": {"label": "Create a staff task", "sensitive": False},
    "notify_staff": {"label": "Send an in-app notification to staff", "sensitive": False},
    "message_patient": {"label": "Send a secure portal message to the patient", "sensitive": True},
}

TEMPLATES: dict[str, dict[str, Any]] = {
    "no_show_outreach": {
        "name": "No-show outreach", "trigger": "appointment.no_show",
        "description": "When a patient no-shows, draft a friendly reschedule message and create a front-desk follow-up task.",
        "permissions": ["message_patient", "create_task"], "config": {"assign_role": "receptionist"},
    },
    "critical_result_escalation": {
        "name": "Abnormal result escalation", "trigger": "order.resulted",
        "description": "When lab results come back abnormal, create a task for the ordering clinician (urgent if any value is critical) and notify them.",
        "permissions": ["create_task", "notify_staff"], "config": {},
    },
    "document_routing": {
        "name": "Incoming document routing", "trigger": "document.needs_review",
        "description": "Route each incoming document to the right team's worklist based on its AI classification.",
        "permissions": ["create_task"], "config": {},
    },
    "message_triage": {
        "name": "Patient message triage", "trigger": "message.received",
        "description": "Classify new patient messages (urgent symptoms, refills, billing, scheduling) and route a task to the right role. Urgent messages also notify the patient's clinician.",
        "permissions": ["create_task", "notify_staff"], "config": {},
    },
    "depression_screen_followup": {
        "name": "Positive PHQ-2 follow-up", "trigger": "intake.submitted",
        "description": "When a pre-visit PHQ-2 score is 3 or more, ask the visit clinician to complete a PHQ-9.",
        "permissions": ["create_task"], "config": {"threshold": 3},
    },
    "follow_up_scheduling": {
        "name": "Follow-up scheduling", "trigger": "encounter.completed",
        "description": "When a visit is completed with a follow-up plan, create a front-desk task to schedule it.",
        "permissions": ["create_task"], "config": {"assign_role": "receptionist"},
    },
}

URGENT = re.compile(r"\b(chest pain|can'?t breathe|short(ness)? of breath|suicid|kill myself|overdose|stroke|fainted|passed out|severe bleeding|allergic reaction|swelling of (my )?(face|throat))\b", re.I)


def classify_message(text: str) -> tuple[str, str, str]:
    """Rule-based classifier → (category, urgency, role). Labeled as rule-based in the UI."""
    t = text.lower()
    if URGENT.search(t):
        return "urgent_symptoms", "urgent", "doctor"
    if re.search(r"\b(refill|prescription|pharmacy|ran out|out of my|medication)\b", t):
        return "medication", "normal", "nurse"
    if re.search(r"\b(bill|invoice|charge|payment|insurance|copay|statement)\b", t):
        return "billing", "normal", "billing"
    if re.search(r"\b(appointment|reschedule|cancel|book|schedule)\b", t):
        return "scheduling", "normal", "receptionist"
    if re.search(r"\b(result|lab|test)\b", t):
        return "results", "normal", "nurse"
    return "general", "normal", "nurse"


DOC_ROUTES = {"lab_result": "nurse", "imaging_report": "nurse", "discharge_summary": "nurse", "consult_note": "nurse",
              "prescription": "nurse", "referral": "receptionist", "insurance_card": "receptionist", "id_card": "receptionist",
              "intake_form": "receptionist", "correspondence": "clinic_admin", "other": "clinic_admin"}


def _plan(wf: AutomationWorkflow, p: dict, db: Session) -> list[dict]:
    """Return proposed actions for this event, or [] when the workflow doesn't apply."""
    k, cfg = wf.template_key, wf.config or {}
    pname = p.get("patient_name", "patient")
    if k == "no_show_outreach":
        return [
            {"type": "message_patient", "subject": "We missed you today",
             "body": f"Hi {p.get('patient_first_name', '')}, we missed you at your appointment on {p.get('when', 'today')}. "
                     "Reply here or book online in the portal to reschedule. — Your care team"},
            {"type": "create_task", "title": f"Reschedule no-show: {pname}", "role": cfg.get("assign_role", "receptionist"),
             "priority": "normal", "link": f"/patients/{p['patient_id']}/appointments"},
        ]
    if k == "critical_result_escalation":
        if not p.get("abnormal"):
            return []
        crit = p.get("critical")
        return [
            {"type": "create_task", "title": f"{'CRITICAL ' if crit else ''}Review result: {p.get('title')} — {pname}",
             "user_id": p.get("ordering_user_id"), "priority": "urgent" if crit else "high", "link": f"/patients/{p['patient_id']}/results"},
            {"type": "notify_staff", "user_id": p.get("ordering_user_id"), "title": f"Abnormal result needs review: {pname}", "link": f"/patients/{p['patient_id']}/results"},
        ]
    if k == "document_routing":
        role = DOC_ROUTES.get(p.get("doc_type") or "other", "clinic_admin")
        return [{"type": "create_task", "title": f"Review incoming {str(p.get('doc_type') or 'document').replace('_', ' ')}", "role": role,
                 "priority": "normal", "link": f"/documents/{p['document_id']}",
                 "reason": f"Classified as {p.get('doc_type')} (confidence {p.get('confidence')}) → routed to {role}"}]
    if k == "message_triage":
        cat, urgency, role = classify_message(f"{p.get('subject', '')} {p.get('body', '')}")
        acts = [{"type": "create_task", "title": f"{'URGENT ' if urgency == 'urgent' else ''}Patient message ({cat.replace('_', ' ')}): {pname}",
                 "role": role, "priority": "urgent" if urgency == "urgent" else "normal", "link": f"/messages?thread={p['thread_id']}",
                 "reason": f"Rule-based classifier: {cat} / {urgency}"}]
        if urgency == "urgent" and p.get("pcp_user_id"):
            acts.append({"type": "notify_staff", "user_id": p["pcp_user_id"], "title": f"URGENT patient message from {pname}", "link": f"/messages?thread={p['thread_id']}"})
        return acts
    if k == "depression_screen_followup":
        if (p.get("phq2") or 0) < int(cfg.get("threshold", 3)):
            return []
        return [{"type": "create_task", "title": f"Positive PHQ-2 ({p['phq2']}/6): complete PHQ-9 — {pname}", "user_id": p.get("provider_user_id"),
                 "priority": "high", "link": f"/patients/{p['patient_id']}"}]
    if k == "follow_up_scheduling":
        if not p.get("follow_up"):
            return []
        return [{"type": "create_task", "title": f"Schedule follow-up for {pname}: {p['follow_up'][:120]}", "role": cfg.get("assign_role", "receptionist"),
                 "priority": "normal", "link": f"/patients/{p['patient_id']}/appointments"}]
    return []


def emit(db: Session, org_id: uuid.UUID, event: str, payload: dict) -> None:
    """Record a domain event in the transactional outbox. Workflows run from the dispatcher after commit
    (handler "workflows"), with retries and exactly-once effects — see app/engine/events.py."""
    from app.engine.events import emit as outbox_emit

    outbox_emit(db, org_id, event, payload)


def run_workflows(db: Session, org_id: uuid.UUID, event: str, payload: dict) -> None:
    """Fire enabled template workflows for this event. Called by the outbox dispatcher."""
    if payload.get("patient_id") and not isinstance(payload["patient_id"], uuid.UUID):
        payload = {**payload, "patient_id": uuid.UUID(str(payload["patient_id"]))}
    try:
        wfs = db.scalars(select(AutomationWorkflow).where(AutomationWorkflow.organization_id == org_id, AutomationWorkflow.trigger == event,
                                                          AutomationWorkflow.is_enabled.is_(True))).all()
    except Exception:  # noqa: BLE001
        log.exception("automation lookup failed")
        return
    for wf in wfs:
        sp = db.begin_nested()
        try:
            allowed = set(TEMPLATES.get(wf.template_key, {}).get("permissions", []))
            actions = [a for a in _plan(wf, payload, db) if a["type"] in allowed]  # never exceed declared permissions
            if not actions:
                sp.commit()
                continue
            run = AutomationRun(organization_id=org_id, workflow_id=wf.id, trigger_event=event, subject_type=payload.get("subject_type"),
                                subject_id=str(payload.get("subject_id")) if payload.get("subject_id") else None,
                                patient_id=payload.get("patient_id"), proposed_actions=actions,
                                log=[{"at": now().isoformat(), "msg": f"Triggered by {event}"}])
            db.add(run)
            db.flush()
            if wf.requires_approval and any(ACTIONS[a["type"]]["sensitive"] for a in actions):
                run.status = "pending_approval"
                run.log = [*run.log, {"at": now().isoformat(), "msg": "Waiting for staff approval (contains patient-facing actions)"}]
            else:
                execute(db, run, actor_id=None)
            sp.commit()
        except Exception as e:  # noqa: BLE001
            sp.rollback()
            log.exception("automation run failed")
            fail = AutomationRun(organization_id=org_id, workflow_id=wf.id, trigger_event=event, status="failed", error=type(e).__name__,
                                 patient_id=payload.get("patient_id"), proposed_actions=[], log=[{"at": now().isoformat(), "msg": "Planning failed"}])
            db.add(fail)


def _role_user_ids(db: Session, org_id: uuid.UUID, role: str) -> list[uuid.UUID]:
    return list(db.scalars(select(Membership.user_id).join(MembershipRole).where(Membership.organization_id == org_id,
                                                                                  Membership.is_active.is_(True), MembershipRole.role == role)).all())


def execute(db: Session, run: AutomationRun, actor_id: uuid.UUID | None) -> None:
    run.status = "running"
    steps = list(run.log or [])
    try:
        for a in run.proposed_actions:
            if a["type"] == "create_task":
                t = Task(organization_id=run.organization_id, title=a["title"][:200], description=a.get("reason"), patient_id=run.patient_id,
                         assigned_role=a.get("role") if not a.get("user_id") else None,
                         assigned_user_id=uuid.UUID(str(a["user_id"])) if a.get("user_id") else None,
                         priority=a.get("priority", "normal"), link=a.get("link"), source="automation", run_id=run.id)
                db.add(t)
                steps.append({"at": now().isoformat(), "msg": f"Created task '{a['title'][:80]}' for {a.get('role') or 'assigned clinician'}"})
            elif a["type"] == "notify_staff":
                targets = [uuid.UUID(str(a["user_id"]))] if a.get("user_id") else _role_user_ids(db, run.organization_id, a.get("role", "clinic_admin"))
                for uid in targets:
                    notify(db, run.organization_id, uid, "automation", a["title"][:200], None, a.get("link"))
                steps.append({"at": now().isoformat(), "msg": f"Notified {len(targets)} staff member(s)"})
            elif a["type"] == "message_patient":
                p = db.get(Patient, run.patient_id)
                sender = actor_id or run.decided_by_id
                if not (p and sender):
                    raise ValueError("Patient message needs an approving staff member as sender")
                th = MessageThread(organization_id=run.organization_id, patient_id=p.id, subject=a["subject"], category="appointment",
                                   assigned_provider_id=p.primary_provider_id, patient_unread=1, last_message_at=now())
                db.add(th)
                db.flush()
                db.add(SecureMessage(organization_id=run.organization_id, thread_id=th.id, sender_id=sender, sender_is_patient=False, body=a["body"]))
                if p.portal_user_id:
                    notify(db, run.organization_id, p.portal_user_id, "message", "New message from your care team", a["subject"], f"/portal/messages/{th.id}")
                steps.append({"at": now().isoformat(), "msg": "Sent secure portal message to patient"})
        run.status, run.error = "succeeded", None
    except Exception as e:  # noqa: BLE001
        run.status, run.error = "failed", str(e)[:500]
        steps.append({"at": now().isoformat(), "msg": f"Failed: {str(e)[:200]}"})
    run.log, run.finished_at = steps, now()


def install_all(db: Session, org_id: uuid.UUID, enabled: bool = True) -> None:
    for key, t in TEMPLATES.items():
        db.add(AutomationWorkflow(organization_id=org_id, template_key=key, name=t["name"], description=t["description"], trigger=t["trigger"],
                                  config=dict(t["config"]), requires_approval=True, is_enabled=enabled))


def provider_user_id(db: Session, provider_id: uuid.UUID | None) -> uuid.UUID | None:
    if not provider_id:
        return None
    pr = db.get(ProviderProfile, provider_id)
    return pr.user_id if pr else None
