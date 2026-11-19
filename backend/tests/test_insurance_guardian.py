"""Insurance Guardian: detection → assignment → patient follow-up → staff confirmation → payer re-verification → closure."""

from datetime import date, timedelta

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.engine.monitors import run_monitor
from app.models import Case, NotificationDelivery, Organization, PatientInsurance
from app.services.insurance import coverage_state, run_check


def _cases(api, **params):
    return api.get("/cases", params={"category": "insurance", **params}).json()


def test_reruns_never_duplicate_cases_or_reminders():
    db = SessionLocal()
    try:
        org = db.scalar(select(Organization.id).where(Organization.slug == "harborview"))
        run_monitor(db, org, "insurance.visit_readiness")  # settle any changes made by earlier tests
        run_monitor(db, org, "insurance.stored_end_date")
        db.commit()
        before = (db.scalar(select(func.count()).select_from(Case)), db.scalar(select(func.count()).select_from(NotificationDelivery)))
        for _ in range(3):
            run_monitor(db, org, "insurance.visit_readiness")
            run_monitor(db, org, "insurance.stored_end_date")
        db.commit()
        after = (db.scalar(select(func.count()).select_from(Case)), db.scalar(select(func.count()).select_from(NotificationDelivery)))
        assert before == after
    finally:
        db.close()


def test_stored_end_date_is_never_treated_as_proof():
    db = SessionLocal()
    try:
        ins = db.scalar(select(PatientInsurance).where(PatientInsurance.is_active.is_(True), PatientInsurance.member_id.like("SYN%1")))
        ins.termination_date = date.today() - timedelta(days=10)  # entered date says "ended"
        db.flush()
        run_check(db, ins, dos=date.today(), trigger="staff", actor_id=None, emit_event=False)
        assert coverage_state(db, ins.patient_id, date.today()).state == "verified_active"  # payer says active → active
        db.rollback()
    finally:
        db.close()


def test_full_guardian_loop_portal_to_resolution(as_user):
    ins_staff = as_user("insurance@harborview.dev")
    patient = as_user("patient@harborview.dev")
    # Detected + assigned: Elena's payer reports inactive coverage; the case is on the insurance specialist's worklist.
    mine = [c for c in ins_staff.get("/worklist").json()["cases"] if c["patient_name"] == "Elena Moreau"]
    assert len(mine) == 1 and mine[0]["evidence"]["state"] == "verified_inactive"
    case_id = mine[0]["id"]
    assert "inactive" in mine[0]["title"].lower()
    # Patient was asked in the portal (request + reminder delivered once).
    portal = patient.get("/portal/insurance").json()
    assert [r["status"] for r in portal["requests"]] == ["requested"]
    # Patient uploads a (synthetic) card → staff confirmation task; case waits.
    r = patient.post("/portal/insurance/update", data={"use_sample_card": "true", "member_id": "TYPO123"})
    assert r.status_code == 201, r.text
    detail = ins_staff.get(f"/cases/{case_id}").json()
    assert detail["case"]["status"] == "waiting" and any(t["kind"] == "insurance.confirm_card" for t in detail["tasks"])
    req = next(x for x in ins_staff.get("/insurance/requests").json() if x["patient_name"] == "Elena Moreau")
    assert req["extracted"].get("member_id", "").startswith("HMH")  # read from the card (draft only)
    assert "member_id" in req["discrepancies"]  # typed value differs from the card
    # Doctors can't confirm coverage; confirmation requires attestation.
    assert as_user("dr.chen@harborview.dev").post(f"/insurance/requests/{req['id']}/confirm", json={}).status_code == 403
    body = {"payer_name": req["extracted"]["payer_name"], "member_id": req["extracted"]["member_id"], "plan_name": "PPO Select"}
    assert ins_staff.post(f"/insurance/requests/{req['id']}/confirm", json=body).status_code == 400
    done = ins_staff.post(f"/insurance/requests/{req['id']}/confirm", json={**body, "attest_reviewed_card": True})
    assert done.status_code == 200 and done.json()["status"] == "confirmed"
    # Verify: payer re-check is active → the monitor closes the case automatically, with evidence.
    detail = ins_staff.get(f"/cases/{case_id}").json()
    assert detail["case"]["status"] == "resolved" and detail["case"]["resolution_code"] == "verified_active"
    kinds = [e["kind"] for e in detail["events"]]
    assert kinds[0] == "created" and "patient_submitted" in kinds and "coverage_confirmed" in kinds and kinds[-1] == "resolved"
    assert all(t["status"] in ("done", "cancelled") for t in detail["tasks"])
    cov = ins_staff.get(f"/patients/{detail['case']['patient_id']}/coverage").json()
    assert cov["state"] == "verified_active" and cov["simulated"] is True
    # Audit trail covers each step.
    audit = as_user("clinicadmin@harborview.dev").get("/audit", params={"patient_id": detail["case"]["patient_id"], "limit": 200}).json()
    actions = {a["action"] for a in audit["items"]}
    assert {"case.opened", "portal.insurance_submitted", "insurance.update_confirmed", "insurance.eligibility_checked", "case.resolved"} <= actions


def test_staff_override_clears_single_visit_case(as_user):
    staff = as_user("frontdesk@harborview.dev")
    case = next(c for c in _cases(as_user("insurance@harborview.dev")) if len(c["evidence"].get("visits", [])) == 1)
    appt = case["evidence"]["visits"][0]["appointment_id"]
    assert staff.post(f"/appointments/{appt}/coverage-override", json={"kind": "self_pay", "reason": "ok"}).status_code == 422
    r = staff.post(f"/appointments/{appt}/coverage-override", json={"kind": "self_pay", "reason": "Patient elected self-pay at booking"})
    assert r.status_code == 200
    c = staff.get(f"/cases/{case['id']}").json()["case"]
    assert c["status"] == "resolved" and c["resolution_code"] == "staff_override"


def test_dashboard_numbers_come_from_data(as_user):
    s = as_user("insurance@harborview.dev").get("/insurance/guardian/summary").json()
    assert s["visits"] == sum(s["states"].values()) and s["simulated_eligibility"] is True
    assert s["ready"] == s["states"].get("verified_active", 0) + s["states"].get("cleared_override", 0)
