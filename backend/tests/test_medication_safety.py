"""Closed-loop medication safety (mandatory): signing never completes an inpatient order; pharmacist verification gates
dispensing and administration; rejected orders stop; barcode (simulated) patient/dose/route mismatches are blocked;
duplicate administration is impossible; PRN interval; independent witness for high-alert drugs; append-only eMAR."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import SessionLocal

DOC, RX, RN, RN2 = "dr.santos@harborview.dev", "pharmacist@harborview.dev", "nurse.kim@harborview.dev", "nurse.rivera@harborview.dev"


def _admitted_patient(as_user, skip=0):
    stays = as_user("bedmanager@harborview.dev").get("/adt/stays", params={"status": "admitted"}).json()
    return stays[skip]["patient"]["id"] if "patient" in stays[skip] else stays[skip]["patient_id"]


def _order(doc, pid, **over):
    details = {"name": "Ceftriaxone", "strength": "1 g", "route": "intravenous", "sig": "1 g IV once", "quantity": 1, "refills": 0,
               "frequency": "once"} | over
    o = doc.post("/orders", json={"patient_id": pid, "order_type": "medication", "details": details}).json()
    r = doc.post(f"/orders/{o['id']}/sign", json={"override_reason": "Reviewed in test"})
    assert r.status_code == 200, r.text
    return r.json()


def _lot(rx, name):
    it = next(i for i in rx.get("/inventory/items").json() if i["name"] == name)
    lots = [x for x in rx.get(f"/inventory/items/{it['id']}").json()["lots"] if not x.get("expired") and x["quantity"] > 0]
    return lots[0]


def _dispense(rx, order, name="Ceftriaxone", qty=1):
    lot = _lot(rx, name)
    return rx.post("/inventory/dispense", json={"lot_id": lot["lot_id"], "location_id": lot["location_id"], "quantity": qty,
                                                "patient_id": order["patient_id"], "order_id": order["id"]})


def _give(rn, order, wristband, label, **over):
    body = {"order_id": order["id"], "status": "given", "dose": "1 g", "route": "intravenous", "patient_barcode": wristband,
            "medication_barcode": label} | over
    return rn.post("/mar/administrations", json=body)


def _slot(rn, order):
    mar = rn.get(f"/mar/patients/{order['patient_id']}").json()
    row = next(r for r in mar["orders"] if r["id"] == order["id"])
    return mar["patient"]["wristband"], (row["slots"][0]["at"] if row["slots"] else None)


def test_closed_loop_verification_gates_dispense_and_administration(as_user):
    doc, rx, rn = as_user(DOC), as_user(RX), as_user(RN)
    pid = _admitted_patient(as_user)
    o = _order(doc, pid)
    assert o["status"] == "pending_verification"  # signing never completes an inpatient medication order
    assert any(w["type"] == "screening_incomplete" for w in o["safety_warnings"])  # never silently "safe"

    # Not verified yet: no dispensing, no administration.
    assert _dispense(rx, o).json()["detail"]["code"] == "not_verified"
    r = rn.post("/mar/administrations", json={"order_id": o["id"], "status": "given", "scheduled_for": None})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_verified"

    # Verification: pharmacist only; manual interaction review is required while screening is unavailable.
    assert doc.post(f"/orders/{o['id']}/pharmacy-decision", json={"decision": "verified"}).status_code == 403
    r = rx.post(f"/orders/{o['id']}/pharmacy-decision", json={"decision": "verified"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "manual_review_required"
    r = rx.post(f"/orders/{o['id']}/pharmacy-decision", json={"decision": "verified", "manual_interaction_review": True})
    assert r.status_code == 200 and r.json()["status"] == "active"

    # Dispense only to the right patient; the label drives the scan.
    other = _admitted_patient(as_user, skip=1)
    lot = _lot(rx, "Ceftriaxone")
    bad = rx.post("/inventory/dispense", json={"lot_id": lot["lot_id"], "location_id": lot["location_id"], "quantity": 1, "patient_id": other, "order_id": o["id"]})
    assert bad.status_code == 409 and bad.json()["detail"]["code"] == "patient_mismatch"
    label = _dispense(rx, o).json()["dose_label"]
    assert label.startswith("RXD-")
    assert [x["barcode"] for x in rn.get(f"/mar/orders/{o['id']}/dose-labels").json()] == [label]

    wristband, slot = _slot(rn, o)
    assert slot, "a verified once-only order has one scheduled dose"
    checks = [({"patient_barcode": "PT-WRONG"}, "patient_mismatch"), ({"dose": "2 g"}, "dose_mismatch"), ({"route": "oral"}, "route_mismatch"),
              ({"medication_barcode": "RXD-00000000-0000-0000-0000-000000000000"}, "medication_unknown"), ({"patient_barcode": None}, "scan_patient")]
    for over, code in checks:
        r = _give(rn, o, wristband, label, scheduled_for=slot, **over)
        assert r.status_code == 409 and r.json()["detail"]["code"] == code, (over, r.text)
    assert as_user(RX).post("/mar/administrations", json={"order_id": o["id"], "status": "given", "scheduled_for": slot}).status_code == 403

    r = _give(rn, o, wristband, label, scheduled_for=slot)
    assert r.status_code == 201, r.text
    assert r.json()["scan"]["patient"] == "match" and r.json()["scan"]["simulated"] is True
    # Duplicate administration is impossible (the once-only order is now complete; the slot is documented).
    again = _give(rn, o, wristband, label, scheduled_for=slot)
    assert again.status_code == 409
    mar = rn.get(f"/mar/patients/{pid}").json()
    row = next(x for x in mar["orders"] if x["id"] == o["id"])
    assert row["status"] == "completed" and len(row["administrations"]) == 1


def test_rejected_and_discontinued_orders_stop(as_user):
    doc, rx, rn = as_user(DOC), as_user(RX), as_user(RN)
    pid = _admitted_patient(as_user)
    o = _order(doc, pid)
    assert rx.post(f"/orders/{o['id']}/pharmacy-decision", json={"decision": "rejected"}).status_code == 400  # reason required
    assert rx.post(f"/orders/{o['id']}/pharmacy-decision", json={"decision": "rejected", "note": "Duplicate antibiotic"}).json()["status"] == "rejected"
    assert _dispense(rx, o).json()["detail"]["code"] == "not_verified"
    assert rn.post("/mar/administrations", json={"order_id": o["id"], "status": "given"}).json()["detail"]["code"] == "order_closed"
    assert doc.post(f"/orders/{o['id']}/cancel", json={"reason": "Entered in error"}).status_code == 400

    # Clarify → resubmit → verify; then discontinue blocks further doses.
    o2 = _order(doc, pid)
    assert rx.post(f"/orders/{o2['id']}/pharmacy-decision", json={"decision": "clarify", "note": "Confirm renal dosing"}).json()["status"] == "clarification_needed"
    assert doc.post(f"/orders/{o2['id']}/resubmit", json={"note": "Renal function normal"}).json()["status"] == "pending_verification"
    assert rx.post(f"/orders/{o2['id']}/pharmacy-decision", json={"decision": "verified", "manual_interaction_review": True}).json()["status"] == "active"
    assert doc.post(f"/orders/{o2['id']}/discontinue", json={"note": "Switched to oral"}).json()["status"] == "discontinued"
    assert _dispense(rx, o2).json()["detail"]["code"] == "not_verified"


def test_prn_interval_and_high_alert_witness(as_user):
    doc, rx, rn, rn2 = as_user(DOC), as_user(RX), as_user(RN), as_user(RN2)
    pid = _admitted_patient(as_user, skip=2)
    o = _order(doc, pid, name="Heparin", strength="5,000 units", route="subcutaneous", sig="5,000 units subcut PRN", frequency="prn",
               prn_interval_hours=8)
    rx.post(f"/orders/{o['id']}/pharmacy-decision", json={"decision": "verified", "manual_interaction_review": True})
    label = _dispense(rx, o, name="Heparin", qty=2).json()["dose_label"]
    wristband = rn.get(f"/mar/patients/{pid}").json()["patient"]["wristband"]
    first = _give(rn, o, wristband, label, dose="5,000 units", route="subcutaneous")
    assert first.status_code == 201 and first.json()["requires_witness"] is True  # anticoagulant = high alert
    aid = first.json()["id"]
    assert rn.post(f"/mar/administrations/{aid}/witness").json()["detail"]["code"] == "self_witness"
    assert rn2.post(f"/mar/administrations/{aid}/witness").status_code == 201
    second = _give(rn, o, wristband, label, dose="5,000 units", route="subcutaneous")
    assert second.status_code == 409 and second.json()["detail"]["code"] == "prn_interval"


def test_outpatient_prescription_is_not_on_the_inpatient_loop(as_user):
    doc, rx = as_user(DOC), as_user(RX)
    p = doc.get("/patients", params={"q": "a"}).json()["items"][0]
    o = _order(doc, p["id"], name="Amoxicillin", strength="500 mg", route="oral", sig="1 capsule three times daily", quantity=21, setting="outpatient",
               frequency=None)
    assert o["status"] == "transmitted"
    assert all(x["id"] != o["id"] for x in rx.get("/pharmacy/medication-queue").json())


def test_emar_is_append_only():
    db = SessionLocal()
    try:
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE medication_administrations SET status = 'held' WHERE id = (SELECT id FROM medication_administrations LIMIT 1)"))
            db.execute(text("DELETE FROM medication_administrations"))
        db.rollback()
    finally:
        db.close()
