"""Cross-department workflows in the real organization, driven by ONE platform Super Admin switching workspaces in the
header. Steps that legally need someone else stay with someone else: clinical signatures with a provider (Dr. Chen,
Dr. Santos), the second lab verification with another technologist, approvals never by the requester. External services
are the built-in simulators; where AI is exercised, only the OpenAI call is MOCKED (labelled)."""
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Organization

ADMIN = "admin@undeclared.dev"


def _new_patient(api, last):
    r = api.post("/patients", json={"first_name": "Ws", "last_name": last, "date_of_birth": "1968-05-05", "sex_at_birth": "female",
                                    "confirm_not_duplicate": True, "address_line1": "1 Pier Rd", "city": "Port Harbor", "state": "MA",
                                    "postal_code": "02110", "insurance": {"payer_name": "Bluebay Health (synthetic)", "member_id": "SYN77771"}})
    assert r.status_code == 201, r.text
    return r.json()


def _book(api, patient_id, minutes=45, reason="Follow-up"):
    clinic = next(c for c in api.membership["clinics"] if c["code"] == "HDT")
    chen = next(p for p in api.get("/providers").json() if "Chen" in p["name"])
    start = datetime.now(ZoneInfo(clinic["timezone"])).replace(second=0, microsecond=0) + timedelta(minutes=minutes)
    for _ in range(40):
        r = api.post("/appointments", json={"patient_id": patient_id, "provider_id": chen["id"], "clinic_id": clinic["id"],
                                            "start_at": start.isoformat(), "end_at": (start + timedelta(minutes=5)).isoformat(),
                                            "override_availability": True, "reason": reason})
        if r.status_code == 201:
            return r.json()
        start += timedelta(minutes=7)
    raise AssertionError(r.text)


def test_visit_lab_and_claim(as_user):
    admin, chen, lab2 = as_user(ADMIN), as_user("dr.chen@harborview.dev"), as_user("lab2@harborview.dev")
    front, nurse, labtech, billing = admin.act("receptionist"), admin.act("nurse"), admin.act("lab_tech"), admin.act("billing")
    p = _new_patient(front, f"Visit{uuid.uuid4().hex[:4]}")
    appt = _book(front, p["id"])
    assert front.post(f"/appointments/{appt['id']}/status", json={"action": "check_in"}).status_code == 200
    assert front.post(f"/appointments/{appt['id']}/status", json={"action": "room", "room": "Exam 2"}).json()["status"] == "roomed"
    assert nurse.post(f"/patients/{p['id']}/vitals", json={"systolic": 146, "diastolic": 90, "heart_rate": 80}).status_code == 201
    enc = chen.post("/encounters", json={"patient_id": p["id"], "appointment_id": appt["id"]}).json()
    n = chen.post(f"/encounters/{enc['id']}/notes", json={"note_type": "progress", "title": "Office visit"}).json()
    n = chen.put(f"/notes/{n['id']}", json={"content": {"subjective": "Headaches", "objective": "BP 146/90", "assessment": "Elevated BP",
                                                        "plan": "Lipid panel"}, "expected_version": n["current_version"]}).json()
    o = chen.post("/orders", json={"patient_id": p["id"], "encounter_id": enc["id"], "order_type": "lab", "details": {"code": "57698-3"}}).json()
    o = chen.post(f"/orders/{o['id']}/sign", json={}).json()
    assert o["transmission"]["simulated"] is True
    item = next(x for x in labtech.get("/lab/worklist").json()["to_collect"] if x["order_id"] == o["id"])
    sp = labtech.post("/lab/collect", json={"order_id": item["order_id"], "specimen_type": "blood"}).json()
    labtech.post(f"/lab/specimens/{sp['id']}/receive")
    rows = [{"name": t["name"], "value": "150", "unit": t["unit"], "reference_range": t["reference_range"]} for t in sp["template"]]
    assert labtech.post(f"/lab/specimens/{sp['id']}/results", json=rows).status_code == 200
    assert admin.post(f"/lab/specimens/{sp['id']}/verify").status_code == 400      # same person, even as Super Admin
    assert lab2.post(f"/lab/specimens/{sp['id']}/verify").json()["status"] == "resulted"
    assert chen.post(f"/orders/{o['id']}/review").status_code == 200
    assert chen.post(f"/notes/{n['id']}/sign", json={"expected_version": n["current_version"]}).status_code == 200
    chen.put(f"/encounters/{enc['id']}/diagnoses", json=[{"code": "R03.0", "description": "Elevated blood-pressure reading"}])
    assert chen.post(f"/encounters/{enc['id']}/complete").json()["status"] == "completed"
    cap = billing.get(f"/encounters/{enc['id']}/charges").json()
    billing.put(f"/encounters/{enc['id']}/charges", json=[{"code": x["code"], "units": 1, "diagnosis_codes": x["diagnosis_codes"]} for x in cap["suggestions"]])
    claim = billing.post("/claims", json={"encounter_id": enc["id"]})
    assert claim.status_code in (200, 201), claim.text
    claim = claim.json()
    assert claim["status"] == "ready", claim.get("scrub_errors")
    sub = billing.post(f"/claims/{claim['id']}/submit", headers={"Idempotency-Key": f"ws-{claim['id']}"})
    assert sub.status_code == 200, sub.text
    chart = admin.act("doctor").get(f"/orders/{o['id']}").json()
    assert chart["results"]


