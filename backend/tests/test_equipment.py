"""Equipment maintenance loop and location par levels."""

from sqlalchemy import select

from app.core.db import SessionLocal
from app.engine.monitors import run_monitor
from app.models import Organization


def _run(key):
    db = SessionLocal()
    try:
        r = run_monitor(db, db.scalar(select(Organization.id).where(Organization.slug == "harborview")), key)
        db.commit()
        assert r.status == "succeeded", r.error
    finally:
        db.close()


def test_maintenance_due_loop(as_user):
    admin = as_user("hospitaladmin@harborview.dev")
    _run("equipment.maintenance_due")
    eq = next(e for e in admin.get("/equipment").json() if e["asset_tag"] == "DF-0101")
    assert eq["overdue"]
    case = next(c for c in admin.get("/cases", params={"category": "equipment"}).json() if c["subject_id"] == eq["id"])
    assert case["severity"] == "high"
    assert admin.post(f"/equipment/{eq['id']}/maintenance", json={"kind": "preventive", "result": "failed", "notes": "Battery fault"}).json()["status"] == "out_of_service"
    ok = admin.post(f"/equipment/{eq['id']}/maintenance", json={"kind": "repair", "result": "repaired", "notes": "Battery replaced"}).json()
    assert ok["status"] == "in_service" and not ok["overdue"]
    _run("equipment.maintenance_due")
    assert admin.get(f"/cases/{case['id']}").json()["case"]["status"] == "resolved"
    assert len(admin.get(f"/equipment/{eq['id']}/maintenance").json()) == 2


def test_below_par_restock_by_transfer(as_user):
    rx = as_user("pharmacist@harborview.dev")
    _run("inventory.below_par")
    short = [p for p in rx.get("/inventory/pars").json() if p["on_hand"] < p["par_level"]]
    assert short
    s = short[0]
    main = next(x for x in rx.get("/inventory/locations").json() if x["code"] == "RX-MAIN")
    lot = next(x for x in rx.get(f"/inventory/items/{s['item_id']}").json()["lots"] if x["location_id"] == main["id"] and not x["expired"])
    rx.post("/inventory/transfer", json={"lot_id": lot["lot_id"], "from_location_id": main["id"], "to_location_id": s["location_id"],
                                         "quantity": s["short"] + 1, "reason": "Restock to par"})
    after = next(p for p in rx.get("/inventory/pars", params={"item_id": s["item_id"]}).json() if p["location_id"] == s["location_id"])
    assert after["on_hand"] >= after["par_level"]
