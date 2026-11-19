"""Inpatient ADT + bed invariants: DB-level double-occupancy prevention, one active stay, transitions, housekeeping, permissions."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.db import SessionLocal
from app.core.security import now
from app.models import BedAssignment, Location


def _new_patient(api):
    tag = uuid.uuid4().hex[:6]
    return api.post("/patients", json={"first_name": "Inpt", "last_name": f"Case{tag}", "date_of_birth": "1960-01-01",
                                       "sex_at_birth": "male", "confirm_not_duplicate": True}).json()


def _free_beds(api, n=2, unit="4B"):
    board = api.get("/adt/board").json()
    beds = [b for u in board["units"] if u["code"] == unit for b in u["beds"] if b["status"] == "available"]
    assert len(beds) >= n
    return beds[:n]


def test_database_rejects_double_occupancy():
    db = SessionLocal()
    try:
        a = db.scalar(select(BedAssignment).where(BedAssignment.end_at.is_(None)))
        db.add(BedAssignment(organization_id=a.organization_id, stay_id=uuid.uuid4(), bed_id=a.bed_id, patient_id=a.patient_id,
                             start_at=now() - timedelta(minutes=5)))
        with pytest.raises(IntegrityError):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_admit_transfer_discharge_flow(as_user):
    doc, bedm, nurse = as_user("dr.santos@harborview.dev"), as_user("bedmanager@harborview.dev"), as_user("nurse.kim@harborview.dev")
    p = _new_patient(as_user("frontdesk@harborview.dev"))
    b1, b2 = _free_beds(bedm)
    stay = doc.post("/adt/stays", json={"patient_id": p["id"], "reason": "Cellulitis, IV antibiotics"}).json()
    assert stay["status"] == "pending"
    assert doc.post("/adt/stays", json={"patient_id": p["id"], "reason": "Duplicate request"}).status_code == 400  # one active stay
    # Pharmacist can't place patients; bed manager can.
    assert as_user("pharmacist@harborview.dev").post(f"/adt/stays/{stay['id']}/assign-bed", json={"bed_id": b1["id"]}).status_code == 403
    s = bedm.post(f"/adt/stays/{stay['id']}/assign-bed", json={"bed_id": b1["id"]}).json()
    assert s["status"] == "admitted" and s["bed"]["id"] == b1["id"]
    # Another patient cannot take the occupied bed.
    other = doc.post("/adt/stays", json={"patient_id": _new_patient(as_user("frontdesk@harborview.dev"))["id"], "reason": "Observation"}).json()
    assert bedm.post(f"/adt/stays/{other['id']}/assign-bed", json={"bed_id": b1["id"]}).status_code == 400
    bedm.post(f"/adt/stays/{other['id']}/cancel", json={"reason": "Admitted elsewhere"})
    # Transfer: old bed goes to cleaning with a housekeeping task; can't mark an occupied bed available.
    t = nurse.post(f"/adt/stays/{stay['id']}/transfer", json={"bed_id": b2["id"], "note": "Isolation room needed"}).json()
    assert t["bed"]["id"] == b2["id"]
    board = bedm.get("/adt/board").json()
    status = {b["id"]: b["status"] for u in board["units"] for b in u["beds"]}
    assert status[b1["id"]] == "cleaning" and status[b2["id"]] == "occupied"
    assert any(x["kind"] == "evs.clean_bed" and b1["code"] in x["title"] for x in bedm.get("/tasks", params={"scope": "all"}).json())
    assert bedm.post(f"/beds/{b2['id']}/status", json={"to": "available"}).status_code == 400
    assert bedm.post(f"/beds/{b1['id']}/status", json={"to": "available"}).json()["status"] == "available"
    assert not any(x["kind"] == "evs.clean_bed" and b1["code"] in x["title"] for x in bedm.get("/tasks", params={"scope": "all"}).json())
    # Discharge needs a physician order; nurses can't order it.
    assert nurse.post(f"/adt/stays/{stay['id']}/discharge", json={}).status_code == 400
    assert nurse.post(f"/adt/stays/{stay['id']}/discharge-order", json={"disposition": "home"}).status_code == 403
    assert doc.post(f"/adt/stays/{stay['id']}/discharge-order", json={"disposition": "home"}).json()["status"] == "discharge_ordered"
    blocked = nurse.post(f"/adt/stays/{stay['id']}/discharge", json={})
    assert blocked.status_code == 400 and "checklist incomplete" in blocked.text  # discharge plan created by the coordinator
    assert nurse.post(f"/adt/stays/{stay['id']}/discharge", json={"override_readiness": True}).status_code == 400  # reason required
    d = nurse.post(f"/adt/stays/{stay['id']}/discharge", json={"override_readiness": True, "override_reason": "Transferred to outside facility per family"}).json()
    assert d["status"] == "discharged"
    detail = doc.get(f"/adt/stays/{stay['id']}").json()
    assert [e["kind"] for e in detail["events"]] == ["admission_requested", "admitted", "transferred", "discharge_ordered", "discharged"]
    assert len(detail["movements"]) == 2 and all(m["end_at"] for m in detail["movements"])


def test_board_counts_are_consistent(as_user):
    board = as_user("bedmanager@harborview.dev").get("/adt/board").json()
    for u in board["units"]:
        assert sum(u["counts"].values()) == len(u["beds"])
        assert u["counts"]["occupied"] == sum(1 for b in u["beds"] if b["stay"])
    assert as_user("dr.lake@lakeside.dev", "lakeside").get("/adt/board").status_code == 404


def test_blocking_needs_reason(as_user):
    bedm = as_user("bedmanager@harborview.dev")
    b = _free_beds(bedm, 1, "4C")[0]
    assert bedm.post(f"/beds/{b['id']}/status", json={"to": "blocked"}).status_code == 400
    assert bedm.post(f"/beds/{b['id']}/status", json={"to": "blocked", "reason": "Oxygen outlet broken"}).json()["status"] == "blocked"
    bedm.post(f"/beds/{b['id']}/status", json={"to": "available"})
    db = SessionLocal()
    try:
        assert db.get(Location, uuid.UUID(b["id"])).bed_status == "available"
    finally:
        db.close()
