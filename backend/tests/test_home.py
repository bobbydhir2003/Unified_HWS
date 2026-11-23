"""Role-based Home and work ownership (UX simplification)."""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import now
from app.engine import cases as C
from app.engine.cases import human_duration
from app.models import Organization

ROLES = {"dr.chen@harborview.dev": "doctor", "nurse.kim@harborview.dev": "nurse", "frontdesk@harborview.dev": "receptionist",
         "pharmacist@harborview.dev": "pharmacist", "lab@harborview.dev": "lab_tech", "radiology@harborview.dev": "radiologist",
         "bedmanager@harborview.dev": "bed_manager", "billing@harborview.dev": "billing", "insurance@harborview.dev": "insurance_specialist",
         "hospitaladmin@harborview.dev": "hospital_admin", "clinicadmin@harborview.dev": "clinic_admin"}


def test_home_profiles_priorities_and_today(as_user):
    for email, profile in ROLES.items():
        r = as_user(email).get("/home")
        assert r.status_code == 200, (email, r.text)
        d = r.json()
        assert d["profile"] == profile, (email, d["profile"])
        assert len(d["priorities"]) <= 5
        for p in d["priorities"]:
            assert p["kind"] in ("case", "task", "approval", "critical_result") and p["owner"] and p["link"] and p["action"]
        sev = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        keys = [(sev.get(p["severity"], 2), 0 if p["overdue"] else 1) for p in d["priorities"]]
        assert keys == sorted(keys)  # clinical severity first, then overdue within a severity
        assert isinstance(d["today"]["metrics"], list)
    # Department numbers match the department screens.
    bm = as_user("bedmanager@harborview.dev")
    free = next(m for m in bm.get("/home").json()["today"]["metrics"] if m["label"] == "Free beds")
    assert free["value"] == bm.get("/adt/board").json()["totals"]["available"]


def test_escalation_keeps_owner_and_notifies_admin(as_user):
    db = SessionLocal()
    try:
        org = db.scalar(select(Organization.id).where(Organization.slug == "harborview"))
        c, _ = C.open_case(db, org, C.Finding(dedupe_key=f"test:home:{uuid.uuid4()}", title=f"Overdue nursing check {uuid.uuid4().hex[:5]}",
                                              category="operations", kind="test.home", severity="high", assign_role="nurse"))
        c.due_at = now() - timedelta(minutes=5)
        db.commit()
        C.escalate_due(db)
        db.commit()
        db.refresh(c)
        assert c.status == "escalated" and c.assigned_role == "nurse" and c.data["escalated_to"]
        cid, to_role = str(c.id), c.data["escalated_to"]
    finally:
        db.close()
    nurse_cases = {x["id"] for x in as_user("nurse.kim@harborview.dev").get("/worklist").json()["cases"]}
    assert cid in nurse_cases  # still visible to the team doing the work
    admin = "hospitaladmin@harborview.dev" if to_role == "hospital_admin" else "clinicadmin@harborview.dev"
    assert cid in {x["id"] for x in as_user(admin).get("/worklist").json()["cases"]}  # and to the escalation role


def test_human_duration():
    assert human_duration(45) == "45 min"
    assert human_duration(200) == "3 h 20 min"
    assert human_duration(120) == "2 h"
    assert human_duration(5452) == "3 d 18 h"
