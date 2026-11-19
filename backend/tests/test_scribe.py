"""AI scribe: consent, permissions, honest transcription failure, drafting, applying to versioned notes."""

DOCTOR, FRONT = "dr.chen@harborview.dev", "frontdesk@harborview.dev"


def _open_encounter(doc, cc="Cough x 5 days"):
    p = doc.post("/patients", json={"first_name": "Scribe", "last_name": "Tester", "date_of_birth": "1979-09-09",
                                    "sex_at_birth": "female", "confirm_not_duplicate": True}).json()
    clinic = next(c for c in doc.membership["clinics"] if c["code"] == "HDT")
    return doc.post("/encounters", json={"patient_id": p["id"], "clinic_id": clinic["id"], "chief_complaint": cc}).json()


def test_scribe_requires_consent_and_clinical_role(as_user):
    doc = as_user(DOCTOR)
    enc = _open_encounter(doc)
    r = doc.post(f"/encounters/{enc['id']}/scribe", json={"consent_method": "verbal", "consent_confirmed": False})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "consent_required"
    assert as_user(FRONT).post(f"/encounters/{enc['id']}/scribe", json={"consent_method": "verbal", "consent_confirmed": True}).status_code == 403


def test_recorded_audio_is_never_replaced_with_invented_text(as_user):
    doc = as_user(DOCTOR)
    enc = _open_encounter(doc)
    s = doc.post(f"/encounters/{enc['id']}/scribe", json={"consent_method": "verbal", "consent_confirmed": True}).json()
    assert doc.post(f"/scribe/{s['id']}/audio", files={"file": ("a.webm", b"not audio", "audio/webm")}).status_code == 422
    fake_webm = b"\x1aE\xdf\xa3" + b"\x00" * 64
    r = doc.post(f"/scribe/{s['id']}/audio", files={"file": ("a.webm", fake_webm, "audio/webm")}, data={"seconds": "12"}).json()
    s = doc.get(f"/encounters/{enc['id']}/scribe").json()
    assert s["status"] == "failed" and "speech-to-text" in s["error"]
    assert s["transcript"] is None and s["draft"] is None
    assert r["id"] == s["id"]


def test_demo_draft_apply_marks_ai_content_and_requires_attestation(as_user):
    doc = as_user(DOCTOR)
    enc = _open_encounter(doc)
    s = doc.post(f"/encounters/{enc['id']}/scribe", json={"consent_method": "written", "consent_confirmed": True}).json()
    s = doc.post(f"/scribe/{s['id']}/demo").json()
    s = doc.get(f"/encounters/{enc['id']}/scribe").json()
    assert s["status"] == "ready" and s["transcript_source"] == "synthetic_demo"
    assert s["draft"]["assessment"] and s["draft"]["provider"] == "simulated"
    applied = doc.post(f"/scribe/{s['id']}/apply", json={"mode": "replace"}).json()
    assert applied["status"] == "applied" and applied["applied_note_version"] == 1
    e = doc.get(f"/encounters/{enc['id']}").json()
    note = e["notes"][0]
    assert note["has_ai_content"] is True and note["content"]["plan"]
    versions = doc.get(f"/notes/{note['id']}/versions").json()
    assert versions[0]["source"] == "ai_scribe"
    r = doc.post(f"/notes/{note['id']}/sign", json={"expected_version": note["current_version"]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "ai_review_required"
    # session is closed after applying
    assert doc.post(f"/scribe/{s['id']}/regenerate").status_code == 400


def test_apply_respects_note_versions_and_signed_notes(as_user):
    doc = as_user(DOCTOR)
    enc = _open_encounter(doc, "Low back pain")
    note = doc.post(f"/encounters/{enc['id']}/notes", json={}).json()
    s = doc.post(f"/encounters/{enc['id']}/scribe", json={"consent_method": "verbal", "consent_confirmed": True}).json()
    doc.post(f"/scribe/{s['id']}/transcript", json={"segments": [
        {"speaker": "patient", "text": "My back has hurt for three days after lifting boxes."},
        {"speaker": "clinician", "text": "On exam there is lumbar paraspinal tenderness."},
        {"speaker": "clinician", "text": "This is consistent with a muscle strain."},
        {"speaker": "clinician", "text": "Continue ibuprofen 400 mg and follow up in four weeks."}]})
    assert doc.post(f"/scribe/{s['id']}/apply", json={"mode": "append"}).status_code == 409   # no expected_version
    ok = doc.post(f"/scribe/{s['id']}/apply", json={"mode": "append", "expected_version": note["current_version"]})
    assert ok.status_code == 200
    n = doc.get(f"/notes/{note['id']}").json()
    assert "muscle strain" in n["content"]["assessment"]
