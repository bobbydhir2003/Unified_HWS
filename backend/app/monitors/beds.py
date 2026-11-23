"""Bed flow monitors: slow bed turnover, admissions waiting for a bed, discharges ordered but not departed."""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import now
from app.engine.cases import Finding, human_duration
from app.engine.monitors import Monitor, register
from app.models import BedAssignment, InpatientStay, Location


def _mins(t) -> int:
    return int((now() - t).total_seconds() // 60) if t else 0


class BedCleaningDelay(Monitor):
    key = "beds.cleaning_delay"
    name = "Bed turnover delay"
    description = "A bed has been waiting for cleaning longer than the target, keeping a bed out of service."
    category = "bed"
    default_config = {"threshold_minutes": 60, "critical_minutes": 120, "assign_role": "bed_manager"}
    config_help = {"threshold_minutes": "Open a case after this long in 'cleaning'", "critical_minutes": "Escalate severity to high after this long",
                   "assign_role": "Role that owns turnover cases"}

    def evaluate(self, db: Session, org_id: uuid.UUID, cfg: dict) -> list[Finding]:
        beds = db.scalars(select(Location).where(Location.organization_id == org_id, Location.kind == "bed", Location.bed_status == "cleaning",
                                                 Location.bed_status_changed_at < now() - timedelta(minutes=int(cfg["threshold_minutes"])))).all()
        out = []
        for b in beds:
            m = _mins(b.bed_status_changed_at)
            out.append(Finding(dedupe_key=f"bed.clean:{b.id}:{b.bed_status_changed_at.isoformat()}", kind=self.key, category="bed",
                               severity="high" if m >= int(cfg["critical_minutes"]) else "medium",
                               title=f"Bed {b.code} waiting for cleaning {human_duration(m)}", facility_id=b.facility_id, department_id=b.department_id,
                               subject_type="bed", subject_id=str(b.id), assign_role=cfg["assign_role"], link="/beds", sla_minutes=30,
                               evidence={"bed": b.code, "minutes_in_cleaning": m, "since": b.bed_status_changed_at.isoformat()}))
        return out

    def clear(self, db, case, cfg):
        b = db.get(Location, uuid.UUID(case.subject_id))
        return "condition_cleared", f"Bed {b.code if b else ''} is now {b.bed_status if b else 'removed'}."


class PendingAdmission(Monitor):
    key = "adt.pending_admission"
    name = "Admission waiting for a bed"
    description = "An admission was requested but no bed has been assigned within the target time (boarding risk)."
    category = "bed"
    default_config = {"threshold_minutes": 60, "critical_minutes": 240, "assign_role": "bed_manager"}
    config_help = {"threshold_minutes": "Open a case after waiting this long", "critical_minutes": "High severity after this long",
                   "assign_role": "Role that owns bed placement"}

    def evaluate(self, db, org_id, cfg):
        stays = db.scalars(select(InpatientStay).where(InpatientStay.organization_id == org_id, InpatientStay.status == "pending",
                                                       InpatientStay.requested_at < now() - timedelta(minutes=int(cfg["threshold_minutes"])))).all()
        out = []
        for s in stays:
            m = _mins(s.requested_at)
            out.append(Finding(dedupe_key=f"adt.pending:{s.id}", kind=self.key, category="bed",
                               severity="high" if m >= int(cfg["critical_minutes"]) else "medium",
                               title=f"Waiting {human_duration(m)} for a bed — {s.patient.full_name} ({s.level_of_care.replace('_', '-')})",
                               patient_id=s.patient_id, facility_id=s.facility_id, department_id=s.requested_department_id,
                               subject_type="inpatient_stay", subject_id=str(s.id), assign_role=cfg["assign_role"], link="/beds", sla_minutes=30,
                               evidence={"waiting_minutes": m, "source": s.admit_source, "level_of_care": s.level_of_care, "isolation": s.isolation}))
        return out

    def clear(self, db, case, cfg):
        s = db.get(InpatientStay, uuid.UUID(case.subject_id))
        if s and s.status in ("admitted", "discharge_ordered"):
            a = db.scalar(select(BedAssignment).where(BedAssignment.stay_id == s.id).order_by(BedAssignment.start_at).limit(1))
            bed = db.get(Location, a.bed_id) if a else None
            return "verified_active", f"Patient placed in bed {bed.code if bed else ''}."
        return "no_longer_applicable", f"Admission {s.status if s else 'removed'}."


class DischargeNotDeparted(Monitor):
    key = "discharge.not_departed"
    name = "Discharge ordered, patient not departed"
    description = "A discharge order is older than the target and the patient still occupies the bed."
    category = "discharge"
    default_config = {"threshold_minutes": 120, "assign_role": "nurse"}
    config_help = {"threshold_minutes": "Open a case this long after the discharge order", "assign_role": "Role that owns departure"}

    def evaluate(self, db, org_id, cfg):
        stays = db.scalars(select(InpatientStay).where(InpatientStay.organization_id == org_id, InpatientStay.status == "discharge_ordered",
                                                       InpatientStay.discharge_ordered_at < now() - timedelta(minutes=int(cfg["threshold_minutes"])))).all()
        out = []
        from app.services.discharge import readiness

        for s in stays:
            m = _mins(s.discharge_ordered_at)
            r = readiness(db, s)
            blockers = r["blocking"] if r else []
            out.append(Finding(dedupe_key=f"dc.delay:{s.id}", kind=self.key, category="discharge", severity="high" if m > 360 else "medium",
                               title=f"Discharge ordered {human_duration(m)} ago, not departed — {s.patient.full_name}", patient_id=s.patient_id,
                               facility_id=s.facility_id, department_id=s.department_id, subject_type="inpatient_stay", subject_id=str(s.id),
                               assign_role=cfg["assign_role"], link=f"/inpatients/{s.id}", sla_minutes=60,
                               summary=("Outstanding: " + "; ".join(blockers)) if blockers else "Checklist complete — patient ready to depart.",
                               evidence={"minutes_since_order": m, "disposition": s.discharge_disposition, "blocking_items": blockers}))
        return out

    def clear(self, db, case, cfg):
        s = db.get(InpatientStay, uuid.UUID(case.subject_id))
        return ("verified_active", "Patient departed.") if s and s.status == "discharged" else ("no_longer_applicable", "Discharge order withdrawn.")


register(BedCleaningDelay())
register(PendingAdmission())
register(DischargeNotDeparted())
