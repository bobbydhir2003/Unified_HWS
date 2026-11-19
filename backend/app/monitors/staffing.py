"""Staffing monitor: shifts in the next 48 h below the department's minimum, with ranked fill suggestions as evidence."""

from app.core.security import now
from app.engine.cases import Finding
from app.engine.monitors import Monitor, register
from app.models import Department
from app.services.rostering import gaps, suggest


class CoverageGap(Monitor):
    key = "staffing.coverage_gap"
    name = "Staffing coverage gap"
    description = "A department shift in the next 48 hours has fewer scheduled staff than its minimum. Suggests eligible staff (hard rules enforced)."
    category = "staffing"
    default_config = {"hours_ahead": 48, "assign_role": "hospital_admin"}
    config_help = {"hours_ahead": "Look-ahead window", "assign_role": "Role that owns staffing gaps"}

    def evaluate(self, db, org_id, cfg):
        out = []
        for g in gaps(db, org_id, int(cfg["hours_ahead"])):
            dept = db.get(Department, g["department_id"])
            cands = suggest(db, org_id, dept, g["role"], g["start"], g["end"], limit=3)
            hours = (g["start"] - now()).total_seconds() / 3600
            out.append(Finding(
                dedupe_key=f"staff.gap:{g['department_id']}:{g['role']}:{g['start'].isoformat()}", kind=self.key, category="staffing",
                severity="high" if hours < 12 else "medium",
                title=f"{g['department']}: {g['short']} {g['role']}(s) short for {g['window']} shift {g['start']:%a %b %d %H:%M}",
                facility_id=g["facility_id"], department_id=g["department_id"], subject_type="department", subject_id=str(g["department_id"]),
                assign_role=cfg["assign_role"], link="/roster", sla_minutes=max(int(hours * 60) - 120, 30),
                evidence={"required": g["required"], "scheduled": g["scheduled"], "window_start": g["start"].isoformat(),
                          "suggestions": [{"name": c["name"], "reasons": "; ".join(c["reasons"])} for c in cands] or "No eligible staff — consider agency/float pool"}))
        return out

    def clear(self, db, case, cfg):
        return "verified_active", "Shift now meets the minimum staffing level."


register(CoverageGap())