def test_pharmacy_shortage_to_purchase(as_user):
    admin = as_user(ADMIN)
    rx, ha = admin.act("pharmacist"), admin.act("hospital_admin")
    # A new supply item with a reorder point and no stock: the Pharmacy Watchdog monitor must notice it.
    sku = f"WS-{uuid.uuid4().hex[:6]}"
    it = rx.post("/inventory/items", json={"kind": "supply", "name": f"Workspace gauze {sku}", "sku": sku, "reorder_point": 20,
                                          "reorder_qty": 50, "unit_cost_cents": 100})
    assert it.status_code == 201, it.text
    assert admin.post("/monitors/inventory.low_stock/run").status_code == 200
    case = next((c for c in rx.get("/cases", params={"category": "inventory"}).json() if sku in c["title"]), None)
    assert case, "the low-stock monitor opened a case"
    pr = next(x for x in rx.get("/purchase-requests", params={"status": "open"}).json() if x["item_id"] == it.json()["id"])
    assert pr["source"] == "watchdog"
    assert rx.post(f"/purchase-requests/{pr['id']}/decide", json={"approve": True}).status_code == 403  # pharmacists can't approve spend
    assert ha.post(f"/purchase-requests/{pr['id']}/decide", json={"approve": True}).json()["status"] == "approved"
    assert rx.post(f"/purchase-requests/{pr['id']}/order").json()["po_reference"].startswith("SIM-PO-")
    supply = next(x for x in rx.get("/inventory/locations").json() if x["code"] == "SUPPLY")
    r = rx.post("/inventory/receive", json={"item_id": pr["item_id"], "location_id": supply["id"], "lot_number": f"WS-{uuid.uuid4().hex[:5]}",
                                            "expiry_date": "2030-01-01", "quantity": pr["quantity"], "purchase_request_id": pr["id"]})
    assert r.status_code == 201, r.text


def test_insurance_case_ai_proposal_approval_task(as_user, monkeypatch):
    """Case-assist path for real; only the OpenAI structured call is MOCKED."""
    from app.agents import case_assist as CA
    from app.ai import openai_provider
    from app.ai.config import EffectiveAI
    from app.engine.cases import Finding, open_case

    admin = as_user(ADMIN)
    ins = admin.act("insurance_specialist")
    db = SessionLocal()
    org = db.scalar(select(Organization.id).where(Organization.slug == "harborview"))
    case, _ = open_case(db, org, Finding(dedupe_key=f"test.ws:{uuid.uuid4()}", title="Coverage unverified (workspace test)", category="insurance",
                                         kind="insurance.visit_readiness", assign_role="insurance_specialist", evidence={"state": "unverified"}),
                        rule_key="insurance.visit_readiness")
    db.commit()
    fake = EffectiveAI(provider="openai", api_key="sk-test-not-real", text_model="gpt-4.1-mini", source="ui")
    monkeypatch.setattr(CA, "_provider", lambda db, org, agent: (fake, None, None))

    class _Meta:
        input_tokens, output_tokens, cost_usd, model = 100, 30, 0.0001, "gpt-4.1-mini"

    monkeypatch.setattr(openai_provider.OpenAICore, "structured", lambda self, **kw: (CA.Suggestion(
        summary="Coverage unverified; call the patient.", action="create_task", reason="visit soon", task_title="Call patient about coverage (ws)",
        task_role="insurance_specialist", task_priority="high"), _Meta()))
    run = CA.assist(db, case.id, "case_open")
    cid = case.id
    db.close()
    assert run.status == "succeeded" and run.approvals
    r = ins.post(f"/approvals/{run.approvals[0]}/decide", json={"approve": True})
    assert r.status_code == 200 and r.json()["status"] == "executed", r.text
    task = next(t for t in ins.get("/tasks", params={"scope": "all"}).json() if t["title"] == "Call patient about coverage (ws)")
    assert ins.post(f"/tasks/{task['id']}/complete").status_code == 200
    story = {s["key"]: s["status"] for s in ins.get(f"/cases/{cid}").json()["story"]}
    assert story["approval"] == "done" and story["executed"] == "done"
    db = SessionLocal()
    from app.models import Case

    db.get(Case, cid).status = "cancelled"
    db.commit()
    db.close()


