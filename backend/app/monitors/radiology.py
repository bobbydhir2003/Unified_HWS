"""Radiology monitors: completed studies not yet reported, and critical findings not acknowledged."""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.security import now
from app.engine.cases import Finding, human_duration
from app.engine.events import handler
from app.engine.monitors import Monitor, register, run_monitor
from app.models import DomainEvent, ImagingStudy


class Unread(Monitor):
    key = "radiology.unread"
    name = "Imaging studies awaiting a report"
    description = "Completed studies not yet signed by a radiologist beyond the target (STAT vs routine)."
    category = "radiology"
    default_config = {"stat_minutes": 60, "routine_minutes": 1440, "assign_role": "radiologist"}
    config_help = {"stat_minutes": "STAT completed → signed target", "routine_minutes": "Routine target", "assign_role": "Role that reads studies"}

    def evaluate(self, db, org_id, cfg):
        out = []
        for s in db.scalars(select(ImagingStudy).where(ImagingStudy.organization_id == org_id, ImagingStudy.status.in_(("completed", "preliminary")))):
            stat = s.order.priority == "stat"
            target = int(cfg["stat_minutes" if stat else "routine_minutes"])
            m = int((now() - s.completed_at).total_seconds() // 60) if s.completed_at else 0
            if m < target:
                continue
            out.append(Finding(dedupe_key=f"rad.unread:{s.id}", kind=self.key, category="radiology", severity="high" if stat else "medium",
                               title=f"{s.modality} #{s.accession_number} unread {human_duration(m)} — {s.order.title}", patient_id=s.patient_id,
                               subject_type="imaging_study", subject_id=str(s.id), assign_role=cfg["assign_role"], link="/radiology", sla_minutes=60,
                               evidence={"minutes_since_completed": m, "target": target, "priority": s.order.priority}))
        return out

    def clear(self, db, case, cfg):
        return "verified_active", "Report signed."


class CriticalFinding(Monitor):
    key = "radiology.critical_unacknowledged"
    name = "Critical imaging finding not acknowledged"
    description = "A signed report flagged critical must be acknowledged (read-back) by the ordering clinician."
    category = "radiology"
    default_config = {"sla_minutes": 60}
    config_help = {"sla_minutes": "Minutes to acknowledge before escalation"}

    def evaluate(self, db, org_id, cfg):
        out = []
        for s in db.scalars(select(ImagingStudy).where(ImagingStudy.organization_id == org_id, ImagingStudy.status == "final",
                                                       ImagingStudy.critical_finding.is_(True), ImagingStudy.critical_ack_at.is_(None),
                                                       ImagingStudy.signed_at > now() - timedelta(days=7))):
            out.append(Finding(dedupe_key=f"rad.critical:{s.id}", kind=self.key, category="radiology", severity="critical",
                               title=f"CRITICAL imaging finding — {s.patient.full_name}: {s.impression[:90]}", patient_id=s.patient_id,
                               subject_type="imaging_study", subject_id=str(s.id), assign_user_id=s.order.signed_by_id or s.order.ordered_by_id,
                               link="/radiology?tab=critical", sla_minutes=int(cfg["sla_minutes"]), escalate_to="doctor",
                               evidence={"study": s.order.title, "accession": s.accession_number}))
        return out

    def clear(self, db, case, cfg):
        s = db.get(ImagingStudy, uuid.UUID(case.subject_id))
        return ("verified_active", "Clinician acknowledged with read-back.") if s and s.critical_ack_at else ("no_longer_applicable", "Report changed")


register(Unread())
register(CriticalFinding())


@handler("radiology_critical_monitor", "radiology.report_signed", "radiology.critical_acknowledged")
def _recheck(db, ev: DomainEvent) -> None:
    run_monitor(db, ev.organization_id, "radiology.critical_unacknowledged")
    run_monitor(db, ev.organization_id, "radiology.unread")
