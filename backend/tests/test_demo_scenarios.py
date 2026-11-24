"""Phase 4: cross-department workflows inside ONE private demo hospital, switching roles like a visitor would.
Everything goes through the real APIs and business logic; external services are the built-in simulators. Where an AI
step is exercised, the OpenAI call itself is MOCKED (labelled below) — live behaviour depends on a configured key."""
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conftest import Visitor
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import DemoSandbox


def _book_today(v: Visitor, patient_id: str, minutes: int = 45, reason: str = "Follow-up"):
    clinic = next(c for c in v.membership["clinics"] if c["code"] == "HDT")
    chen = next(p for p in v.get("/providers").json() if "Chen" in p["name"])
    start = datetime.now(ZoneInfo(clinic["timezone"])).replace(second=0, microsecond=0) + timedelta(minutes=minutes)
    for _ in range(40):
        r = v.post("/appointments", json={"patient_id": patient_id, "provider_id": chen["id"], "clinic_id": clinic["id"],
                                          "start_at": start.isoformat(), "end_at": (start + timedelta(minutes=5)).isoformat(),
                                          "override_availability": True, "reason": reason})
        if r.status_code == 201:
            return r.json()
        start += timedelta(minutes=7)
    raise AssertionError(r.text)


def _new_patient(v: Visitor, last: str):
    r = v.post("/patients", json={"first_name": "Demo", "last_name": last, "date_of_birth": "1968-05-05", "sex_at_birth": "female",
                                  "confirm_not_duplicate": True, "address_line1": "1 Pier Rd", "city": "Port Harbor", "state": "MA",
                                  "postal_code": "02110", "insurance": {"payer_name": "Bluebay Health (synthetic)", "member_id": "SYN77771"}})
    assert r.status_code == 201, r.text
    return r.json()


def test_scenario_a_complete_patient_journey(app, demo):
    v = Visitor(app, "203.0.113.10").enter("front_desk")
    # 1-4. Front desk: register, book, check in, room.
    p = _new_patient(v, f"Journey{uuid.uuid4().hex[:4]}")
    appt = _book_today(v, p["id"])
    assert v.post(f"/appointments/{appt['id']}/status", json={"action": "check_in"}).status_code == 200
    assert v.post(f"/appointments/{appt['id']}/status", json={"action": "room", "room": "Exam 2"}).json()["status"] == "roomed"
    # 5-6. Nurse: vitals.
    v.switch(key="nurse")
    vit = v.post(f"/patients/{p['id']}/vitals", json={"systolic": 148, "diastolic": 92, "heart_rate": 84, "spo2": 98})
    assert vit.status_code == 201, vit.text
    # 7-10. Doctor: chart, visit note, lab order.
    v.switch(key="doctor")
    chart = v.get(f"/patients/{p['id']}").json()
    assert chart["id"] == p["id"] and v.get(f"/patients/{p['id']}/vitals").json()[0]["systolic"] == 148
    enc = v.post("/encounters", json={"patient_id": p["id"], "appointment_id": appt["id"]}).json()
    n = v.post(f"/encounters/{enc['id']}/notes", json={"note_type": "progress", "title": "Office visit"})
    assert n.status_code == 201, n.text
    n = n.json()
    n = v.put(f"/notes/{n['id']}", json={"content": {"subjective": "Headaches", "objective": "BP 148/92", "assessment": "Elevated BP",
                                                     "plan": "Lipid panel; recheck BP"}, "expected_version": n["current_version"]}).json()
    o = v.post("/orders", json={"patient_id": p["id"], "encounter_id": enc["id"], "order_type": "lab", "details": {"code": "57698-3"}}).json()
    o = v.post(f"/orders/{o['id']}/sign", json={}).json()
    assert o["status"] == "transmitted" and o["transmission"]["simulated"] is True
    # 11-13. Laboratory: collect, receive, result; a SECOND technologist verifies (two-person rule kept).
    v.switch(key="lab_tech")
    item = next(x for x in v.get("/lab/worklist").json()["to_collect"] if x["order_id"] == o["id"])
    sp = v.post("/lab/collect", json={"order_id": item["order_id"], "specimen_type": "blood", "container": "Gold top"}).json()
    v.post(f"/lab/specimens/{sp['id']}/receive")
    rows = [{"name": t["name"], "value": "150", "unit": t["unit"], "reference_range": t["reference_range"]} for t in sp["template"]]
    assert v.post(f"/lab/specimens/{sp['id']}/results", json=rows).status_code == 200
    assert v.post(f"/lab/specimens/{sp['id']}/verify").status_code == 400          # same person can't verify
    v.as_person("Marcus Bell")
    assert v.post(f"/lab/specimens/{sp['id']}/verify").json()["status"] == "resulted"
    # 14-15. Doctor: review results, sign the note, diagnose, complete.
    v.switch(key="doctor")
    assert v.post(f"/orders/{o['id']}/review").status_code == 200
    assert v.post(f"/notes/{n['id']}/sign", json={"expected_version": n["current_version"]}).status_code == 200
    v.put(f"/encounters/{enc['id']}/diagnoses", json=[{"code": "R03.0", "description": "Elevated blood-pressure reading"}])
    assert v.post(f"/encounters/{enc['id']}/complete").json()["status"] == "completed"
    # 16-18. Billing: charges → claim → simulated clearinghouse.
    v.switch(key="billing")
    cap = v.get(f"/encounters/{enc['id']}/charges").json()
    v.put(f"/encounters/{enc['id']}/charges", json=[{"code": x["code"], "units": 1, "diagnosis_codes": x["diagnosis_codes"]} for x in cap["suggestions"]])
    claim = v.post("/claims", json={"encounter_id": enc["id"]}).json()
    sub = v.post(f"/claims/{claim['id']}/submit", headers={"Idempotency-Key": f"demo-{claim['id']}"})
    assert sub.status_code == 200, sub.text
    # 19. Connected records: the doctor's chart shows the completed visit and the resulted lab; audit covers the journey.
    v.switch(key="super_admin")
    order = v.get(f"/orders/{o['id']}").json()
    assert order["status"] in ("completed", "resulted", "reviewed") and order["results"]
    actions = {a["action"] for a in v.get("/audit", params={"patient_id": p["id"], "limit": 200}).json()["items"]}
    assert {"appointment.check_in", "encounter.completed"} <= actions


