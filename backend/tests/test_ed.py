"""Emergency department: quick registration (temporary identity), nurse triage, rooming, provider, admission →
boarding → inpatient bed releases the ED bay, and identity reconciliation that preserves append-only history."""

import uuid

from sqlalchemy import func, select, text

from app.core.db import SessionLocal
from app.models import AuditEvent, Patient


def test_ed_to_inpatient_with_identity_reconciliation(as_user):
    nurse, doc, bedm, front = (as_user(e) for e in ("nurse.kim@harborview.dev", "dr.santos@harborview.dev", "bedmanager@harborview.dev",
                                                     "frontdesk@harborview.dev"))
    v = nurse.post("/ed/arrivals", json={"unidentified": True, "sex": "female", "approx_age": 30, "chief_complaint": "Found unresponsive",
                                         "arrival_mode": "ambulance"})
    assert v.status_code == 201, v.text
    v = v.json()
    assert v["patient"]["temporary"] and v["patient"]["name"].startswith("Unidentified")
    # Triage is recorded by nursing/physicians only — front desk can't.
    assert front.post(f"/ed/visits/{v['id']}/triage", json={"esi_level": 2}).status_code == 403
    t = nurse.post(f"/ed/visits/{v['id']}/triage", json={"esi_level": 2, "vitals": {"heart_rate": 118, "spo2": 91}}).json()
    assert t["esi_level"] == 2 and t["status"] == "triaged"
    bay = next(b for b in nurse.get("/ed/board").json()["bays"] if b["status"] == "available")
    assert nurse.post(f"/ed/visits/{v['id']}/room", json={"bed_id": bay["id"]}).json()["bay"]["id"] == bay["id"]
    assert doc.post(f"/ed/visits/{v['id']}/assign", json={"me": True}).json()["provider"]
    # Only physicians decide admission.
    assert nurse.post(f"/ed/visits/{v['id']}/disposition", json={"disposition": "admit"}).status_code == 403
    adm = doc.post(f"/ed/visits/{v['id']}/disposition", json={"disposition": "admit", "admit_reason": "Altered mental status", "level_of_care": "icu"}).json()
    assert adm["status"] == "boarding" and adm["stay_id"]
    # Identity reconciliation: real patient identified at bedside.
    real = front.post("/patients", json={"first_name": "Rowan", "last_name": f"Identified{uuid.uuid4().hex[:5]}", "date_of_birth": "1994-03-03",
                                         "sex_at_birth": "female", "confirm_not_duplicate": True}).json()
    assert front.post(f"/ed/visits/{v['id']}/reconcile", json={"patient_id": real["id"], "method": "ID card"}).status_code == 400  # attestation
    r = front.post(f"/ed/visits/{v['id']}/reconcile", json={"patient_id": real["id"], "method": "State ID verified by nurse", "attest_identity_verified": True})
    assert r.status_code == 200, r.text
    moved = r.json()["moved"]
    assert {"ed_visits", "triage_assessments", "vital_signs", "inpatient_stays", "adt_events"} <= set(moved)
    assert r.json()["visit"]["patient"]["id"] == real["id"]
    db = SessionLocal()
    try:
        tmp = db.get(Patient, uuid.UUID(v["patient"]["id"]))
        assert tmp.status == "merged" and str(tmp.merged_into_id) == real["id"]
        # The audit log is never rewritten: arrival is still recorded against the temporary id.
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.patient_id == tmp.id, AuditEvent.action == "ed.arrival")) == 1
        # Outside a merge, append-only tables still refuse patient_id changes.
        try:
            db.execute(text("UPDATE triage_assessments SET patient_id = :p WHERE patient_id = :q"), {"p": tmp.id, "q": uuid.UUID(real["id"])})
            raise AssertionError("append-only table accepted an update")
        except Exception as e:  # noqa: BLE001
            assert "append-only" in str(e)
        db.rollback()
    finally:
        db.close()
    # Inpatient bed assignment ends the ED visit and frees the bay.
    board = bedm.get("/adt/board").json()
    icu = next(b for u in board["units"] if u["code"] == "ICU" for b in u["beds"] if b["status"] == "available")
    assert bedm.post(f"/adt/stays/{adm['stay_id']}/assign-bed", json={"bed_id": icu["id"]}).status_code == 200
    done = doc.get(f"/ed/visits/{v['id']}").json()
    assert done["status"] == "departed" and done["disposition"] == "admitted"
    assert next(b for b in nurse.get("/ed/board").json()["bays"] if b["id"] == bay["id"])["status"] == "cleaning"


def test_one_active_ed_visit_per_patient(as_user):
    nurse = as_user("nurse.kim@harborview.dev")
    p = as_user("frontdesk@harborview.dev").post("/patients", json={"first_name": "Ed", "last_name": f"Twice{uuid.uuid4().hex[:5]}",
                                                                  "date_of_birth": "1970-01-01", "sex_at_birth": "male", "confirm_not_duplicate": True}).json()
    assert nurse.post("/ed/arrivals", json={"patient_id": p["id"], "chief_complaint": "Cough"}).status_code == 201
    assert nurse.post("/ed/arrivals", json={"patient_id": p["id"], "chief_complaint": "Cough again"}).status_code == 400
