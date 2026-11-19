"""Analytics: live-data dashboards, care gaps, outreach idempotency, quality sanity, CSV export, access control."""

import uuid
from datetime import timedelta

from app.core.db import SessionLocal
from app.core.security import now
from app.models import LabResult, Order, Patient

DOCTOR, FRONT, BILLING, ADMIN = "dr.chen@harborview.dev", "frontdesk@harborview.dev", "billing@harborview.dev", "clinicadmin@harborview.dev"


def test_analytics_access_control(as_user):
    assert as_user(FRONT).get("/analytics/operations").status_code == 403
    assert as_user(DOCTOR).get("/analytics/operations").status_code == 200
    assert as_user(DOCTOR).get("/analytics/financial").status_code == 403
    assert as_user(BILLING).get("/analytics/financial").status_code == 200


def test_operations_numbers_are_consistent(as_user):
    d = as_user(DOCTOR).get("/analytics/operations", params={"days": 90}).json()
    assert sum(d["by_status"].values()) == d["total_appointments"]
    assert all(0 <= u["utilization"] <= 1.5 for u in d["utilization"])


def test_care_gap_detection_and_outreach_is_idempotent(as_user):
    doc, admin = as_user(DOCTOR), as_user(ADMIN)
    p = doc.post("/patients", json={"first_name": "Gap", "last_name": f"Case{uuid.uuid4().hex[:4]}", "date_of_birth": "1960-01-01",
                                    "sex_at_birth": "female", "confirm_not_duplicate": True}).json()
    doc.post(f"/patients/{p['id']}/problems", json={"code": "E11.9", "description": "Type 2 diabetes mellitus without complications", "is_chronic": True})
    gaps = {r["patient_id"] for r in doc.get("/analytics/care-gaps", params={"measure": "a1c_overdue"}).json()["patients"]}
    assert p["id"] in gaps  # diabetic with no A1c on file
    with SessionLocal() as db:  # insert a deterministic poor-control A1c result
        pat = db.get(Patient, uuid.UUID(p["id"]))
        o = Order(organization_id=pat.organization_id, patient_id=pat.id, order_type="lab", status="completed", title="Hemoglobin A1c", code="4548-4",
                  details={"code": "4548-4"}, ordered_by_id=doc.me["user"]["id"], signed_by_id=doc.me["user"]["id"], resulted_at=now())
        db.add(o)
        db.flush()
        db.add(LabResult(organization_id=pat.organization_id, order_id=o.id, patient_id=pat.id, name="Hemoglobin A1c", value="10.4", unit="%",
                         reference_range="4.0-5.6", flag="high", resulted_at=now() - timedelta(days=1)))
        db.commit()
    gaps = {r["patient_id"]: r for r in doc.get("/analytics/care-gaps", params={"measure": "a1c_poor_control"}).json()["patients"]}
    assert p["id"] in gaps and "10.4" in gaps[p["id"]]["detail"]
    assert p["id"] not in {r["patient_id"] for r in doc.get("/analytics/care-gaps", params={"measure": "a1c_overdue"}).json()["patients"]}
    first = admin.post("/analytics/care-gaps/outreach", json={"measure": "a1c_poor_control", "patient_ids": [p["id"]]}).json()
    again = admin.post("/analytics/care-gaps/outreach", json={"measure": "a1c_poor_control", "patient_ids": [p["id"]]}).json()
    assert first["created"] == 1 and again["created"] == 0


def test_quality_measures_are_sane_and_export(as_user):
    doc = as_user(DOCTOR)
    q = doc.get("/analytics/quality").json()
    assert "not certified" in q["disclaimer"]
    for m in q["measures"]:
        assert 0 <= m["numerator"] <= max(m["denominator"], 0) or m["denominator"] == 0
    r = doc.get("/analytics/export/quality.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "numerator" in r.text.splitlines()[0]
    r = doc.get("/analytics/export/appointments.csv", params={"days": 30})
    assert "patient" not in r.text.splitlines()[0]  # operational export carries no patient identifiers
    assert as_user(ADMIN).get("/audit", params={"action": "analytics.exported"}).json()["total"] >= 2


def test_population_is_tenant_scoped(as_user):
    harbor = as_user(DOCTOR).get("/analytics/population").json()
    lake = as_user("dr.lake@lakeside.dev", "lakeside").get("/analytics/population").json()
    assert lake["active_patients"] < harbor["active_patients"]
