"""Billing: role gating, charge capture, claim scrub, idempotent submission & payments, denials/appeals, portal pay, isolation."""

import uuid

import pytest
from sqlalchemy import text

from app.core.db import engine

DOCTOR, BILLING, PATIENT = "dr.chen@harborview.dev", "billing@harborview.dev", "patient@harborview.dev"


def completed_visit(doc, member_id="SYN55501", patient_id=None):
    if patient_id is None:
        p = doc.post("/patients", json={"first_name": "Bill", "last_name": f"Able{uuid.uuid4().hex[:5]}", "date_of_birth": "1975-05-05",
                                        "sex_at_birth": "male", "address_line1": "1 Main St", "city": "Port Harbor", "postal_code": "02110",
                                        "confirm_not_duplicate": True,
                                        "insurance": {"payer_name": "Bluebay Health (synthetic)", "member_id": member_id}}).json()
        patient_id = p["id"]
    clinic = next(c for c in doc.membership["clinics"] if c["code"] == "HDT")
    e = doc.post("/encounters", json={"patient_id": patient_id, "clinic_id": clinic["id"], "chief_complaint": "Follow-up"}).json()
    n = doc.post(f"/encounters/{e['id']}/notes", json={}).json()
    n = doc.put(f"/notes/{n['id']}", json={"content": {"subjective": "s", "objective": "o", "assessment": "HTN", "plan": "continue"},
                                           "expected_version": n["current_version"]}).json()
    doc.post(f"/notes/{n['id']}/sign", json={"expected_version": n["current_version"]})
    doc.put(f"/encounters/{e['id']}/diagnoses", json=[{"code": "I10", "description": "Essential hypertension"},
                                                      {"code": "E78.5", "description": "Hyperlipidemia"}])
    assert doc.post(f"/encounters/{e['id']}/complete").json()["status"] == "completed"
    return e["id"], patient_id


def test_billing_requires_billing_role(as_user):
    assert as_user(DOCTOR).get("/claims").status_code == 403
    assert as_user(BILLING).get("/claims").status_code == 200
    assert as_user(PATIENT).get("/billing/summary").status_code == 403


def test_charge_claim_submit_adjudicate_and_patient_payment(as_user):
    doc, bill = as_user(DOCTOR), as_user(BILLING)
    eid, pid = completed_visit(doc)
    cap = bill.get(f"/encounters/{eid}/charges").json()
    assert cap["suggestions"][0]["code"] in ("99203", "99204")  # new patient, 2 diagnoses
    lines = [{"code": s["code"], "units": 1, "diagnosis_codes": s["diagnosis_codes"]} for s in cap["suggestions"]]
    assert bill.put(f"/encounters/{eid}/charges", json=[{"code": "99999", "diagnosis_codes": ["I10"]}]).status_code == 400
    assert bill.put(f"/encounters/{eid}/charges", json=[{"code": "99213", "diagnosis_codes": ["J02.9"]}]).status_code == 400
    bill.put(f"/encounters/{eid}/charges", json=lines)
    c = bill.post("/claims", json={"encounter_id": eid}).json()
    assert c["status"] == "ready" and c["total_charge_cents"] > 0
    assert bill.post(f"/claims/{c['id']}/submit").status_code == 400  # Idempotency-Key required
    key = {"Idempotency-Key": f"submit-{uuid.uuid4()}"}
    first = bill.post(f"/claims/{c['id']}/submit", headers=key).json()
    replay = bill.post(f"/claims/{c['id']}/submit", headers=key).json()
    assert first["status"] == "accepted" and replay["idempotent_replay"] is True and replay["clearinghouse_ref"] == first["clearinghouse_ref"]
    assert bill.get(f"/claims/{c['id']}").json()["submission_count"] == 1
    adj = bill.post(f"/claims/{c['id']}/simulate-adjudication").json()
    if adj["status"] == "denied":
        bill.post(f"/claims/{c['id']}/appeal", json={"text": "Documentation attached supports medical necessity for this visit."})
        adj = bill.post(f"/claims/{c['id']}/simulate-appeal-decision").json()
    assert adj["status"] == "paid"
    assert adj["paid_cents"] + adj["patient_responsibility_cents"] + adj["adjustment_cents"] == adj["total_charge_cents"]
    inv = next(i for i in bill.get(f"/patients/{pid}/billing").json()["invoices"] if i["claim_id"] == c["id"])
    assert inv["balance_cents"] == adj["patient_responsibility_cents"]
    pkey = {"Idempotency-Key": f"pay-{uuid.uuid4()}"}
    assert bill.post(f"/invoices/{inv['id']}/payments", json={"amount_cents": inv["balance_cents"] + 1, "method": "cash"}, headers=pkey).status_code == 400
    r1 = bill.post(f"/invoices/{inv['id']}/payments", json={"amount_cents": 1000, "method": "cash"}, headers=pkey).json()
    r2 = bill.post(f"/invoices/{inv['id']}/payments", json={"amount_cents": 1000, "method": "cash"}, headers=pkey).json()
    assert r2["idempotent_replay"] is True and r2["payment"]["id"] == r1["payment"]["id"]
    assert bill.get(f"/patients/{pid}/billing").json()["balance_cents"] == inv["balance_cents"] - 1000
    summary = bill.get("/billing/summary").json()
    assert summary["payments_mtd"].get("insurance", 0) > 0 and summary["simulated"] is True


