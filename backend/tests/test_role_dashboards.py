"""Role dashboards on Home: every workspace loads its own dashboard from live data, figures match the department
screens, restricted charts and other organizations never appear, and recent AI activity is the user's own."""
import uuid

from sqlalchemy import update

from app.core.db import SessionLocal
from app.models import Patient

SUPER = "admin@undeclared.dev"
STAFF_ROLES = ["super_admin", "hospital_admin", "clinic_admin", "doctor", "nurse", "receptionist", "billing", "insurance_specialist",
               "pharmacist", "lab_tech", "radiology_tech", "radiologist", "bed_manager"]
PRIMARY = {"doctor": "doctor_assistant", "nurse": "discharge_coordination", "receptionist": "insurance_guardian", "pharmacist": "pharmacy_watchdog",
           "billing": "claims_review", "insurance_specialist": "insurance_guardian", "bed_manager": "discharge_coordination",
           "hospital_admin": "hospital_operations", "super_admin": "hospital_operations"}


def test_every_staff_workspace_gets_its_own_dashboard(as_user):
    admin = as_user(SUPER)
    titles = set()
    for role in STAFF_ROLES:
        r = admin.act(role).get("/home")
        assert r.status_code == 200, (role, r.text)
        d = r.json()
        dash = d["dashboard"]
        assert d["dashboard_profile"] == role, (role, d["dashboard_profile"])
        assert dash["header"]["title"] and dash["metrics"], role
        assert all(isinstance(m["value"], (int, str)) and m["link"].startswith("/") for m in dash["metrics"]), role
        assert dash["agents"]["primary"], role
        if role in PRIMARY:
            assert dash["agents"]["primary"] == PRIMARY[role]
        titles.add(dash["header"]["title"])
        assert d["identity"]["is_platform_admin"] is True and d["identity"]["acting_role"] == role  # identity ≠ workspace
    assert len(titles) == len(STAFF_ROLES)  # no generic fallback
    assert admin.act("patient").get("/home").status_code in (200, 403)  # patients use the portal


def test_dashboard_figures_match_department_screens(as_user):
    rx, nurse, bm = as_user("pharmacist@harborview.dev"), as_user("nurse.kim@harborview.dev"), as_user("bedmanager@harborview.dev")
    m = {x["key"]: x["value"] for x in rx.get("/home").json()["dashboard"]["metrics"]}
    assert m["verify"] == len(rx.get("/pharmacy/medication-queue").json())
    n = {x["key"]: x["value"] for x in nurse.get("/home").json()["dashboard"]["metrics"]}
    assert n["patients"] == len(nurse.get("/nursing/patients").json())
    b = {x["key"]: x["value"] for x in bm.get("/home").json()["dashboard"]["metrics"]}
    assert b["free"] == bm.get("/adt/board").json()["totals"]["available"]
    auto = rx.get("/home").json()["dashboard"]["automation"]
    assert auto["monitors"] == 22 and auto["safety_rule_only"] == 3 and auto["enabled"] <= 22


def test_restricted_patients_and_other_organizations_never_appear(as_user):
    admin, lake = as_user(SUPER), as_user("dr.lake@lakeside.dev", "lakeside")
    doc = admin.act("doctor")
    sched = doc.get("/home").json()["dashboard"]["queue"]
    ids = [i["patient_id"] for i in (sched or {}).get("items", []) if i.get("patient_id")]
    assert ids, "the seeded clinic has appointments today"
    if ids:
        db = SessionLocal()
        db.execute(update(Patient).where(Patient.id == uuid.UUID(ids[0])).values(is_restricted=True))
        db.commit()
        try:
            again = [i.get("patient_id") for i in (doc.get("/home").json()["dashboard"]["queue"] or {}).get("items", [])]
            assert ids[0] not in again
        finally:
            db.execute(update(Patient).where(Patient.id == uuid.UUID(ids[0])).values(is_restricted=False))
            db.commit()
            db.close()
    harbor = {i.get("patient_id") for role in ("receptionist", "pharmacist", "hospital_admin")
              for sec in ("queue", "extra") for i in ((admin.act(role).get("/home").json()["dashboard"].get(sec) or {}).get("items", []))}
    lakeside = lake.get("/home").json()["dashboard"]
    seen = {i.get("patient_id") for sec in ("queue", "extra") for i in ((lakeside.get(sec) or {}).get("items", []))}
    assert not ((harbor - {None}) & seen)


def test_recent_ai_activity_is_only_the_users_own(as_user):
    ins, front = as_user("insurance@harborview.dev"), as_user("frontdesk@harborview.dev")
    c = ins.post("/assist/conversations", json={"agent_key": "insurance_guardian", "context_type": "workspace", "new": True}).json()
    ins.post(f"/assist/conversations/{c['id']}/messages", json={"text": "Summarize open coverage issues"})
    mine = ins.get("/home").json()["dashboard"]["ai_recent"]
    assert any(r["agent_key"] == "insurance_guardian" and r["summary"].startswith("Answered") for r in mine)
    theirs = front.get("/home").json()["dashboard"]["ai_recent"]
    assert not any(r["summary"].startswith("Answered") and r.get("context_type") == "workspace" and r["agent_key"] == "insurance_guardian"
                   and r["at"] == mine[0]["at"] for r in theirs)
