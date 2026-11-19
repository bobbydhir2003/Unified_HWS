"""Discharge coordination closed loop: order → checklist + owner tasks → data-verified items → clinician-approved
instructions → departure; plus guardrails (auto items can't be ticked by hand, owners only, instructions need clinical:sign)."""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def test_closed_loop_discharge(as_user):
    doc, nurse, pharm, front = (as_user(e) for e in ("dr.santos@harborview.dev", "nurse.kim@harborview.dev", "pharmacist@harborview.dev",
                                                       "frontdesk@harborview.dev"))
    tag = uuid.uuid4().hex[:6]
    p = front.post("/patients", json={"first_name": "Dc", "last_name": f"Loop{tag}", "date_of_birth": "1955-02-02", "sex_at_birth": "female",
                                      "confirm_not_duplicate": True}).json()
    board = as_user("bedmanager@harborview.dev").get("/adt/board").json()
    bed = next(b for u in board["units"] if u["code"] == "4C" for b in u["beds"] if b["status"] == "available")
    stay = doc.post("/adt/stays", json={"patient_id": p["id"], "reason": "COPD exacerbation", "bed_id": bed["id"]}).json()
    assert stay["status"] == "admitted"
    doc.post(f"/adt/stays/{stay['id']}/discharge-order", json={"disposition": "home"})
    st = doc.get(f"/adt/stays/{stay['id']}/discharge").json()
    items = {i["key"]: i for i in st["readiness"]["items"]}
    assert not st["readiness"]["ready"] and all(i["task_id"] for i in items.values())  # one owner task per item
    # Auto items can't be ticked by hand; owners only for manual items.
    assert nurse.post(f"/adt/stays/{stay['id']}/discharge/items/follow_up", json={"status": "done"}).status_code == 400
    assert front.post(f"/adt/stays/{stay['id']}/discharge/items/med_rec", json={"status": "done"}).status_code == 400
    assert pharm.post(f"/adt/stays/{stay['id']}/discharge/items/med_rec", json={"status": "done", "note": "Home meds reconciled"}).status_code == 200
    for k in ("transport", "education"):
        assert nurse.post(f"/adt/stays/{stay['id']}/discharge/items/{k}", json={"status": "done"}).status_code == 200
    assert nurse.post(f"/adt/stays/{stay['id']}/discharge/items/equipment", json={"status": "not_applicable"}).status_code == 200
    # Documentation verified from data: a signed discharge-summary note on the inpatient encounter.
    encs = doc.get(f"/patients/{p['id']}/encounters").json()
    enc = next(e for e in (encs["items"] if isinstance(encs, dict) else encs) if e["encounter_type"] == "inpatient")
    n = doc.post(f"/encounters/{enc['id']}/notes", json={"note_type": "discharge_summary", "title": "Discharge summary"}).json()
    n = doc.put(f"/notes/{n['id']}", json={"content": {"subjective": "Improved dyspnea", "objective": "SpO2 95% RA", "assessment": "COPD exacerbation, resolved",
                                                       "plan": "Prednisone 40 mg daily for 3 more days. Use inhaler as prescribed."},
                                           "expected_version": n["current_version"]}).json()
    assert doc.post(f"/notes/{n['id']}/sign", json={"expected_version": n["current_version"]}).status_code == 200
    # Instructions: agent drafts → only clinical:sign can approve.
    dr = doc.post(f"/adt/stays/{stay['id']}/discharge/instructions/draft").json()
    assert "Prednisone 40 mg" in dr["text"]
    assert nurse.post(f"/adt/stays/{stay['id']}/discharge/instructions/approve", json={"approval_id": dr["approval_id"], "text": dr["text"]}).status_code == 403
    doc.post(f"/adt/stays/{stay['id']}/discharge/instructions/approve", json={"approval_id": dr["approval_id"], "text": dr["text"] + "\nBring your inhaler."})
    # Follow-up verified from data: front desk books an appointment.
    clinic = next(c for c in front.membership["clinics"] if c["code"] == "HDT")
    chen = next(x for x in front.get("/providers").json() if "Chen" in x["name"])
    start = datetime.now(ZoneInfo(clinic["timezone"])).replace(second=0, microsecond=0) + timedelta(days=6, minutes=3)
    for _ in range(30):
        r = front.post("/appointments", json={"patient_id": p["id"], "provider_id": chen["id"], "clinic_id": clinic["id"], "start_at": start.isoformat(),
                                              "end_at": (start + timedelta(minutes=5)).isoformat(), "override_availability": True, "reason": "Post-discharge"})
        if r.status_code == 201:
            break
        start += timedelta(minutes=7)
    st = nurse.get(f"/adt/stays/{stay['id']}/discharge").json()["readiness"]
    assert st["ready"], st["blocking"]
    tasks = {t["kind"]: t for t in nurse.get("/tasks", params={"scope": "all", "status": "done"}).json() if t["patient_id"] == p["id"]}
    assert {"discharge.follow_up", "discharge.documentation", "discharge.instructions"} <= set(tasks)  # verify step closed them
    d = nurse.post(f"/adt/stays/{stay['id']}/discharge", json={}).json()
    assert d["status"] == "discharged"
