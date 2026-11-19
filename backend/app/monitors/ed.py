"""Emergency department monitors: boarding delays and door-to-provider targets by nurse-recorded ESI."""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.security import now
from app.engine.cases import Finding
from app.engine.monitors import Monitor, register
from app.models import EdVisit


def _mins(t):
    return int((now() - t).total_seconds() // 60) if t else 0


class EdBoarding(Monitor):
    key = "ed.boarding"
    name = "ED boarding"
    description = "An admitted ED patient has been waiting in the department for an inpatient bed longer than the target."
    category = "ed"
    default_config = {"threshold_minutes": 120, "critical_minutes": 240, "assign_role": "bed_manager"}
    config_help = {"threshold_minutes": "Open a case after boarding this long", "critical_minutes": "High severity after this long",
                   "assign_role": "Role that owns boarding cases"}

    def evaluate(self, db, org_id, cfg):
        out = []
        for v in db.scalars(select(EdVisit).where(EdVisit.organization_id == org_id, EdVisit.status == "boarding",
                                                  EdVisit.disposition_at < now() - timedelta(minutes=int(cfg["threshold_minutes"])))):
            m = _mins(v.disposition_at)
            out.append(Finding(dedupe_key=f"ed.boarding:{v.id}", kind=self.key, category="ed", severity="high" if m >= int(cfg["critical_minutes"]) else "medium",
                               title=f"ED boarding {m // 60}h {m % 60}m — {v.patient.full_name}", patient_id=v.patient_id, facility_id=v.facility_id,
                               subject_type="ed_visit", subject_id=str(v.id), assign_role=cfg["assign_role"], link="/beds", sla_minutes=30,
                               evidence={"boarding_minutes": m, "esi": v.esi_level, "stay_id": str(v.stay_id) if v.stay_id else None}))
        return out

    def clear(self, db, case, cfg):
        v = db.get(EdVisit, uuid.UUID(case.subject_id))
        return ("verified_active", "Patient left the ED for an inpatient bed.") if v and v.disposition == "admitted" else ("no_longer_applicable", "No longer boarding.")


class DoorToProvider(Monitor):
    key = "ed.door_to_provider"
    name = "ED door-to-provider"
    description = "A patient has not been seen by a provider within the target for their nurse-assigned ESI level."
    category = "ed"
    default_config = {"esi_1_2_minutes": 10, "esi_3_minutes": 60, "esi_4_5_minutes": 120, "untriaged_minutes": 15, "assign_role": "doctor"}
    config_help = {"esi_1_2_minutes": "Target for ESI 1–2", "esi_3_minutes": "Target for ESI 3", "esi_4_5_minutes": "Target for ESI 4–5",
                   "untriaged_minutes": "Open a case if a patient waits this long without triage (assigned to nursing)",
                   "assign_role": "Role that owns provider delays"}

    def evaluate(self, db, org_id, cfg):
        out = []
        for v in db.scalars(select(EdVisit).where(EdVisit.organization_id == org_id, EdVisit.status.in_(("waiting", "triaged", "roomed")),
                                                  EdVisit.provider_seen_at.is_(None))):
            m = _mins(v.arrival_at)
            if v.esi_level is None:
                if m >= int(cfg["untriaged_minutes"]):
                    out.append(Finding(dedupe_key=f"ed.untriaged:{v.id}", kind=self.key, category="ed", severity="high",
                                       title=f"Waiting {m} min without triage — {v.patient.full_name}", patient_id=v.patient_id, facility_id=v.facility_id,
                                       subject_type="ed_visit", subject_id=str(v.id), assign_role="nurse", link="/ed", sla_minutes=10,
                                       evidence={"minutes_since_arrival": m, "complaint": v.chief_complaint}))
                continue
            target = int(cfg["esi_1_2_minutes"] if v.esi_level <= 2 else cfg["esi_3_minutes"] if v.esi_level == 3 else cfg["esi_4_5_minutes"])
            if m >= target:
                out.append(Finding(dedupe_key=f"ed.d2p:{v.id}", kind=self.key, category="ed", severity="critical" if v.esi_level <= 2 else "high" if v.esi_level == 3 else "medium",
                                   title=f"ESI {v.esi_level} waiting {m} min for a provider (target {target}) — {v.patient.full_name}", patient_id=v.patient_id,
                                   facility_id=v.facility_id, subject_type="ed_visit", subject_id=str(v.id), assign_role=cfg["assign_role"], link="/ed",
                                   sla_minutes=10, evidence={"esi": v.esi_level, "minutes_since_arrival": m, "target_minutes": target}))
        return out

    def clear(self, db, case, cfg):
        v = db.get(EdVisit, uuid.UUID(case.subject_id))
        if v and v.provider_seen_at:
            return "verified_active", f"Seen by a provider {int((v.provider_seen_at - v.arrival_at).total_seconds() // 60)} min after arrival."
        if v and v.esi_level is not None and case.dedupe_key.startswith("ed.untriaged"):
            return "verified_active", f"Triaged ESI {v.esi_level}."
        return "no_longer_applicable", "Patient left the department."


register(EdBoarding())
register(DoorToProvider())