def test_scenario_b_pharmacy_shortage_to_approval(app, demo):
    v = Visitor(app, "203.0.113.20").enter("pharmacist")
    case = next(c for c in v.get("/cases", params={"category": "inventory"}).json() if "IV start kit" in c["title"])
    pr = next(x for x in v.get("/purchase-requests", params={"status": "open"}).json() if x["item"] == "IV start kit")
    assert pr["source"] == "watchdog"
    assert v.post(f"/purchase-requests/{pr['id']}/decide", json={"approve": True}).status_code == 403  # no spending authority
    v.switch(key="hospital_admin")
    assert v.post(f"/purchase-requests/{pr['id']}/decide", json={"approve": True}).json()["status"] == "approved"
    v.switch(key="pharmacist")
    assert v.post(f"/purchase-requests/{pr['id']}/order").json()["po_reference"].startswith("SIM-PO-")  # simulated supplier
    supply = next(x for x in v.get("/inventory/locations").json() if x["code"] == "SUPPLY")
    r = v.post("/inventory/receive", json={"item_id": pr["item_id"], "location_id": supply["id"], "lot_number": "IV-DEMO1",
                                           "expiry_date": "2030-01-01", "quantity": pr["quantity"], "purchase_request_id": pr["id"]})
    assert r.status_code == 201, r.text
    v.switch(key="super_admin")
    assert v.post("/monitors/inventory.low_stock/run").status_code == 200   # the monitor re-checks and verifies
    assert v.get(f"/cases/{case['id']}").json()["case"]["status"] == "resolved"


