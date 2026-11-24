"""Pharmacy & inventory: ledger integrity, expired-lot block, two-person waste approval, Watchdog loops
(expiry → task → approved stock action → verified resolution; low stock → purchase request → approve → receive), verification."""

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.db import SessionLocal
from app.engine.monitors import run_monitor
from app.models import Organization


def _org():
    db = SessionLocal()
    try:
        return db.scalar(select(Organization.id).where(Organization.slug == "harborview"))
    finally:
        db.close()


def _run(key):
    db = SessionLocal()
    try:
        run_monitor(db, _org(), key)
        db.commit()
    finally:
        db.close()


def _lot(api, sku_name, lot_prefix=None):
    it = next(i for i in api.get("/inventory/items").json() if i["name"] == sku_name)
    d = api.get(f"/inventory/items/{it['id']}").json()
    lots = [x for x in d["lots"] if not lot_prefix or x["lot_number"].startswith(lot_prefix)]
    return it, lots[0]


def test_ledger_db_invariants():
    db = SessionLocal()
    try:
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE stock_balances SET quantity = -1 WHERE id = (SELECT id FROM stock_balances LIMIT 1)"))
        db.rollback()
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE stock_movements SET quantity = 999 WHERE id = (SELECT id FROM stock_movements LIMIT 1)"))
        db.rollback()
    finally:
        db.close()


def test_expired_heparin_waste_needs_second_pharmacist_and_case_verifies(as_user):
    rx, rx2, doc = as_user("pharmacist@harborview.dev"), as_user("pharmacist2@harborview.dev"), as_user("dr.santos@harborview.dev")
    _run("pharmacy.expiring")
    case = next(c for c in rx.get("/cases", params={"category": "pharmacy"}).json() if "EXPIRED Heparin" in c["title"])
    assert case["severity"] == "high" and case["assigned_role"] == "pharmacist"
    it, lot = _lot(rx, "Heparin", "HEP-X")
    assert lot["expired"]
    # Dispensing an expired lot is refused.
    r = rx.post("/inventory/dispense", json={"lot_id": lot["lot_id"], "location_id": lot["location_id"], "quantity": 1})
    assert r.status_code == 400 and "expired" in r.text
    # Waste → approval request; requester can't approve; doctors can't; a second pharmacist can.
    w = rx.post("/inventory/adjust", json={"lot_id": lot["lot_id"], "location_id": lot["location_id"], "quantity": lot["quantity"], "action": "waste",
                                           "reason": "Expired — removed from ICU med room", "case_id": case["id"]}).json()
    assert w["status"] == "pending_approval"
    assert rx.post(f"/approvals/{w['approval_id']}/decide", json={"approve": True}).status_code == 400
    assert doc.post(f"/approvals/{w['approval_id']}/decide", json={"approve": True}).status_code == 400
    ok = rx2.post(f"/approvals/{w['approval_id']}/decide", json={"approve": True}).json()
    assert ok["status"] == "executed" and ok["result"]["balance_after"] == 0
    _run("pharmacy.expiring")
    c = rx.get(f"/cases/{case['id']}").json()
    assert c["case"]["status"] == "resolved" and c["case"]["resolution_code"] == "verified_active"
    moves = rx.get(f"/inventory/items/{it['id']}").json()["movements"]
    assert moves[0]["kind"] == "waste" and moves[0]["approved"]


def test_low_stock_purchase_loop(as_user):
    rx, admin = as_user("pharmacist@harborview.dev"), as_user("hospitaladmin@harborview.dev")
    _run("inventory.low_stock")
    case = next(c for c in rx.get("/cases", params={"category": "inventory"}).json() if "IV start kit" in c["title"])
    pr = next(p for p in rx.get("/purchase-requests", params={"status": "open"}).json() if p["item"] == "IV start kit")
    assert pr["source"] == "watchdog" and pr["quantity"] >= 120 and pr["recommendation"]["method"]
    assert rx.post(f"/purchase-requests/{pr['id']}/decide", json={"approve": True}).status_code == 403  # pharmacists can't approve spend
    assert admin.post(f"/purchase-requests/{pr['id']}/decide", json={"approve": True}).json()["status"] == "approved"
    assert rx.post(f"/purchase-requests/{pr['id']}/order").json()["po_reference"].startswith("SIM-PO-")
    supply = next(x for x in rx.get("/inventory/locations").json() if x["code"] == "SUPPLY")
    r = rx.post("/inventory/receive", json={"item_id": pr["item_id"], "location_id": supply["id"], "lot_number": f"IV-{uuid.uuid4().hex[:5]}",
                                            "expiry_date": "2030-01-01", "quantity": pr["quantity"], "purchase_request_id": pr["id"]})
    assert r.status_code == 201
    assert next(p for p in rx.get("/purchase-requests").json() if p["id"] == pr["id"])["status"] == "received"
    _run("inventory.low_stock")
    assert rx.get(f"/cases/{case['id']}").json()["case"]["status"] == "resolved"


def test_stock_rules_and_verification(as_user):
    rx, doc, nurse = as_user("pharmacist@harborview.dev"), as_user("dr.santos@harborview.dev"), as_user("nurse.kim@harborview.dev")
    it, lot = _lot(rx, "Ceftriaxone")
    assert rx.post("/inventory/dispense", json={"lot_id": lot["lot_id"], "location_id": lot["location_id"], "quantity": lot["quantity"] + 1}).status_code == 400
    assert nurse.post("/inventory/dispense", json={"lot_id": lot["lot_id"], "location_id": lot["location_id"], "quantity": 1}).status_code == 403
    assert rx.post("/inventory/receive", json={"item_id": it["id"], "location_id": lot["location_id"], "lot_number": "NOEXP", "quantity": 5}).status_code == 400
    q = rx.get("/pharmacy/verifications").json()
    assert q, "expected seeded inpatient medication orders"
    assert doc.post("/pharmacy/verifications", json={"order_id": q[0]["order_id"], "status": "verified"}).status_code == 403
    assert rx.post("/pharmacy/verifications", json={"order_id": q[0]["order_id"], "status": "rejected"}).status_code == 400  # note required
    # Interaction screening is unavailable (no licensed knowledge base), so verifying needs an explicit manual review.
    assert rx.post("/pharmacy/verifications", json={"order_id": q[0]["order_id"], "status": "verified"}).status_code == 409
    assert rx.post("/pharmacy/verifications", json={"order_id": q[0]["order_id"], "status": "verified",
                                                    "manual_interaction_review": True}).status_code == 201
    assert all(x["order_id"] != q[0]["order_id"] for x in rx.get("/pharmacy/verifications").json())
