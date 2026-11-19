"""Cases: accountable problems with owners, SLAs, escalation and an append-only timeline.

All state changes go through this module so every transition is validated and recorded (case_events + audit).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import now
from app.models import Case, CaseEvent, Membership, MembershipRole, Task
from app.models.engine import CASE_OPEN
from app.services import audit
from app.services.realtime import publish

log = logging.getLogger("undeclared.engine.cases")

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
DEFAULT_SLA_MINUTES = {"info": 7 * 1440, "low": 3 * 1440, "medium": 1440, "high": 240, "critical": 30}
DEFAULT_ESCALATION = {"default": "clinic_admin"}
MAX_ESCALATION_LEVEL = 2

# Allowed manual transitions (system transitions — escalate, auto-resolve, unsnooze — are handled explicitly).
TRANSITIONS = {
    "open": {"in_progress", "waiting", "snoozed", "resolved", "cancelled"},
    "in_progress": {"open", "waiting", "snoozed", "resolved", "cancelled"},
    "waiting": {"in_progress", "open", "snoozed", "resolved", "cancelled"},
    "snoozed": {"open", "in_progress", "resolved", "cancelled"},
    "escalated": {"in_progress", "waiting", "resolved", "cancelled"},
    "resolved": {"open"},
    "cancelled": set(),
}


class CaseError(ValueError):
    pass


@dataclass
class Finding:
    """What a monitor (or event handler) detected. `dedupe_key` identifies the problem across runs."""

    dedupe_key: str
    title: str
    category: str
    kind: str
    severity: str = "medium"
    summary: str | None = None
    patient_id: uuid.UUID | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    facility_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    assign_role: str | None = None
    assign_user_id: uuid.UUID | None = None
    link: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    sla_minutes: int | None = None
    escalate_to: str | None = None


def log_event(db: Session, case: Case, kind: str, message: str, *, actor_id: uuid.UUID | None = None,
              actor_kind: str | None = None, data: dict | None = None) -> None:
    db.add(CaseEvent(organization_id=case.organization_id, case_id=case.id, at=now(), kind=kind, message=message[:500], actor_id=actor_id,
                     actor_kind=actor_kind or ("user" if actor_id else "system"), data=data or {}))


def _touch(db: Session, case: Case) -> None:
    publish(db, case.organization_id, "cases", case_id=case.id, category=case.category)


def find_open(db: Session, org_id: uuid.UUID, dedupe_key: str) -> Case | None:
    return db.scalar(select(Case).where(Case.organization_id == org_id, Case.dedupe_key == dedupe_key, Case.status.in_(CASE_OPEN)))


def open_case(db: Session, org_id: uuid.UUID, f: Finding, *, source: str = "monitor", rule_key: str | None = None,
              rule_version: int | None = None, actor_id: uuid.UUID | None = None) -> tuple[Case, bool]:
    """Create the case unless an open one with the same dedupe key exists. Returns (case, created)."""
    existing = find_open(db, org_id, f.dedupe_key)
    if existing:
        return existing, False
    sla = f.sla_minutes or DEFAULT_SLA_MINUTES.get(f.severity, 1440)
    case = Case(organization_id=org_id, facility_id=f.facility_id, department_id=f.department_id, category=f.category, kind=f.kind,
                dedupe_key=f.dedupe_key, title=f.title[:250], summary=f.summary, severity=f.severity, patient_id=f.patient_id,
                subject_type=f.subject_type, subject_id=f.subject_id, link=f.link, assigned_role=f.assign_role,
                assigned_user_id=f.assign_user_id, due_at=now() + timedelta(minutes=sla), source=source, rule_key=rule_key,
                rule_version=rule_version, evidence=f.evidence, data={**f.data, "escalate_to": f.escalate_to} if f.escalate_to else f.data)
    sp = db.begin_nested()
    try:
        db.add(case)
        db.flush()
        sp.commit()
    except IntegrityError:
        sp.rollback()  # lost a race with a concurrent run — the other case wins
        existing = find_open(db, org_id, f.dedupe_key)
        if existing:
            return existing, False
        raise
    owner = f"user {f.assign_user_id}" if f.assign_user_id else (f.assign_role or "unassigned")
    log_event(db, case, "created", f"Detected: {f.title[:200]} → assigned to {owner}",
              actor_id=actor_id, data={"rule": rule_key, "version": rule_version, "severity": f.severity, "evidence": f.evidence})
    audit.record(db, "case.opened", org_id=org_id, actor_id=actor_id, resource_type="case", resource_id=case.id,
                 patient_id=f.patient_id, details={"kind": f.kind, "rule": rule_key, "version": rule_version})
    _touch(db, case)
    return case, True


def refresh_case(db: Session, case: Case, f: Finding) -> bool:
    """Monitor re-detected an open case: refresh evidence; raise severity if it worsened. Returns True if severity rose."""
    case.last_detected_at = now()
    case.evidence = f.evidence
    if f.title and f.title[:250] != case.title:  # keep the headline in step with current evidence (e.g. "2 short" → "1 short")
        case.title = f.title[:250]
    if f.summary:
        case.summary = f.summary
    rose = SEVERITY_RANK.get(f.severity, 0) > SEVERITY_RANK.get(case.severity, 0)
    if rose:
        log_event(db, case, "severity", f"Severity raised {case.severity} → {f.severity}", data={"evidence": f.evidence})
        case.severity = f.severity
        sla = f.sla_minutes or DEFAULT_SLA_MINUTES.get(f.severity, 1440)
        new_due = now() + timedelta(minutes=sla)
        if case.due_at is None or new_due < case.due_at:
            case.due_at = new_due
        _touch(db, case)
    return rose


def transition(db: Session, case: Case, to: str, *, actor_id: uuid.UUID | None, note: str | None = None,
               resolution_code: str | None = None, system: bool = False, actor_kind: str | None = None) -> None:
    frm = case.status
    if frm == to:
        return
    if not system and to not in TRANSITIONS.get(frm, set()):
        raise CaseError(f"Cannot move a case from {frm} to {to}")
    if to in ("resolved", "cancelled") and not (note or resolution_code):
        raise CaseError("A resolution note is required")
    case.status = to
    if to in ("resolved", "cancelled"):
        case.resolved_at, case.resolved_by_id = now(), actor_id
        case.resolution, case.resolution_code = note, resolution_code or ("resolved" if to == "resolved" else "cancelled")
        # Close outstanding tasks for this case — the problem is gone.
        for t in db.scalars(select(Task).where(Task.case_id == case.id, Task.status.in_(("open", "in_progress")))):
            t.status, t.completed_at = ("done" if to == "resolved" else "cancelled"), now()
    elif frm in ("resolved", "cancelled"):
        case.resolved_at = case.resolved_by_id = case.resolution = case.resolution_code = None
    if to != "snoozed":
        case.snoozed_until = case.snooze_reason = None
    log_event(db, case, to if to in ("resolved", "cancelled") else "status", f"{frm} → {to}" + (f": {note}" if note else ""),
              actor_id=actor_id, actor_kind=actor_kind, data={"from": frm, "to": to, "code": resolution_code})
    audit.record(db, f"case.{to}", org_id=case.organization_id, actor_id=actor_id, resource_type="case", resource_id=case.id,
                 patient_id=case.patient_id, details={"from": frm, "code": resolution_code})
    _touch(db, case)


def resolve(db: Session, case: Case, note: str, *, code: str = "resolved", actor_id: uuid.UUID | None = None,
            actor_kind: str | None = None) -> None:
    transition(db, case, "resolved", actor_id=actor_id, note=note, resolution_code=code, system=True, actor_kind=actor_kind)


def assign(db: Session, case: Case, *, role: str | None, user_id: uuid.UUID | None, actor_id: uuid.UUID | None, note: str | None = None) -> None:
    case.assigned_role, case.assigned_user_id = role, user_id
    target = f"user {user_id}" if user_id else (role or "unassigned")
    log_event(db, case, "assigned", f"Assigned to {target}" + (f" — {note}" if note else ""), actor_id=actor_id,
              data={"role": role, "user_id": str(user_id) if user_id else None})
    if case.status == "open" and user_id:
        case.status = "in_progress"
    _touch(db, case)


def snooze(db: Session, case: Case, until: datetime, reason: str, *, actor_id: uuid.UUID) -> None:
    if not reason or len(reason.strip()) < 5:
        raise CaseError("A snooze needs a justification (at least 5 characters)")
    if until <= now() or until > now() + timedelta(days=30):
        raise CaseError("Snooze must end between now and 30 days from now")
    transition(db, case, "snoozed", actor_id=actor_id, note=reason)
    case.snoozed_until, case.snooze_reason = until, reason.strip()[:300]


def comment(db: Session, case: Case, text_: str, *, actor_id: uuid.UUID) -> None:
    log_event(db, case, "comment", text_[:500], actor_id=actor_id)
    _touch(db, case)


def role_user_ids(db: Session, org_id: uuid.UUID, role: str) -> list[uuid.UUID]:
    return list(db.scalars(select(Membership.user_id).join(MembershipRole).where(
        Membership.organization_id == org_id, Membership.is_active.is_(True), MembershipRole.role == role)).all())


def add_task(db: Session, case: Case | None, *, org_id: uuid.UUID, title: str, role: str | None = None,
             user_id: uuid.UUID | None = None, dedupe_key: str | None = None, priority: str = "normal", kind: str | None = None,
             description: str | None = None, link: str | None = None, due_minutes: int | None = None,
             patient_id: uuid.UUID | None = None, department_id: uuid.UUID | None = None, source: str = "automation") -> Task | None:
    """Create a task unless an open task with the same dedupe key exists (returns None in that case)."""
    if dedupe_key and db.scalar(select(Task.id).where(Task.organization_id == org_id, Task.dedupe_key == dedupe_key,
                                                      Task.status.in_(("open", "in_progress")))):
        return None
    t = Task(organization_id=org_id, title=title[:200], description=description, assigned_role=None if user_id else role,
             assigned_user_id=user_id, priority=priority, link=link or (case.link if case else None), source=source,
             case_id=case.id if case else None, dedupe_key=dedupe_key, kind=kind,
             patient_id=patient_id or (case.patient_id if case else None),
             facility_id=case.facility_id if case else None, department_id=department_id or (case.department_id if case else None),
             due_at=now() + timedelta(minutes=due_minutes) if due_minutes else None)
    sp = db.begin_nested()
    try:
        db.add(t)
        db.flush()
        sp.commit()
    except IntegrityError:
        sp.rollback()
        return None
    if case:
        log_event(db, case, "task", f"Task created: {title[:200]} → {('user' if user_id else role) or 'unassigned'}",
                  data={"task_id": str(t.id)})
    publish(db, org_id, "tasks", task_id=t.id)
    return t


def escalate_due(db: Session) -> dict[str, int]:
    """Escalate overdue cases exactly once per level; wake snoozed cases whose time has come."""
    from app.engine.notifications import deliver_to_role

    stats = {"escalated": 0, "woken": 0}
    for c in db.scalars(select(Case).where(Case.status == "snoozed", Case.snoozed_until <= now())).all():
        transition(db, c, "open", actor_id=None, note="Snooze ended", system=True)
        stats["woken"] += 1
    db.flush()
    overdue = db.scalars(select(Case).where(Case.status.in_(("open", "in_progress", "waiting", "escalated")), Case.due_at < now(),
                                            Case.escalation_level < MAX_ESCALATION_LEVEL)).all()
    for c in overdue:
        level = c.escalation_level
        # Conditional update = exactly-once escalation per level even with concurrent workers.
        res = db.execute(update(Case).where(Case.id == c.id, Case.escalation_level == level)
                         .values(escalation_level=level + 1).execution_options(synchronize_session=False))
        if res.rowcount != 1:
            continue
        c.escalation_level = level + 1
        to_role = (c.data or {}).get("escalate_to") or DEFAULT_ESCALATION["default"]
        if level + 1 >= 2:
            to_role = "hospital_admin" if role_user_ids(db, c.organization_id, "hospital_admin") else "clinic_admin"
        prev = c.assigned_role or "unassigned"
        c.status, c.escalated_at, c.assigned_role, c.assigned_user_id = "escalated", now(), to_role, None
        sla = DEFAULT_SLA_MINUTES.get(c.severity, 1440)
        c.due_at = now() + timedelta(minutes=max(sla // 2, 15))
        log_event(db, c, "escalated", f"SLA missed — escalated (level {level + 1}) from {prev} to {to_role}",
                  data={"level": level + 1, "from": prev, "to": to_role})
        audit.record(db, "case.escalated", org_id=c.organization_id, resource_type="case", resource_id=c.id, patient_id=c.patient_id,
                     details={"level": level + 1, "to": to_role})
        deliver_to_role(db, c.organization_id, to_role, case=c, category="escalation",
                        subject=f"Escalated: {c.title[:150]}", body=f"Case #{c.number} missed its target time and was escalated to you.",
                        link=f"/cases/{c.id}", dedupe=f"case:{c.id}:escalation:{level + 1}")
        _touch(db, c)
        db.flush()
        stats["escalated"] += 1
    db.flush()
    return stats
