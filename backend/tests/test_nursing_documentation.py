"""Nursing documentation: flowsheet validation + I&O totals + append-only corrections; assessments draft → sign
(required fields, author only, frozen in the DB) → amendment; care plans with progress; permissions."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import SessionLocal

RN, RN2, DOC, FRONT = "nurse.kim@harborview.dev", "nurse.rivera@harborview.dev", "dr.santos@harborview.dev", "frontdesk@harborview.dev"


def _pid(as_user):
    s = as_user("bedmanager@harborview.dev").get("/adt/stays", params={"status": "admitted"}).json()[0]
    return s["patient"]["id"] if "patient" in s else s["patient_id"]


def test_flowsheet_io_and_corrections(as_user):
    rn, front = as_user(RN), as_user(FRONT)
    pid = _pid(as_user)
    assert front.post(f"/patients/{pid}/flowsheet", json={"values": {"intake_oral": 200}}).status_code == 403
    assert rn.post(f"/patients/{pid}/flowsheet", json={"values": {"pain_score": 14}}).status_code == 400   # out of range
    assert rn.post(f"/patients/{pid}/flowsheet", json={"values": {"mobility": "Flying"}}).status_code == 400  # not an option
    before = rn.get(f"/patients/{pid}/flowsheet").json()["io"]
    assert rn.post(f"/patients/{pid}/flowsheet", json={"values": {"intake_oral": 250, "intake_iv": 500, "output_urine": 300, "pain_score": 3}}).status_code == 201
    fs = rn.get(f"/patients/{pid}/flowsheet").json()
    assert fs["io"]["intake_ml"] - before["intake_ml"] == 750 and fs["io"]["output_ml"] - before["output_ml"] == 300
    urine = next(o for o in fs["observations"] if o["row_key"] == "output_urine" and o["value"] == 300)
    assert rn.post(f"/flowsheet/{urine['id']}/correct", json={"value": 350, "reason": "Mis-read the bag"}).status_code == 201
    assert rn.post(f"/flowsheet/{urine['id']}/correct", json={"value": 360, "reason": "Again"}).status_code == 400
    fs2 = rn.get(f"/patients/{pid}/flowsheet").json()
    assert fs2["io"]["output_ml"] - fs["io"]["output_ml"] == 50  # the correction replaces, both rows are kept
    db = SessionLocal()
    try:
        with pytest.raises(DBAPIError):
            db.execute(text("DELETE FROM nursing_observations WHERE id = :i"), {"i": urine["id"]})
        db.rollback()
    finally:
        db.close()


def test_assessment_sign_freeze_and_amend(as_user):
    rn, rn2 = as_user(RN), as_user(RN2)
    pid = _pid(as_user)
    a = rn.post(f"/patients/{pid}/nursing-assessments", json={"template_key": "fall_risk", "data": {"history": "No"}}).json()
    assert a["status"] == "draft"
    assert rn2.put(f"/nursing-assessments/{a['id']}", json={"data": {"history": "Yes"}}).status_code == 403  # author only
    assert rn.post(f"/nursing-assessments/{a['id']}/sign").status_code == 400  # required fields missing
    rn.put(f"/nursing-assessments/{a['id']}", json={"data": {"history": "No", "gait": "Unsteady", "aid": "Cane / frame", "cognition": "Yes",
                                                               "precautions": "Bed low, call bell in reach"}})
    signed = rn.post(f"/nursing-assessments/{a['id']}/sign").json()
    assert signed["status"] == "signed" and signed["signed_by"]
    assert rn.put(f"/nursing-assessments/{a['id']}", json={"data": {}}).status_code == 400
    db = SessionLocal()
    try:
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE nursing_assessments SET data = '{}'::jsonb WHERE id = :i"), {"i": a["id"]})
        db.rollback()
    finally:
        db.close()
    am = rn2.post(f"/nursing-assessments/{a['id']}/amend", json={"reason": "Patient now reports a fall last month"}).json()
    rn2.put(f"/nursing-assessments/{am['id']}", json={"data": {**signed["data"], "history": "Yes"}})
    assert rn2.post(f"/nursing-assessments/{am['id']}/sign").json()["status"] == "signed"
    by_id = {x["id"]: x for x in rn.get(f"/patients/{pid}/nursing-assessments").json()}
    assert by_id[a["id"]]["status"] == "amended" and by_id[a["id"]]["data"]["history"] == "No"  # original preserved


def test_care_plan_progress(as_user):
    rn, doc = as_user(RN), as_user(DOC)
    pid = _pid(as_user)
    c = rn.post(f"/patients/{pid}/care-plans", json={"problem": "Risk of pressure injury", "goal": "Skin intact at discharge",
                                                      "interventions": ["Reposition every 2 hours", "Pressure-relieving mattress"]}).json()
    assert c["status"] == "active" and len(c["interventions"]) == 2
    c = rn.post(f"/care-plans/{c['id']}/progress", json={"note": "Skin intact, repositioned as planned", "status": "active"}).json()
    assert len(c["progress"]) == 1
    c = rn.post(f"/care-plans/{c['id']}/progress", json={"note": "Goal met", "status": "met"}).json()
    assert c["status"] == "met"
    assert rn.post(f"/care-plans/{c['id']}/progress", json={"note": "late note"}).status_code == 400
    assert any(x["id"] == c["id"] for x in doc.get(f"/patients/{pid}/care-plans").json())  # visible to the care team
