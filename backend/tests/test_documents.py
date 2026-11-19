"""Document intake: upload validation, AI analysis (simulated), matching, review gate, isolation, PHI gate, fax webhook."""

import pytest
from fastapi.testclient import TestClient

from app.ai.provider import AIPolicyError, AnthropicProvider
from app.core.config import settings
from app.services.sample_docs import make_sample

DOCTOR, FRONT, NURSE = "dr.chen@harborview.dev", "frontdesk@harborview.dev", "nurse.rivera@harborview.dev"


def _patient(api, q="Elena Moreau"):
    return api.get("/patients", params={"q": q}).json()["items"][0]


def test_upload_rejects_unsupported_bytes(as_user):
    api = as_user(FRONT)
    r = api.post("/documents", files={"file": ("evil.pdf", b"<script>alert(1)</script>", "application/pdf")})
    assert r.status_code == 422
    assert api.post("/documents", files={"file": ("empty.pdf", b"", "application/pdf")}).status_code == 422


def test_exact_sample_is_analyzed_and_matched_but_not_filed(as_user):
    api = as_user(FRONT)
    p = _patient(api)
    d = api.post("/documents/samples", json={"kind": "lab_result", "fidelity": "exact", "patient_id": p["id"]}).json()
    assert d["status"] == "needs_review"          # never auto-filed
    assert d["patient_id"] is None
    assert d["suggested_patient_id"] == p["id"]
    assert d["doc_type"] == "lab_result" and d["ai_output"]["key_findings"]
    assert d["ai_provider"] == "simulated"
    assert d["match_candidates"][0]["score"] >= 0.9


def test_ambiguous_or_unknown_documents_get_no_confident_suggestion(as_user):
    api = as_user(FRONT)
    d = api.post("/documents/samples", json={"kind": "referral", "fidelity": "unknown"}).json()
    assert d["status"] == "needs_review" and d["suggested_patient_id"] is None


def test_filing_requires_review_permission_and_identity_confirmation(as_user):
    front, nurse = as_user(FRONT), as_user(NURSE)
    p = _patient(front)
    d = front.post("/documents/samples", json={"kind": "imaging_report", "patient_id": p["id"]}).json()
    body = {"patient_id": p["id"], "doc_type": "imaging_report", "title": "Chest X-ray", "identity_confirmed": True}
    assert front.post(f"/documents/{d['id']}/file", json=body).status_code == 403   # receptionist: upload only
    r = nurse.post(f"/documents/{d['id']}/file", json={**body, "identity_confirmed": False})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "identity_not_confirmed"
    filed = nurse.post(f"/documents/{d['id']}/file", json=body).json()
    assert filed["status"] == "filed" and filed["patient_id"] == p["id"]
    assert any(x["id"] == d["id"] for x in nurse.get(f"/patients/{p['id']}/documents").json())
    assert nurse.get(f"/documents/{d['id']}/file").status_code == 200
    assert nurse.post(f"/documents/{d['id']}/file", json=body).status_code == 400   # can't file twice
    assert any(i["type"] == "document" for i in as_user(DOCTOR).get(f"/patients/{p['id']}/timeline").json())


def test_documents_are_tenant_isolated(as_user):
    d = as_user(FRONT).post("/documents/samples", json={"kind": "referral"}).json()
    lake = as_user("dr.lake@lakeside.dev", "lakeside")
    assert lake.get(f"/documents/{d['id']}").status_code == 404
    assert lake.get(f"/documents/{d['id']}/file").status_code == 404
    assert all(x["id"] != d["id"] for x in lake.get("/documents").json()["items"])


def test_external_ai_refused_for_phi_without_approval(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key-not-used")
    monkeypatch.setattr(settings, "ai_phi_allowed", False)
    pdf, _, _ = make_sample("lab_result", None, "unknown", seed=1)
    with pytest.raises(AIPolicyError):
        AnthropicProvider().analyze_document("text", pdf, "application/pdf", contains_phi=True)


def test_fax_webhook_requires_secret(app):
    c = TestClient(app)
    pdf, _, _ = make_sample("referral", None, "unknown", seed=2)
    files = {"file": ("fax.pdf", pdf, "application/pdf")}
    assert c.post("/api/integrations/fax/harborview/inbound", files=files, headers={"X-Fax-Secret": "wrong"}).status_code == 401
    r = c.post("/api/integrations/fax/harborview/inbound", files=files, data={"from_number": "+15550100"},
               headers={"X-Fax-Secret": "dev-fax-secret-harborview"})
    assert r.status_code == 202
