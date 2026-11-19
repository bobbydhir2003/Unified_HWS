"""Radiology: technologist workflow, radiologist-only report signing, frozen signed reports (DB), addenda,
critical-finding acknowledgment closes its case. No PACS: simulated archive, no viewer."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import SessionLocal


def test_radiology_flow(as_user):
    rad, doc = as_user("radiology@harborview.dev"), as_user("dr.santos@harborview.dev")
    wl = rad.get("/radiology/worklist").json()
    o = next(x for x in wl["to_schedule"] if x["modality"] == "XR")
    s = rad.post("/radiology/studies", json={"order_id": o["order_id"]}).json()
    assert s["status"] == "scheduled" and s["study_instance_uid"].startswith("2.25.") and s["viewer_url"] is None and s["pacs"] == "simulated"
    assert rad.post(f"/radiology/studies/{s['id']}/status", json={"to": "completed"}).status_code == 400  # must follow the sequence
    for to in ("arrived", "in_progress", "completed"):
        assert rad.post(f"/radiology/studies/{s['id']}/status", json={"to": to}).status_code == 200
    report = {"findings": "Right lower lobe consolidation. Small right pleural effusion.", "impression": "Right lower lobe pneumonia with small effusion.",
              "critical_finding": True}
    assert doc.put(f"/radiology/studies/{s['id']}/report", json=report).status_code == 403  # radiologists only
    rad.put(f"/radiology/studies/{s['id']}/report", json=report)
    signed = rad.post(f"/radiology/studies/{s['id']}/sign").json()
    assert signed["status"] == "final" and signed["signed_by"]
    assert "IMPRESSION" in doc.get(f"/orders/{o['order_id']}").json()["result_text"]
    # Signed report is frozen in the database; addenda are allowed.
    db = SessionLocal()
    try:
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE imaging_studies SET impression = 'changed' WHERE id = :i"), {"i": uuid.UUID(s["id"])})
        db.rollback()
    finally:
        db.close()
    assert rad.put(f"/radiology/studies/{s['id']}/report", json=report).status_code == 400
    assert len(rad.post(f"/radiology/studies/{s['id']}/addendum", json={"text": "Compared with prior: new finding."}).json()["addenda"]) == 1
    # Critical finding: case to the ordering clinician; acknowledgment resolves it.
    case = next(c for c in as_user("hospitaladmin@harborview.dev").get("/cases", params={"category": "radiology"}).json() if c["subject_id"] == s["id"])
    assert case["severity"] == "critical"
    assert as_user("nurse.kim@harborview.dev").post(f"/radiology/studies/{s['id']}/acknowledge", json={"read_back": "noted by nurse"}).status_code == 403
    assert doc.post(f"/radiology/studies/{s['id']}/acknowledge", json={"read_back": "RLL pneumonia — antibiotics adjusted"}).status_code == 200
    assert doc.get(f"/cases/{case['id']}").json()["case"]["status"] == "resolved"
