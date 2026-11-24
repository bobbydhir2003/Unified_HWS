"""Orders: role separation, allergy safety checks, simulated transmission, results review/release, isolation."""

DOCTOR, NURSE, PATIENT = "dr.chen@harborview.dev", "nurse.rivera@harborview.dev", "patient@harborview.dev"

AMOX = {"name": "Amoxicillin", "strength": "500 mg", "route": "oral", "sig": "1 capsule three times daily", "quantity": 30, "refills": 0}


def _new_patient(api, last="Ordertest"):
    return api.post("/patients", json={"first_name": "Rx", "last_name": last, "date_of_birth": "1970-01-01", "sex_at_birth": "male",
                                       "confirm_not_duplicate": True}).json()


def test_nurse_drafts_doctor_signs_and_allergy_requires_override(as_user):
    nurse, doc = as_user(NURSE), as_user(DOCTOR)
    p = _new_patient(nurse)
    nurse.post(f"/patients/{p['id']}/allergies", json={"substance": "Penicillin", "severity": "severe", "reaction": "Hives"})
    o = nurse.post("/orders", json={"patient_id": p["id"], "order_type": "medication", "details": AMOX, "indication_codes": ["J02.9"]}).json()
    assert o["status"] == "draft" and o["safety_warnings"][0]["type"] == "allergy"
    assert nurse.post(f"/orders/{o['id']}/sign", json={}).status_code == 403
    r = doc.post(f"/orders/{o['id']}/sign", json={})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "safety_warnings"
    signed = doc.post(f"/orders/{o['id']}/sign", json={"override_reason": "Tolerated amoxicillin in 2024 without reaction"}).json()
    # Outpatient prescription: sent through the simulated e-prescribing channel; signing never marks it "completed".
    assert signed["status"] == "transmitted" and signed["transmission"]["simulated"] is True
    assert signed["safety_override_reason"]
    meds = doc.get(f"/patients/{p['id']}/medications").json()
    assert any(m["name"] == "Amoxicillin" and m["source"] == "prescribed" for m in meds)
    # duplicate therapy now flagged on a second order
    o2 = nurse.post("/orders", json={"patient_id": p["id"], "order_type": "medication", "details": AMOX}).json()
    assert any(w["type"] == "duplicate" for w in o2["safety_warnings"])


def test_order_validation(as_user):
    doc = as_user(DOCTOR)
    p = _new_patient(doc, "Validation")
    assert doc.post("/orders", json={"patient_id": p["id"], "order_type": "lab", "details": {"code": "nope"}}).status_code == 400
    bad = {**AMOX, "quantity": 0}
    assert doc.post("/orders", json={"patient_id": p["id"], "order_type": "medication", "details": bad}).status_code == 422


def test_lab_result_review_and_patient_release(as_user):
    doc, pat = as_user(DOCTOR), as_user(PATIENT)
    pid = pat.membership["patient_id"]
    o = doc.post("/orders", json={"patient_id": pid, "order_type": "lab", "details": {"code": "57698-3"}}).json()
    o = doc.post(f"/orders/{o['id']}/sign", json={}).json()
    assert o["status"] == "transmitted" and o["transmission"]["simulated"]
    assert doc.post(f"/orders/{o['id']}/review").status_code == 400  # nothing resulted yet
    o = doc.post(f"/orders/{o['id']}/simulate-result").json()
    assert o["status"] == "resulted" and len(o["results"]) == 4
    assert any("Result: Lipid panel" in n["title"] for n in doc.get("/notifications").json()["items"])
    assert all(r["order_id"] != o["id"] for r in pat.get(f"/patients/{pid}/results").json())  # not released yet
    assert pat.post(f"/orders/{o['id']}/review").status_code == 403
    o = doc.post(f"/orders/{o['id']}/review", params={"release_to_patient": True}).json()
    assert o["status"] == "completed" and o["released_to_patient_at"]
    assert any(r["order_id"] == o["id"] for r in pat.get(f"/patients/{pid}/results").json())


def test_orders_are_tenant_isolated(as_user):
    doc = as_user(DOCTOR)
    p = _new_patient(doc, "Isolated")
    o = doc.post("/orders", json={"patient_id": p["id"], "order_type": "imaging",
                                  "details": {"code": "71046", "clinical_question": "Cough, rule out pneumonia"}}).json()
    lake = as_user("dr.lake@lakeside.dev", "lakeside")
    assert lake.get(f"/orders/{o['id']}").status_code == 404
    assert lake.post(f"/orders/{o['id']}/sign", json={}).status_code == 404
    assert all(x["id"] != o["id"] for x in lake.get("/orders").json()["items"])