def test_emergency_admission_to_discharge(as_user):
    admin, santos = as_user(ADMIN), as_user("dr.santos@harborview.dev")
    nurse, bedm, rx, front = admin.act("nurse"), admin.act("bed_manager"), admin.act("pharmacist"), admin.act("receptionist")
    p = _new_patient(front, f"Ed{uuid.uuid4().hex[:4]}")
    v = nurse.post("/ed/arrivals", json={"patient_id": p["id"], "chief_complaint": "Shortness of breath"})
    assert v.status_code == 201, v.text
    v = v.json()
    nurse.post(f"/ed/visits/{v['id']}/triage", json={"esi_level": 3, "vitals": {"heart_rate": 104, "spo2": 92}})
    bay = next(b for b in nurse.get("/ed/board").json()["bays"] if b["status"] == "available")
    nurse.post(f"/ed/visits/{v['id']}/room", json={"bed_id": bay["id"]})
    santos.post(f"/ed/visits/{v['id']}/assign", json={"me": True})
    adm = santos.post(f"/ed/visits/{v['id']}/disposition", json={"disposition": "admit", "admit_reason": "COPD exacerbation",
                                                                   "level_of_care": "med_surg"}).json()
    assert adm["status"] == "boarding"
    board = bedm.get("/adt/board").json()
    bed = next(b for u in board["units"] if u["inpatient"] for b in u["beds"] if b["status"] == "available")
    assert bedm.post(f"/adt/stays/{adm['stay_id']}/assign-bed", json={"bed_id": bed["id"]}).status_code == 200
    assert nurse.post(f"/adt/stays/{adm['stay_id']}/handoffs", json={"shift": "day", "situation": "On 2L O2"}).status_code == 201
    santos.post(f"/adt/stays/{adm['stay_id']}/discharge-order", json={"disposition": "home"})
    assert rx.post(f"/adt/stays/{adm['stay_id']}/discharge/items/med_rec", json={"status": "done", "note": "Reconciled"}).status_code == 200
    for k in ("transport", "education"):
        assert nurse.post(f"/adt/stays/{adm['stay_id']}/discharge/items/{k}", json={"status": "done"}).status_code == 200
    nurse.post(f"/adt/stays/{adm['stay_id']}/discharge/items/equipment", json={"status": "not_applicable"})
    encs = santos.get(f"/patients/{p['id']}/encounters").json()
    enc = next(e for e in (encs["items"] if isinstance(encs, dict) else encs) if e["encounter_type"] == "inpatient")
    n = santos.post(f"/encounters/{enc['id']}/notes", json={"note_type": "discharge_summary", "title": "Discharge summary"}).json()
    n = santos.put(f"/notes/{n['id']}", json={"content": {"subjective": "Improved", "objective": "SpO2 95%", "assessment": "Resolved",
                                                          "plan": "Prednisone 40 mg daily for 3 more days."}, "expected_version": n["current_version"]}).json()
    assert santos.post(f"/notes/{n['id']}/sign", json={"expected_version": n["current_version"]}).status_code == 200
    dr = santos.post(f"/adt/stays/{adm['stay_id']}/discharge/instructions/draft").json()
    assert admin.act("nurse").post(f"/adt/stays/{adm['stay_id']}/discharge/instructions/approve",
                                   json={"approval_id": dr["approval_id"], "text": dr["text"]}).status_code == 403  # clinicians sign
    santos.post(f"/adt/stays/{adm['stay_id']}/discharge/instructions/approve", json={"approval_id": dr["approval_id"], "text": dr["text"]})
    _book(front, p["id"], minutes=60 * 24 * 6, reason="Post-discharge")
    st = nurse.get(f"/adt/stays/{adm['stay_id']}/discharge").json()["readiness"]
    assert st["ready"], st["blocking"]
    assert nurse.post(f"/adt/stays/{adm['stay_id']}/discharge", json={}).json()["status"] == "discharged"


def test_administration_settings_persist(as_user):
    admin = as_user(ADMIN)
    fac = next(f for f in admin.get("/facilities").json() if f["facility_type"] == "hospital")
    note = f"ws-{uuid.uuid4().hex[:4]}"
    assert admin.patch(f"/facilities/{fac['id']}", json={"settings": {**fac["settings"], "workspace_note": note}}).status_code == 200
    assert next(f for f in admin.get("/facilities").json() if f["id"] == fac["id"])["settings"]["workspace_note"] == note
    code = admin.get("/fee-schedule").json()[0]["code"]
    assert admin.put(f"/fee-schedule/{code}", json={"description": "Edited in workspace test", "price_cents": 4321}).status_code == 200
    assert next(x for x in admin.get("/fee-schedule").json() if x["code"] == code)["price_cents"] == 4321
    mon = admin.get("/monitors").json()[0]["key"]
    assert admin.patch(f"/monitors/{mon}", json={"is_enabled": False}).status_code == 200
    assert next(m for m in admin.get("/monitors").json() if m["key"] == mon)["is_enabled"] is False
    admin.patch(f"/monitors/{mon}", json={"is_enabled": True})
    t = admin.post("/tasks", json={"title": "Review weekend staffing (ws)", "assigned_role": "hospital_admin"}).json()
    assert any(x["id"] == t["id"] for x in admin.act("hospital_admin").get("/tasks").json())
    assert admin.act("hospital_admin").post(f"/tasks/{t['id']}/complete").status_code == 200
    assert admin.post(f"/tasks/{t['id']}/reopen").status_code == 200 and admin.post(f"/tasks/{t['id']}/complete").status_code == 200