def test_scenario_c_insurance_with_ai_proposal_and_approval(app, demo, monkeypatch):
    """The case-assist path runs for real; only the OpenAI structured call is MOCKED."""
    from app.agents import case_assist as CA
    from app.ai import openai_provider
    from app.ai.config import EffectiveAI

    v = Visitor(app, "203.0.113.30").enter("insurance_specialist")
    case = next(c for c in v.get("/worklist").json()["cases"] if c["patient_name"] == "Elena Moreau")
    fake = EffectiveAI(provider="openai", api_key="sk-test-not-real", text_model="gpt-4.1-mini", source="owner-demo")
    monkeypatch.setattr(CA, "_provider", lambda db, org, agent: (fake, None, None))

    class _Meta:
        input_tokens, output_tokens, cost_usd, model = 100, 30, 0.0001, "gpt-4.1-mini"

    monkeypatch.setattr(openai_provider.OpenAICore, "structured", lambda self, **kw: (CA.Suggestion(
        summary="Payer reports inactive coverage; ask the specialist to call the patient.", action="create_task",
        reason="Visit soon and coverage inactive", task_title="Call Elena Moreau about her new insurance card",
        task_role="insurance_specialist", task_priority="high"), _Meta()))
    db = SessionLocal()
    run = CA.assist(db, uuid.UUID(case["id"]), "case_open")
    db.close()
    assert run.status == "succeeded" and run.approvals
    detail = v.get(f"/cases/{case['id']}").json()
    assert {s["key"]: s["status"] for s in detail["story"]}["proposed"] == "done"
    r = v.post(f"/approvals/{run.approvals[0]}/decide", json={"approve": True})
    assert r.status_code == 200 and r.json()["status"] == "executed", r.text
    task = next(t for t in v.get("/tasks", params={"scope": "all"}).json() if t["title"].startswith("Call Elena Moreau"))
    assert v.post(f"/tasks/{task['id']}/complete").status_code == 200
    # Patient follow-up in the portal, then the specialist confirms the synthetic card; the payer re-check closes the case.
    v.switch(key="patient")
    assert v.post("/portal/insurance/update", data={"use_sample_card": "true"}).status_code == 201
    v.switch(key="insurance_specialist")
    req = next(x for x in v.get("/insurance/requests").json() if x["patient_name"] == "Elena Moreau")
    body = {"payer_name": req["extracted"]["payer_name"], "member_id": req["extracted"]["member_id"], "plan_name": "PPO Select",
            "attest_reviewed_card": True}
    assert v.post(f"/insurance/requests/{req['id']}/confirm", json=body).json()["status"] == "confirmed"
    final = v.get(f"/cases/{case['id']}").json()
    assert final["case"]["status"] == "resolved"
    assert {s["key"]: s["status"] for s in final["story"]}["verified"] == "done"


