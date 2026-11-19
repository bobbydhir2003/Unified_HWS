"""Lab monitors: unacknowledged critical results (call-back), turnaround delays, specimens collected but not received."""

import uuid

from sqlalchemy import select

from app.core.security import now
from app.engine.cases import Finding
from app.engine.events import handler
from app.engine.monitors import Monitor, register, run_monitor
from app.models import CriticalResultAlert, DomainEvent, Patient, Specimen


def _m(t):
    return int((now() - t).total_seconds() // 60)


class CriticalCallback(Monitor):
    key = "lab.critical_unacknowledged"
    name = "Critical lab result not acknowledged"
    description = "A verified critical value must be acknowledged (read-back) by the responsible clinician. Opens immediately; escalates on the SLA."
    category = "lab"
    default_config = {"sla_minutes": 30}
    config_help = {"sla_minutes": "Minutes for the clinician to acknowledge before escalation"}

    def evaluate(self, db, org_id, cfg):
        out = []
        for a in db.scalars(select(CriticalResultAlert).where(CriticalResultAlert.organization_id == org_id, CriticalResultAlert.acknowledged_at.is_(None))):
            p = db.get(Patient, a.patient_id)
            out.append(Finding(dedupe_key=f"lab.critical:{a.id}", kind=self.key, category="lab", severity="critical",
                               title=f"CRITICAL {a.summary} — {p.full_name}: acknowledge result", patient_id=a.patient_id, subject_type="critical_alert",
                               subject_id=str(a.id), assign_user_id=a.clinician_user_id, assign_role=None if a.clinician_user_id else "doctor",
                               link="/lab?tab=critical", sla_minutes=int(cfg["sla_minutes"]), escalate_to="doctor",
                               evidence={"result": a.summary, "minutes_since_verified": _m(a.created_at)}))
        return out

    def on_open(self, db, case, f, cfg):
        a = db.get(CriticalResultAlert, uuid.UUID(case.subject_id))
        if a:
            a.case_id = case.id
        if case.assigned_user_id:
            from app.engine.notifications import deliver

            deliver(db, case.organization_id, channel="in_app", dedupe=f"{case.dedupe_key}:page", subject=case.title, body="Acknowledge with read-back.",
                    link=case.link, case=case, user_id=case.assigned_user_id, category="critical_result")

    def clear(self, db, case, cfg):
        a = db.get(CriticalResultAlert, uuid.UUID(case.subject_id))
        return "verified_active", f"Acknowledged {_m(a.created_at) - _m(a.acknowledged_at)} min after verification (read-back recorded)." if a and a.acknowledged_at else ("no_longer_applicable", "Alert removed")


class Turnaround(Monitor):
    key = "lab.turnaround"
    name = "Lab turnaround / specimen delays"
    description = "Specimens collected but not received, or received but not verified, beyond the target time."
    category = "lab"
    default_config = {"not_received_minutes": 60, "stat_minutes": 60, "routine_minutes": 240, "assign_role": "lab_tech"}
    config_help = {"not_received_minutes": "Collected → received target", "stat_minutes": "STAT received → verified target",
                   "routine_minutes": "Routine received → verified target", "assign_role": "Role that owns lab delays"}

    def evaluate(self, db, org_id, cfg):
        out = []
        for sp in db.scalars(select(Specimen).where(Specimen.organization_id == org_id, Specimen.status.in_(("collected", "received", "in_process")))):
            if sp.status == "collected":
                m, target, what = _m(sp.collected_at), int(cfg["not_received_minutes"]), "not received in lab"
            else:
                stat = sp.order.priority == "stat"
                m, target, what = _m(sp.received_at), int(cfg["stat_minutes" if stat else "routine_minutes"]), "awaiting verification"
            if m < target:
                continue
            out.append(Finding(dedupe_key=f"lab.tat:{sp.id}:{sp.status if sp.status == 'collected' else 'lab'}", kind=self.key, category="lab",
                               severity="high" if sp.order.priority == "stat" else "medium",
                               title=f"Accession {sp.accession_number} {what} for {m} min — {sp.order.title}", patient_id=sp.patient_id,
                               subject_type="specimen", subject_id=str(sp.id), assign_role=cfg["assign_role"], link="/lab", sla_minutes=60,
                               evidence={"minutes": m, "target": target, "priority": sp.order.priority, "status": sp.status}))
        return out

    def clear(self, db, case, cfg):
        sp = db.get(Specimen, uuid.UUID(case.subject_id))
        return "verified_active", f"Specimen now {sp.status if sp else 'removed'}."


register(CriticalCallback())
register(Turnaround())


@handler("lab_critical_monitor", "lab.critical_result", "lab.critical_acknowledged")
def _recheck(db, ev: DomainEvent) -> None:
    run_monitor(db, ev.organization_id, "lab.critical_unacknowledged")