def test_inactive_coverage_denial_appeal_upheld_transfers_to_patient(as_user):
    doc, bill = as_user(DOCTOR), as_user(BILLING)
    eid, pid = completed_visit(doc, member_id="SYN55510")
    cap = bill.get(f"/encounters/{eid}/charges").json()
    bill.put(f"/encounters/{eid}/charges", json=[{"code": "99213", "diagnosis_codes": ["I10"]}])
    c = bill.post("/claims", json={"encounter_id": eid}).json()
    bill.post(f"/claims/{c['id']}/submit", headers={"Idempotency-Key": f"submit-{uuid.uuid4()}"})
    d = bill.post(f"/claims/{c['id']}/simulate-adjudication").json()
    assert d["status"] == "denied" and d["denial_code"] == "CO-27"
    assert bill.post(f"/claims/{c['id']}/appeal", json={"text": "short"}).status_code == 422
    bill.post(f"/claims/{c['id']}/appeal", json={"text": "Patient states coverage was active on the date of service; please review."})
    closed = bill.post(f"/claims/{c['id']}/simulate-appeal-decision").json()
    assert closed["status"] == "closed" and closed["patient_responsibility_cents"] == closed["total_charge_cents"]
    invs = bill.get(f"/patients/{pid}/billing").json()["invoices"]
    assert any(i["claim_id"] == c["id"] and i["total_cents"] == c["total_charge_cents"] for i in invs)
    assert cap["encounter"]["id"] == eid


def test_portal_patient_pays_own_bill(as_user):
    doc, bill, pat = as_user(DOCTOR), as_user(BILLING), as_user(PATIENT)
    pid = pat.membership["patient_id"]
    eid, _ = completed_visit(doc, patient_id=pid)
    bill.put(f"/encounters/{eid}/charges", json=[{"code": "99213", "diagnosis_codes": ["I10"]}])
    r = bill.post("/claims", json={"encounter_id": eid})
    if r.status_code == 409:  # no insurance → self-pay invoice
        bill.post(f"/encounters/{eid}/self-pay-invoice")
    else:
        c = r.json()
        bill.post("/claims/{}/rescrub".format(c["id"]))
        bill.post(f"/claims/{c['id']}/submit", headers={"Idempotency-Key": f"s-{uuid.uuid4()}"})
        res = bill.post(f"/claims/{c['id']}/simulate-adjudication").json()
        if res["status"] == "denied":
            bill.post(f"/claims/{c['id']}/appeal", json={"text": "Please reconsider; documentation supports the visit level billed."})
            bill.post(f"/claims/{c['id']}/simulate-appeal-decision")
    bills = pat.get("/portal/bills").json()
    inv = next(i for i in bills["invoices"] if i["status"] == "open")
    paid = pat.post(f"/portal/bills/{inv['id']}/pay", json={"amount_cents": inv["balance_cents"]}, headers={"Idempotency-Key": f"pp-{uuid.uuid4()}"}).json()
    assert paid["invoice"]["status"] == "paid" and paid["payment"]["method"] == "card_simulated"
    assert pat.get("/claims").status_code == 403


def test_charge_amount_integrity_enforced_by_database():
    with pytest.raises(Exception, match="ck_charges_amount"):
        with engine.begin() as conn:
            conn.execute(text("update charges set amount_cents = amount_cents + 1 where id = (select id from charges limit 1)"))


def test_claims_are_tenant_isolated(as_user):
    bill = as_user(BILLING)
    c = bill.get("/claims").json()["items"][0]
    lake = as_user("dr.lake@lakeside.dev", "lakeside")
    assert lake.get(f"/claims/{c['id']}").status_code == 404
    assert lake.post(f"/claims/{c['id']}/submit", headers={"Idempotency-Key": "lake-attempt-1"}).status_code in (403, 404)  # no billing:write there