def test_scenario_d_emergency_admission_to_discharge(app, demo):
    v = Visitor(app, "203.0.113.40").enter("front_desk")
    p = _new_patient(v, f"Inpatient{uuid.uuid4().hex[:4]}")
    v.switch(key="nurse")
    visit = v.post("/ed/arrivals", json={"patient_id": p["id"], "chief_complaint": "Shortness of breath", "arrival_mode": "walk_in"})
    assert visit.status_code == 201, visit.text
    visit = visit.json()
    v.post(f"/ed/visits/{visit['id']}/triage", json={"esi_level": 3, "vitals": {"heart_rate": 104, "spo2": 92}})
    bay = next(b for b in v.get("/ed/board").json()["bays"] if b["status"] == "available")
    v.post(f"/ed/visits/{visit['id']}/room", json={"bed_id": bay["id"]})
    v.switch(key="doctor")
    v.post(f"/ed/visits/{visit['id']}/assign", json={"me": True})
    adm = v.post(f"/ed/visits/{visit['id']}/disposition", json={"disposition": "admit", "admit_reason": "COPD exacerbation",
                                                                 "level_of_care": "med_surg"}).json()
    assert adm["status"] == "boarding" and adm["stay_id"]
    v.switch(key="bed_manager")
    board = v.get("/adt/board").json()
    bed = next(b for u in board["units"] if u["code"] == "4B" for b in u["beds"] if b["status"] == "available")
    assert v.post(f"/adt/stays/{adm['stay_id']}/assign-bed", json={"bed_id": bed["id"]}).status_code == 200
    v.switch(key="nurse")
    h = v.post(f"/adt/stays/{adm['stay_id']}/handoffs", json={"shift": "day", "situation": "Admitted for COPD exacerbation, on 2L O2"})
    assert h.status_code == 201
    v.switch(key="doctor")
    v.post(f"/adt/stays/{adm['stay_id']}/discharge-order", json={"disposition": "home"})
    st = v.get(f"/adt/stays/{adm['stay_id']}/discharge").json()
    assert not st["readiness"]["ready"] and all(i["task_id"] for i in st["readiness"]["items"])  # discharge tasks created
    v.switch(key="pharmacist")
    assert v.post(f"/adt/stays/{adm['stay_id']}/discharge/items/med_rec", json={"status": "done", "note": "Reconciled"}).status_code == 200
    v.switch(key="nurse")
    for k in ("transport", "education"):
        assert v.post(f"/adt/stays/{adm['stay_id']}/discharge/items/{k}", json={"status": "done"}).status_code == 200
    v.post(f"/adt/stays/{adm['stay_id']}/discharge/items/equipment", json={"status": "not_applicable"})
    v.switch(key="doctor")
    encs = v.get(f"/patients/{p['id']}/encounters").json()
    enc = next(e for e in (encs["items"] if isinstance(encs, dict) else encs) if e["encounter_type"] == "inpatient")
    n = v.post(f"/encounters/{enc['id']}/notes", json={"note_type": "discharge_summary", "title": "Discharge summary"}).json()
    n = v.put(f"/notes/{n['id']}", json={"content": {"subjective": "Improved", "objective": "SpO2 95% RA", "assessment": "COPD exacerbation, resolved",
                                                     "plan": "Prednisone 40 mg daily for 3 more days."}, "expected_version": n["current_version"]}).json()
    assert v.post(f"/notes/{n['id']}/sign", json={"expected_version": n["current_version"]}).status_code == 200
    dr = v.post(f"/adt/stays/{adm['stay_id']}/discharge/instructions/draft").json()
    v.post(f"/adt/stays/{adm['stay_id']}/discharge/instructions/approve", json={"approval_id": dr["approval_id"], "text": dr["text"]})
    v.switch(key="front_desk")
    _book_today(v, p["id"], minutes=60 * 24 * 6, reason="Post-discharge")
    v.switch(key="nurse")
    st = v.get(f"/adt/stays/{adm['stay_id']}/discharge").json()["readiness"]
    assert st["ready"], st["blocking"]
    assert v.post(f"/adt/stays/{adm['stay_id']}/discharge", json={}).json()["status"] == "discharged"


def test_scenario_e_hospital_administration(app, demo):
    v = Visitor(app, "203.0.113.50").enter("super_admin")
    fac = next(f for f in v.get("/facilities").json() if f["facility_type"] == "hospital")
    assert v.patch(f"/facilities/{fac['id']}", json={"settings": {**fac["settings"], "demo_label": "North tower"}}).status_code == 200
    staff = v.get("/staff").json()
    kim = next(s for s in staff if s["last_name"] == "Kim")
    r = v.patch(f"/staff/{kim['membership_id'] if 'membership_id' in kim else kim['id']}", json={"title": "Charge RN"})
    assert r.status_code == 200, r.text
    summary = v.get("/command/summary")
    assert summary.status_code == 200
    cases = v.get("/cases").json()
    assert cases
    c = cases[0]
    bm = next(s for s in staff if s["last_name"] == "Morgan" and "bed_manager" in s["roles"])
    assert v.post(f"/cases/{c['id']}/assign", json={"user_id": bm["user_id"] if "user_id" in bm else bm["id"]}).status_code == 200
    # Assigning to someone outside the hospital is refused.
    assert v.post(f"/cases/{c['id']}/assign", json={"user_id": str(uuid.uuid4())}).status_code == 400
    t = v.post("/tasks", json={"title": "Review weekend staffing", "assigned_role": "hospital_admin"})
    assert t.status_code == 201, t.text
    v.switch(key="hospital_admin")
    assert any(x["id"] == t.json()["id"] for x in v.get("/tasks").json())
    assert v.post(f"/tasks/{t.json()['id']}/complete").status_code == 200
    db = SessionLocal()
    sb = db.scalar(select(DemoSandbox).where(DemoSandbox.organization_id == v.org))
    assert sb.status == "leased"
    db.close()
