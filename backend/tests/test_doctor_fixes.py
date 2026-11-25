"""Doctor workspace fixes: starting a task (the My Work 500), JSON error contract, Aster general chat + explicit patient
context, My Visits scoping, and Sonara audio → transcript review → draft → apply with a controlled transcriber double."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.db import SessionLocal
from app.models import Patient

DOC, SUPER, NURSE, FRONT = "dr.chen@harborview.dev", "admin@undeclared.dev", "nurse.kim@harborview.dev", "frontdesk@harborview.dev"


def test_starting_a_task_works_and_errors_are_json(as_user, app, monkeypatch):
    doc = as_user(DOC)
    t = doc.post("/tasks", json={"title": "Call back about results", "priority": "normal"}).json()
    r = doc.post(f"/tasks/{t['id']}/start")
    assert r.status_code == 200, r.text  # was a database error (status VARCHAR(10) + constraint without in_progress)
    assert r.json()["status"] == "in_progress"
    assert any(x["id"] == t["id"] and x["status"] == "in_progress" for x in doc.get("/tasks").json())
    assert doc.post(f"/tasks/{t['id']}/complete").json()["status"] == "done"
    # Any unexpected server failure still answers with the JSON error shape (never a plain-text page).
    from app.api.routers import home_dashboard

    def boom(*a, **k):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(home_dashboard, "build", boom)
    c = TestClient(app, raise_server_exceptions=False)
    tok = c.post("/api/auth/login", json={"email": DOC, "password": "Undeclared!2026"}).json()["access_token"]
    r = c.get("/api/v1/home", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 500 and r.headers["content-type"].startswith("application/json")
    body = r.json()["detail"]
    assert body["code"] == "internal_error" and "synthetic failure" not in str(body)


def test_aster_general_chat_and_explicit_patient_context(as_user):
    doc, lake = as_user(DOC), as_user("dr.lake@lakeside.dev", "lakeside")
    conv = doc.post("/assist/conversations", json={"agent_key": "doctor_assistant", "context_type": "workspace", "new": True})
    assert conv.status_code == 200, conv.text
    conv = conv.json()
    assert conv["context_type"] == "workspace"
    conv = doc.post(f"/assist/conversations/{conv['id']}/messages", json={"text": "Hello Aster, what can you help me with?"}).json()
    hello = [m for m in conv["messages"] if m["role"] == "assistant"][-1]["content"]
    assert "Aster" in hello and "schedule" in hello
    conv = doc.post(f"/assist/conversations/{conv['id']}/messages", json={"text": "What appointments do I have today?"}).json()
    last = [m for m in conv["messages"] if m["role"] == "assistant"][-1]
    assert {t["tool"] for t in last["tool_activity"]} == {"get_my_schedule"}
    conv = doc.post(f"/assist/conversations/{conv['id']}/messages", json={"text": "Explain the difference between a draft and a signed note"}).json()
    assert "draft" in [m for m in conv["messages"] if m["role"] == "assistant"][-1]["content"].lower()
    again = doc.get(f"/assist/conversations/{conv['id']}").json()
    assert len(again["messages"]) == 6  # persisted multi-turn history
    # No patient facts in general mode: a chart question is redirected, not answered from guesswork.
    conv = doc.post(f"/assist/conversations/{conv['id']}/messages", json={"text": "What medications is my patient on?"}).json()
    assert [m for m in conv["messages"] if m["role"] == "assistant"][-1]["citations"] == []
    # Explicit patient context: cited chart answers; unauthorized contexts are refused.
    from sqlalchemy import select

    from app.models import ProviderProfile, User

    db0 = SessionLocal()
    chen = db0.scalar(select(ProviderProfile.id).join(User, User.id == ProviderProfile.user_id).where(User.email == DOC))
    pid = str(db0.scalar(select(Patient.id).where(Patient.is_restricted.is_(False), Patient.primary_provider_id.is_distinct_from(chen),
                                                  Patient.last_name.not_like("%Tester%")).limit(1)))  # no treating relationship with Dr. Chen
    db0.close()
    pc = doc.post("/assist/conversations", json={"agent_key": "doctor_assistant", "context_type": "patient", "context_id": pid, "new": True}).json()
    pc = doc.post(f"/assist/conversations/{pc['id']}/messages", json={"text": "List current medications"}).json()
    assert pc["context_type"] == "patient" and pc["id"] != conv["id"]
    assert lake.post("/assist/conversations", json={"agent_key": "doctor_assistant", "context_type": "patient", "context_id": pid}).status_code == 404
    db = SessionLocal()
    db.execute(update(Patient).where(Patient.id == uuid.UUID(pid)).values(is_restricted=True))
    db.commit()
    try:
        assert doc.get(f"/assist/conversations/{pc['id']}").status_code == 404  # lost access → history no longer readable
        assert doc.post(f"/assist/conversations/{pc['id']}/messages", json={"text": "and allergies?"}).status_code == 404
    finally:
        db.execute(update(Patient).where(Patient.id == uuid.UUID(pid)).values(is_restricted=False))
        db.commit()
        db.close()


def test_my_visits_views_and_scope(as_user):
    doc, admin = as_user(DOC), as_user(SUPER).act("doctor")
    d = doc.get("/my-visits").json()
    assert d["scope"] == "mine" and d["view"] == "today"
    home = {m["key"]: m["value"] for m in doc.get("/home").json()["dashboard"]["metrics"]}
    assert d["counts"]["today"] == home["visits"]  # same appointments as the dashboard
    for view in ("upcoming", "in_progress", "completed", "documentation"):
        r = doc.get("/my-visits", params={"view": view})
        assert r.status_code == 200, (view, r.text)
        if view in ("in_progress", "completed", "documentation"):
            assert all(i["kind"] == "encounter" and i["link"] == f"/encounters/{i['id']}" for i in r.json()["items"])
    a = admin.get("/my-visits").json()
    assert a["scope"] == "clinics" and a["scope_note"]  # Platform Admin is never presented as the clinician
    assert as_user(FRONT).get("/my-visits").status_code == 403  # no clinical access


def test_sonara_audio_review_draft_apply_with_transcriber_double(as_user, monkeypatch):
    from app.ai.scribe import Segment
    from app.services import scribe as svc
    from tests.test_scribe import _open_encounter

    class FakeTranscriber:  # controlled test double for the speech-to-text service (no real audio leaves the test)
        name = "test-double"

        def transcribe(self, audio, content_type):
            return [Segment(speaker="other", text="What brings you in today?"), Segment(speaker="other", text="I have had a sore throat for three days.")]

    monkeypatch.setattr(svc, "get_transcriber", lambda: FakeTranscriber())
    doc = as_user(DOC)
    enc = _open_encounter(doc, "Sore throat")
    s = doc.post(f"/encounters/{enc['id']}/scribe", json={"consent_method": "verbal", "consent_confirmed": True}).json()
    assert s["consent_method"] == "verbal" and s["consent_recorded_at"]
    fake_webm = b"\x1aE\xdf\xa3" + b"\x00" * 2048
    doc.post(f"/scribe/{s['id']}/audio", files={"file": ("visit.webm", fake_webm, "audio/webm")}, data={"seconds": "20"})
    s = doc.get(f"/encounters/{enc['id']}/scribe").json()
    assert s["status"] == "transcribed" and len(s["transcript"]) == 2  # the state the panel previously didn't render
    reviewed = [{"speaker": "clinician", "text": "What brings you in today?"}, {"speaker": "patient", "text": "I have had a sore throat for three days."}]
    assert doc.post(f"/scribe/{s['id']}/transcript", json={"segments": reviewed}).status_code == 200
    s = doc.get(f"/encounters/{enc['id']}/scribe").json()
    assert s["status"] == "ready" and s["draft"]["subjective"] and s["transcript_edited"]
    assert as_user(FRONT).post(f"/scribe/{s['id']}/apply", json={"mode": "replace"}).status_code == 403
    applied = doc.post(f"/scribe/{s['id']}/apply", json={"mode": "replace"}).json()
    assert applied["status"] == "applied"
    note = doc.get(f"/encounters/{enc['id']}").json()["notes"][0]
    assert note["status"] == "draft"  # stays a draft until the clinician signs
    assert as_user(SUPER).act("doctor").post(f"/notes/{note['id']}/sign", json={"expected_version": note["current_version"], "attest_ai_reviewed": True}).status_code == 403
    _ = pytest
