"""Milestone C completion: one synthetic patient through the real application, across departments, via the public API.

1 ED arrival → 2 assessment + admission request → 3 bed assignment → 4 Command Center updates → 5 pharmacy shortage alert →
6 automation engine assigns it to pharmacy → 7 discharge approaches → 8 missing discharge tasks identified →
9 departments complete them → 10 discharge → 11 insurance & billing updated → 12 Hospital Operations Agent source-backed
summary → 13 every action and approval in the audit trail. Synthetic data only; no step is mocked."""

import re
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.db import SessionLocal
from app.engine.monitors import run_monitor
from app.models import Organization

AUDIT_ACTIONS: list[str] = []


def _run_monitor(key):
    db = SessionLocal()
    try:
        run_monitor(db, db.scalar(select(Organization.id).where(Organization.slug == "harborview")), key)
        db.commit()
    finally:
        db.close()


def _tiles(api):
    return {t["key"]: t["value"] for t in api.get("/command/summary").json()["hospital"]["tiles"]}


def test_synthetic_hospital_end_to_end(as_user):
    nurse, doc, bedm, front, rx, rx2, billing, admin = (as_user(e) for e in (
        "nurse.kim@harborview.dev", "dr.santos@harborview.dev", "bedmanager@harborview.dev", "frontdesk@harborview.dev",
        "pharmacist@harborview.dev", "pharmacist2@harborview.dev", "billing@harborview.dev", "hospitaladmin@harborview.dev"))
    tag = uuid.uuid4().hex[:6]
    p = front.post("/patients", json={"first_name": "Demo", "last_name": f"Journey{tag}", "date_of_birth": "1961-04-12", "sex_at_birth": "male",
                                      "address_line1": "1 Harbor Way", "city": "Port Harbor", "postal_code": "02110", "confirm_not_duplicate": True,
                                      "insurance": {"payer_name": "Bluebay Health (synthetic)", "member_id": f"SYN{tag}1"}})
    assert p.status_code == 201, p.text
    p = p.json()
    before = _tiles(admin)

    # 1. ED arrival.
    v = nurse.post("/ed/arrivals", json={"patient_id": p["id"], "chief_complaint": "Shortness of breath", "arrival_mode": "walk_in"})
    assert v.status_code == 201, v.text
    v = v.json()
    assert _tiles(admin)["ed"] == before["ed"] + 1

    # 2. Nurse assessment (triage with vitals), physician evaluates and requests admission.
    t = nurse.post(f"/ed/visits/{v['id']}/triage", json={"esi_level": 3, "vitals": {"heart_rate": 104, "spo2": 90, "resp_rate": 24}})
    assert t.status_code == 200 and t.json()["status"] == "triaged", t.text
    bay = next(b for b in nurse.get("/ed/board").json()["bays"] if b["status"] == "available")
    assert nurse.post(f"/ed/visits/{v['id']}/room", json={"bed_id": bay["id"]}).status_code == 200
    assert doc.post(f"/ed/visits/{v['id']}/assign", json={"me": True}).status_code == 200
    adm = doc.post(f"/ed/visits/{v['id']}/disposition", json={"disposition": "admit", "admit_reason": "COPD exacerbation", "level_of_care": "med_surg"})
    assert adm.status_code == 200, adm.text
    adm = adm.json()
    assert adm["status"] == "boarding" and adm["stay_id"]
    assert _tiles(admin)["pending_admits"] == before["pending_admits"] + 1

    # 3. Bed management assigns an available bed (ED visit ends, bay goes to cleaning).
    bed = next(b for u in bedm.get("/adt/board").json()["units"] if u["code"] == "4C" for b in u["beds"] if b["status"] == "available")
    assert bedm.post(f"/adt/stays/{adm['stay_id']}/assign-bed", json={"bed_id": bed["id"]}).status_code == 200
    assert doc.get(f"/ed/visits/{v['id']}").json()["status"] == "departed"

    # 4. Command Center reflects it (same numbers the bed board shows).
    after = _tiles(admin)
    assert after["inpatients"] == before["inpatients"] + 1
    assert after["pending_admits"] == before["pending_admits"]
    board = bedm.get("/adt/board").json()
    assert after["beds"] == board["totals"]["available"] and after["beds"] < before["beds"]  # inpatient bed taken; ED bay now cleaning
    assert next(b for u in board["units"] for b in u["beds"] if b["id"] == bed["id"])["status"] == "occupied"

    # 5. Pharmacy inventory generates a shortage alert (a ward stock item falls below its reorder point).
    item = rx.post("/inventory/items", json={"kind": "medication", "name": f"Ipratropium neb {tag}", "sku": f"IPR-{tag}", "unit": "vial",
                                             "reorder_point": 40, "reorder_qty": 120, "unit_cost_cents": 150})
    assert item.status_code == 201, item.text
    item_id = item.json()["id"]
    loc = next(x for x in rx.get("/inventory/locations").json() if x["code"] == "SUPPLY")
    assert rx.post("/inventory/receive", json={"item_id": item_id, "location_id": loc["id"], "lot_number": f"IPR-{tag}",
                                               "expiry_date": "2030-01-01", "quantity": 12}).status_code == 201
    _run_monitor("inventory.low_stock")

    # 6. The shared automation engine routes it to pharmacy staff, with a purchase request awaiting a second person.
    case = next(c for c in rx.get("/cases", params={"category": "pharmacy"}).json() if f"Ipratropium neb {tag}" in c["title"])
    assert case["assigned_role"] == "pharmacist" and case["status"] in ("open", "in_progress")
    assert _tiles(admin)["pharmacy"] >= before["pharmacy"] + 1
    pr = next(x for x in rx.get("/purchase-requests", params={"status": "open"}).json() if x["item_id"] == item_id)
    assert rx.post(f"/purchase-requests/{pr['id']}/decide", json={"approve": True}).status_code == 403  # requester-side role can't approve spend
    assert admin.post(f"/purchase-requests/{pr['id']}/decide", json={"approve": True}).json()["status"] == "approved"

    # 7. The patient approaches discharge: physician writes the discharge order.
    stay_id = adm["stay_id"]
    assert doc.post(f"/adt/stays/{stay_id}/discharge-order", json={"disposition": "home"}).status_code == 200
    assert _tiles(admin)["discharges"] == before["discharges"] + 1

    # 8. Missing discharge tasks are identified, each with an owner task.
    st = doc.get(f"/adt/stays/{stay_id}/discharge").json()
    assert not st["readiness"]["ready"] and st["readiness"]["blocking"]
    items = {i["key"]: i for i in st["readiness"]["items"]}
    assert {"med_rec", "transport", "education", "follow_up", "documentation", "instructions"} <= set(items)
    assert all(i["task_id"] for i in items.values())
    # A premature discharge is refused while items are open.
    assert nurse.post(f"/adt/stays/{stay_id}/discharge", json={}).status_code == 400

    # 9. Departments complete their tasks (owners only; data-verified items close from real records).
    assert front.post(f"/adt/stays/{stay_id}/discharge/items/med_rec", json={"status": "done"}).status_code == 400
    assert rx.post(f"/adt/stays/{stay_id}/discharge/items/med_rec", json={"status": "done", "note": "Home meds reconciled"}).status_code == 200
    for k in ("transport", "education"):
        assert nurse.post(f"/adt/stays/{stay_id}/discharge/items/{k}", json={"status": "done"}).status_code == 200
    if "equipment" in items:
        assert nurse.post(f"/adt/stays/{stay_id}/discharge/items/equipment", json={"status": "not_applicable"}).status_code == 200
    encs = doc.get(f"/patients/{p['id']}/encounters").json()
    enc = next(e for e in (encs["items"] if isinstance(encs, dict) else encs) if e["encounter_type"] == "inpatient")
    n = doc.post(f"/encounters/{enc['id']}/notes", json={"note_type": "discharge_summary", "title": "Discharge summary"}).json()
    n = doc.put(f"/notes/{n['id']}", json={"content": {"subjective": "Breathing easier", "objective": "SpO2 95% RA", "assessment": "COPD exacerbation, improved",
                                                       "plan": "Prednisone 40 mg daily for 3 more days. Use inhaler as prescribed."},
                                           "expected_version": n["current_version"]}).json()
    assert doc.post(f"/notes/{n['id']}/sign", json={"expected_version": n["current_version"]}).status_code == 200
    dr = doc.post(f"/adt/stays/{stay_id}/discharge/instructions/draft").json()
    assert nurse.post(f"/adt/stays/{stay_id}/discharge/instructions/approve", json={"approval_id": dr["approval_id"], "text": dr["text"]}).status_code == 403
    assert doc.post(f"/adt/stays/{stay_id}/discharge/instructions/approve", json={"approval_id": dr["approval_id"], "text": dr["text"]}).status_code == 200
    clinic = next(c for c in front.membership["clinics"] if c["code"] == "HDT")
    chen = next(x for x in front.get("/providers").json() if "Chen" in x["name"])
    start = datetime.now(ZoneInfo(clinic["timezone"])).replace(second=0, microsecond=0) + timedelta(days=7, minutes=11)
    for _ in range(30):
        r = front.post("/appointments", json={"patient_id": p["id"], "provider_id": chen["id"], "clinic_id": clinic["id"], "start_at": start.isoformat(),
                                              "end_at": (start + timedelta(minutes=5)).isoformat(), "override_availability": True, "reason": "Post-discharge"})
        if r.status_code == 201:
            break
        start += timedelta(minutes=7)
    assert r.status_code == 201, r.text
    st = nurse.get(f"/adt/stays/{stay_id}/discharge").json()["readiness"]
    assert st["ready"], st["blocking"]

    # 10. Discharge.
    d = nurse.post(f"/adt/stays/{stay_id}/discharge", json={})
    assert d.status_code == 200 and d.json()["status"] == "discharged", d.text
    end = _tiles(admin)
    assert end["inpatients"] == before["inpatients"] and end["discharges"] == before["discharges"]

    # 11. Insurance and billing: facility charges captured on discharge (handler on adt.discharged), visible in the coding
    # queue with what's still missing before a claim can go out; the patient journey shows the whole path.
    row = next(x for x in billing.get("/coding/queue").json() if x["encounter_id"] == enc["id"])
    assert row["charge_codes"] and "missing" in row
    j = doc.get(f"/patients/{p['id']}/journey").json()["events"]
    kinds = {e["kind"] for e in j}
    assert {"ed", "adt", "encounter", "appointment"} <= kinds

    # 12. Hospital Operations Agent: summary built only from tool results (operations numbers with sources + cited cases).
    run = admin.post("/agents/hospital_operations/run", json={"input": "Summarize current hospital operations for the shift lead."})
    assert run.status_code == 200, run.text
    run = run.json()
    assert run["status"] == "succeeded" and run["tool_calls"]
    assert {c["tool"] for c in run["tool_calls"]} >= {"get_operations_summary"}
    assert "Operations:" in run["output"] or run["mode"] == "openai"
    assert re.search(r"\[C\d+\]", run["output"]) or "0 open" in run["output"]
    brief = admin.get("/reports/briefing").json()
    assert all(m["source"] for m in brief["metrics"])

    # 13. Every action and approval for this journey is in the audit trail.
    audit = as_user("clinicadmin@harborview.dev")
    pat_actions = {a["action"] for a in audit.get("/audit", params={"patient_id": p["id"], "page_size": 200}).json()["items"]}
    AUDIT_ACTIONS[:] = sorted(pat_actions)
    all_actions = {a["action"] for a in audit.get("/audit", params={"page_size": 200}).json()["items"]}
    assert {
        "patient.created", "ed.arrival", "ed.triage", "ed.roomed", "ed.provider_assigned", "ed.admit_requested",  # steps 1-2
        "adt.admission_requested", "adt.admitted", "ed.departed",                                                # step 3
        "adt.discharge_ordered", "discharge.plan_created", "discharge.item_updated",                            # steps 7-9
        "note.signed", "discharge.instructions_drafted", "approval.requested", "approval.executed",              # step 9 approvals
        "appointment.created", "adt.discharged", "patient.journey_viewed",                                      # steps 9-11
    } <= pat_actions, sorted(pat_actions)
    assert {"agent.run", "inventory.item_created", "inventory.received", "procurement.approved"} <= all_actions  # steps 5-6, 12
