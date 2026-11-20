"""Revenue expansion: prior auth loop (needed → drafted → checklist → simulated payer → verified closure), claim review
findings gate submission without ever editing the claim, facility charges at discharge."""

import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.engine.monitors import run_monitor
from app.models import Organization


def _run(key):
    db = SessionLocal()
    try:
        run_monitor(db, db.scalar(select(Organization.id).where(Organization.slug == "harborview")), key)
        db.commit()
    finally:
        db.close()


def _patient(front, member):
    r = front.post("/patients", json={"first_name": "Pa", "last_name": f"Case{uuid.uuid4().hex[:5]}", "date_of_birth": "1970-01-01", "sex_at_birth": "female",
                                         "address_line1": "1 Main St", "city": "Port Harbor", "postal_code": "02110", "confirm_not_duplicate": True,
                                         "insurance": {"payer_name": "Bluebay Health (synthetic)", "member_id": member}})
    assert r.status_code == 201, r.text
    return r.json()


def test_prior_auth_loop(as_user):
    front, doc, ins = as_user("frontdesk@harborview.dev"), as_user("dr.santos@harborview.dev"), as_user("insurance@harborview.dev")
    p = _patient(front, f"SYN{uuid.uuid4().int % 10**7:07d}1")
    o = doc.post("/orders", json={"patient_id": p["id"], "order_type": "imaging", "priority": "urgent",
                                  "details": {"code": "70450", "clinical_question": "Persistent headache with new neuro deficit"}}).json()
    doc.post(f"/orders/{o['id']}/sign", json={})
    _run("billing.prior_auth_required")
    case = next(c for c in ins.get("/cases", params={"category": "billing"}).json() if c["subject_id"] == o["id"])
    pa = next(x for x in ins.get("/prior-auths", params={"status": "open"}).json() if x["order_id"] == o["id"])
    assert pa["status"] == "draft" and pa["source"] == "monitor"
    assert ins.post(f"/prior-auths/{pa['id']}/submit").status_code == 400  # checklist incomplete
    for k in ("notes", "insurance"):
        ins.post(f"/prior-auths/{pa['id']}/checklist", json={"key": k, "done": True})
    assert doc.post(f"/prior-auths/{pa['id']}/submit").status_code == 403  # insurance staff work authorizations
    r = ins.post(f"/prior-auths/{pa['id']}/submit").json()
    assert r["status"] == "approved" and r["auth_number"].startswith("SIM-PA-") and r["valid_to"]
    _run("billing.prior_auth_required")
    c = ins.get(f"/cases/{case['id']}").json()["case"]
    assert c["status"] == "resolved" and c["resolution_code"] == "verified_active"


def test_denied_authorization_keeps_case_open(as_user):
    front, doc, ins = as_user("frontdesk@harborview.dev"), as_user("dr.santos@harborview.dev"), as_user("insurance@harborview.dev")
    p = _patient(front, f"SYN{uuid.uuid4().int % 10**7:07d}7")
    o = doc.post("/orders", json={"patient_id": p["id"], "order_type": "imaging", "details": {"code": "72148", "clinical_question": "Chronic low back pain"}}).json()
    doc.post(f"/orders/{o['id']}/sign", json={})
    pa = ins.post("/prior-auths", json={"order_id": o["id"]}).json()
    for k in ("notes", "insurance"):
        ins.post(f"/prior-auths/{pa['id']}/checklist", json={"key": k, "done": True})
    assert ins.post(f"/prior-auths/{pa['id']}/submit").json()["status"] == "denied"
    _run("billing.prior_auth_required")
    case = next(c for c in ins.get("/cases", params={"category": "billing"}).json() if c["subject_id"] == o["id"])
    assert "denied" in case["title"] and case["severity"] == "high"


def test_claim_review_blockers_gate_submission(as_user):
    from tests.test_billing import completed_visit

    doc, bill, admin = as_user("dr.chen@harborview.dev"), as_user("billing@harborview.dev"), as_user("clinicadmin@harborview.dev")
    org = admin.get("/organization").json()
    admin.patch("/organization", json={"name": org["name"], "settings": {**org["settings"], "prior_auth_codes": {"99213": "Test: office visit"}}})
    try:
        eid, _pid = completed_visit(doc, member_id=f"SYN{uuid.uuid4().int % 10**6:06d}1")
        bill.put(f"/encounters/{eid}/charges", json=[{"code": "99213", "diagnosis_codes": ["I10"]}])
        c = bill.post("/claims", json={"encounter_id": eid}).json()
        assert c["status"] == "draft" and any("prior authorization" in e for e in c["scrub_errors"])
        rv = bill.post(f"/claims/{c['id']}/review").json()
        blocker = next(f for f in rv["findings"] if f["code"] == "missing_prior_auth")
        assert blocker["severity"] == "blocker"
        before = bill.get(f"/claims/{c['id']}").json()
        assert [ch["code"] for ch in before["charges"]] == ["99213"]  # review never changes the claim
        assert bill.post(f"/claim-findings/{blocker['id']}", json={"status": "dismissed", "note": "ok"}).status_code == 422
        assert bill.post(f"/claim-findings/{blocker['id']}", json={"status": "resolved", "note": "Payer confirmed no auth needed"}).json()["status"] == "resolved"
    finally:  # remove only our key from the *current* settings (other counters, e.g. mrn_seq, keep advancing)
        cur = admin.get("/organization").json()["settings"]
        cur.pop("prior_auth_codes", None)
        admin.patch("/organization", json={"name": org["name"], "settings": cur})


def test_facility_charges_on_discharge(as_user):
    doc, bedm = as_user("dr.santos@harborview.dev"), as_user("bedmanager@harborview.dev")
    p = _patient(as_user("frontdesk@harborview.dev"), "SYN0000001")
    bed = next(b for u in bedm.get("/adt/board").json()["units"] if u["inpatient"] for b in u["beds"] if b["status"] == "available")
    s = doc.post("/adt/stays", json={"patient_id": p["id"], "reason": "Observation", "bed_id": bed["id"]}).json()
    assert "id" in s, s
    doc.post(f"/adt/stays/{s['id']}/discharge-order", json={"disposition": "home"})
    doc.post(f"/adt/stays/{s['id']}/discharge", json={"override_readiness": True, "override_reason": "Short observation stay"})
    q = as_user("billing@harborview.dev").get("/coding/queue").json()
    row = next(r for r in q if r["encounter_id"] == s["encounter_id"])
    assert "RB-MS" in row["charge_codes"] and "diagnoses" in row["missing"]
