"""End-to-end front desk → clinical visit flow, plus scheduling and note-integrity rules."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app.core.db import engine

DOCTOR = "dr.chen@harborview.dev"
FRONT = "frontdesk@harborview.dev"
NURSE = "nurse.rivera@harborview.dev"


def next_weekday(d: date, offset_days=30) -> date:
    d = d + timedelta(days=offset_days)
    while d.weekday() > 4:
        d += timedelta(days=1)
    return d


@pytest.fixture(scope="module")
def ctx(as_user):
    front = as_user(FRONT)
    clinic = next(c for c in front.membership["clinics"] if c["code"] == "HDT")
    chen = next(p for p in front.get("/providers").json() if "Chen" in p["name"])
    types = {t["name"]: t for t in front.get("/appointment-types").json()}
    return {"front": front, "clinic": clinic, "chen": chen, "types": types}


def test_duplicate_detection_blocks_then_allows_override(as_user):
    front = as_user(FRONT)
    body = {"first_name": "Jonathon", "last_name": "Brennan", "date_of_birth": "1990-02-14", "sex_at_birth": "male"}
    r = front.post("/patients", json=body)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "possible_duplicate"
    assert any("Brennan" in c["name"] for c in r.json()["detail"]["candidates"])
    r = front.post("/patients", json={**body, "confirm_not_duplicate": True})
    assert r.status_code == 201 and r.json()["mrn"].startswith("UD")


def test_appointment_conflicts_and_availability(ctx):
    front, clinic, chen, t = ctx["front"], ctx["clinic"], ctx["chen"], ctx["types"]["Follow-up"]
    p1 = front.post("/patients", json={"first_name": "Conflict", "last_name": "Tester", "date_of_birth": "1980-05-05",
                                       "sex_at_birth": "female", "confirm_not_duplicate": True}).json()
    p2 = front.post("/patients", json={"first_name": "Second", "last_name": "Booker", "date_of_birth": "1981-06-06",
                                       "sex_at_birth": "male", "confirm_not_duplicate": True}).json()
    day = next_weekday(date.today(), 40)
    tz = ZoneInfo(clinic["timezone"])
    start = datetime.combine(day, time(10, 0), tz)
    mk = lambda pid, s, **kw: front.post("/appointments", json={  # noqa: E731
        "patient_id": pid, "provider_id": chen["id"], "clinic_id": clinic["id"], "appointment_type_id": t["id"],
        "start_at": s.isoformat(), **kw})
    a = mk(p1["id"], start)
    assert a.status_code == 201, a.text
    clash = mk(p2["id"], start + timedelta(minutes=10))
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "provider_conflict"
    assert mk(p2["id"], start + timedelta(minutes=20)).status_code == 201  # back-to-back is fine
    late = mk(p2["id"], datetime.combine(day, time(19, 0), tz))
    assert late.status_code == 409 and late.json()["detail"]["code"] == "outside_availability"
    # DB-level guard holds even if app checks are bypassed.
    with pytest.raises(Exception, match="appointments_no_provider_overlap"):
        with engine.begin() as conn:
            conn.execute(text("""insert into appointments (id, organization_id, clinic_id, patient_id, provider_id, start_at, end_at,
                status, mode, created_at, updated_at) select gen_random_uuid(), organization_id, clinic_id, :p, provider_id,
                start_at + interval '5 minutes', end_at, 'scheduled', 'in_person', now(), now() from appointments where id=:a"""),
                         {"p": p2["id"], "a": a.json()["id"]})
    # Cancelled appointments free the slot.
    assert front.post(f"/appointments/{a.json()['id']}/status", json={"action": "cancel"}).status_code == 400  # reason required
    assert front.post(f"/appointments/{a.json()['id']}/status", json={"action": "cancel", "reason": "Patient request"}).status_code == 200
    assert mk(p2["id"], start - timedelta(minutes=0) + timedelta(hours=1)).status_code == 201


def test_full_visit_registration_to_signed_note(ctx, as_user):
    front, clinic, chen = ctx["front"], ctx["clinic"], ctx["chen"]
    doctor, nurse = as_user(DOCTOR), as_user(NURSE)

    # 1. Register
    p = front.post("/patients", json={
        "first_name": "Workflow", "last_name": "Patient", "date_of_birth": "1975-03-03", "sex_at_birth": "female",
        "phone": "(555) 111-2222", "confirm_not_duplicate": True,
        "insurance": {"payer_name": "Bluebay Health (synthetic)", "member_id": "SYN123"}}).json()
    # 2. Book for now (override hours so the test is time-independent), check in, room
    start = datetime.now(ZoneInfo(clinic["timezone"])).replace(second=0, microsecond=0) + timedelta(minutes=5)
    # Find a free moment for Dr. Chen
    for _ in range(40):
        r = front.post("/appointments", json={"patient_id": p["id"], "provider_id": chen["id"], "clinic_id": clinic["id"],
                                              "start_at": start.isoformat(), "end_at": (start + timedelta(minutes=5)).isoformat(),
                                              "override_availability": True, "reason": "Sore throat"})
        if r.status_code == 201:
            break
        start += timedelta(minutes=7)
    assert r.status_code == 201, r.text
    appt = r.json()
    assert front.post(f"/appointments/{appt['id']}/status", json={"action": "check_in"}).status_code == 200
    assert front.post(f"/appointments/{appt['id']}/status", json={"action": "room", "room": "Exam 1"}).json()["status"] == "roomed"

    # 3. Doctor starts encounter; nurse records vitals and drafts
    enc = doctor.post("/encounters", json={"patient_id": p["id"], "appointment_id": appt["id"]}).json()
    assert enc["status"] == "in_progress" and enc["chief_complaint"] == "Sore throat"
    v = nurse.post(f"/patients/{p['id']}/vitals", json={"encounter_id": enc["id"], "systolic": 122, "diastolic": 78, "heart_rate": 72})
    assert v.status_code == 201
    assert nurse.post(f"/patients/{p['id']}/vitals", json={"systolic": 120}).status_code == 400  # incomplete BP

    note = nurse.post(f"/encounters/{enc['id']}/notes", json={}).json()
    assert note["status"] == "draft" and note["current_version"] == 1
    content = {"subjective": "Sore throat x3 days", "objective": "Pharynx erythematous", "assessment": "", "plan": ""}
    saved = nurse.put(f"/notes/{note['id']}", json={"content": content, "expected_version": 1}).json()
    assert saved["current_version"] == 2
    # Optimistic concurrency
    stale = doctor.put(f"/notes/{note['id']}", json={"content": content, "expected_version": 1})
    assert stale.status_code == 409

    # 4. Signing rules
    assert nurse.post(f"/notes/{note['id']}/sign", json={"expected_version": 2}).status_code == 403
    assert doctor.post(f"/notes/{note['id']}/sign", json={"expected_version": 2}).status_code == 400  # A/P missing
    content |= {"assessment": "Acute pharyngitis", "plan": "Supportive care"}
    ai = doctor.put(f"/notes/{note['id']}", json={"content": content, "expected_version": 2, "source": "ai_scribe"}).json()
    assert ai["has_ai_content"] is True
    r = doctor.post(f"/notes/{note['id']}/sign", json={"expected_version": 3})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "ai_review_required"
    assert doctor.post(f"/encounters/{enc['id']}/complete").status_code == 400  # unsigned note
    signed = doctor.post(f"/notes/{note['id']}/sign", json={"expected_version": 3, "attest_ai_reviewed": True}).json()
    assert signed["status"] == "signed" and signed["ai_reviewed"] is True

    # 5. Signed notes are immutable (API + DB); addenda allowed
    assert doctor.put(f"/notes/{note['id']}", json={"content": content, "expected_version": 4}).status_code == 400
    with pytest.raises(Exception, match="cannot be modified"):
        with engine.begin() as conn:
            conn.execute(text("update clinical_notes set content='{}' where id=:i"), {"i": note["id"]})
    with pytest.raises(Exception, match="append-only"):
        with engine.begin() as conn:
            conn.execute(text("update clinical_note_versions set content='{}' where note_id=:i"), {"i": note["id"]})
    add = doctor.post(f"/notes/{note['id']}/addenda", json={"body": "Rapid strep negative."})
    assert add.status_code == 201 and len(add.json()["addenda"]) == 1
    versions = doctor.get(f"/notes/{note['id']}/versions").json()
    assert [v["version"] for v in versions] == [4, 3, 2, 1]

    # 6. Diagnoses + complete + check out
    assert doctor.post(f"/encounters/{enc['id']}/complete").status_code == 400  # no diagnosis
    d = doctor.put(f"/encounters/{enc['id']}/diagnoses", json=[{"code": "J02.9", "description": "Acute pharyngitis, unspecified",
                                                               "add_to_problem_list": True}])
    assert d.status_code == 200
    done = doctor.post(f"/encounters/{enc['id']}/complete").json()
    assert done["status"] == "completed"
    assert front.get(f"/appointments/{appt['id']}").json()["status"] == "completed"
    assert front.post(f"/appointments/{appt['id']}/status", json={"action": "check_out"}).json()["status"] == "checked_out"

    # 7. Shows up in timeline and summary
    tl = doctor.get(f"/patients/{p['id']}/timeline").json()
    assert {"encounter", "note", "vitals", "appointment", "problem"} <= {i["type"] for i in tl}
    summ = doctor.get(f"/patients/{p['id']}/summary").json()
    assert any(pr["code"] == "J02.9" for pr in summ["problems"])
