"""Milestone A acceptance: one synthetic patient journey through real APIs.

Registration → appointment → Insurance Guardian detects inactive coverage → staff fixes coverage → payer re-verifies →
case closes → check-in → visit → AI scribe draft → clinician attestation + signature → completion → follow-up task →
charges/claim (simulated clearinghouse). Every step must leave an audit trail.
"""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.db import SessionLocal
from app.engine.monitors import run_monitor
from app.models import Organization


def test_milestone_a_patient_journey(as_user):
    front, doc, ins, bill = (as_user(e) for e in ("frontdesk@harborview.dev", "dr.chen@harborview.dev", "insurance@harborview.dev",
                                                   "billing@harborview.dev"))
    clinic = next(c for c in doc.membership["clinics"] if c["code"] == "HDT")
    chen = next(p for p in front.get("/providers").json() if "Chen" in p["name"])
    # 1. Registration with coverage the payer will report inactive (simulator: member id ending 0).
    tag = uuid.uuid4().hex[:5]
    p = front.post("/patients", json={"first_name": "Journey", "last_name": f"Tester{tag}", "date_of_birth": "1970-07-07",
                                      "sex_at_birth": "female", "confirm_not_duplicate": True, "email": f"journey{tag}@example.com",
                                      "address_line1": "12 Harbor St", "city": "Port Harbor", "state": "MA", "postal_code": "02110",
                                      "insurance": {"payer_name": "Bluebay Health (synthetic)", "member_id": f"SYN{tag}0"}}).json()
    # 2. Appointment later today (the Guardian watches every upcoming visit, including same-day).
    start = datetime.now(ZoneInfo(clinic["timezone"])).replace(second=0, microsecond=0) + timedelta(minutes=45)
    for _ in range(30):
        r = front.post("/appointments", json={"patient_id": p["id"], "provider_id": chen["id"], "clinic_id": clinic["id"], "start_at": start.isoformat(),
                                              "end_at": (start + timedelta(minutes=5)).isoformat(), "override_availability": True, "reason": "Follow-up"})
        if r.status_code == 201:
            break
        start += timedelta(minutes=7)
    appt = r.json()
    # 3. Insurance Guardian (scheduled monitor) verifies with the payer and opens an accountable case.
    db = SessionLocal()
    try:
        org = db.scalar(select(Organization.id).where(Organization.slug == "harborview"))
        run_monitor(db, org, "insurance.visit_readiness")
        db.commit()
    finally:
        db.close()
    case = next(c for c in ins.get("/worklist").json()["cases"] if c["patient_id"] == p["id"])
    assert case["evidence"]["state"] == "verified_inactive" and case["assigned_role"] == "insurance_specialist"
    # 4. Staff follow-up: correct coverage on file, re-check with the payer → the case verifies and closes itself.
    chart = doc.get(f"/patients/{p['id']}").json()
    old = chart["insurances"][0]
    front.put(f"/patients/{p['id']}/insurances/{old['id']}", json={**{k: old[k] for k in ("payer_name", "priority", "subscriber_relation")},
                                                                    "member_id": f"SYN{tag}1", "is_active": True})
    chk = ins.post(f"/patients/{p['id']}/insurances/{old['id']}/eligibility-checks", json={"date_of_service": start.date().isoformat()})
    assert chk.status_code == 201 and chk.json()["result"] == "active"
    closed = ins.get(f"/cases/{case['id']}").json()["case"]
    assert closed["status"] == "resolved" and closed["resolution_code"] == "verified_active"
    # 5. Check-in, visit, AI scribe draft.
    assert front.post(f"/appointments/{appt['id']}/status", json={"action": "check_in"}).status_code == 200
    enc = doc.post("/encounters", json={"patient_id": p["id"], "appointment_id": appt["id"]}).json()
    s = doc.post(f"/encounters/{enc['id']}/scribe", json={"consent_method": "verbal", "consent_confirmed": True}).json()
    doc.post(f"/scribe/{s['id']}/demo")
    s = doc.get(f"/encounters/{enc['id']}/scribe").json()
    assert s["status"] == "ready" and s["draft"]["provider"] in ("simulated", "openai", "anthropic")
    doc.post(f"/scribe/{s['id']}/apply", json={"mode": "replace"})
    note = doc.get(f"/encounters/{enc['id']}").json()["notes"][0]
    # 6. Clinician approval: AI content cannot be signed without explicit attestation.
    assert doc.post(f"/notes/{note['id']}/sign", json={"expected_version": note["current_version"]}).status_code == 422
    assert doc.post(f"/notes/{note['id']}/sign", json={"expected_version": note["current_version"], "attest_ai_reviewed": True}).status_code == 200
    doc.put(f"/encounters/{enc['id']}/diagnoses", json=[{"code": "I10", "description": "Essential hypertension"}])
    doc.patch(f"/encounters/{enc['id']}", json={"follow_up": "Recheck blood pressure in 4 weeks"})
    assert doc.post(f"/encounters/{enc['id']}/complete").json()["status"] == "completed"
    # 7. Follow-up: the automation (outbox → workflow) created a front-desk scheduling task.
    tasks = front.get("/tasks", params={"scope": "all"}).json()
    assert any(t["patient_id"] == p["id"] and "follow-up" in t["title"].lower() for t in tasks)
    # 8. Billing: charge capture → claim → simulated submission (idempotent).
    cap = bill.get(f"/encounters/{enc['id']}/charges").json()
    bill.put(f"/encounters/{enc['id']}/charges", json=[{"code": x["code"], "units": 1, "diagnosis_codes": x["diagnosis_codes"]} for x in cap["suggestions"]])
    claim = bill.post("/claims", json={"encounter_id": enc["id"]}).json()
    sub = bill.post(f"/claims/{claim['id']}/submit", headers={"Idempotency-Key": f"journey-{tag}"})
    assert sub.status_code == 200, sub.text
    # 9. Audit trail covers the journey.
    audit = as_user("clinicadmin@harborview.dev").get("/audit", params={"patient_id": p["id"], "limit": 200}).json()
    actions = {a["action"] for a in audit["items"]}
    assert {"case.opened", "insurance.eligibility_checked", "case.resolved", "appointment.check_in", "encounter.completed"} <= actions
