"""Realtime Voice: the server mints an ephemeral client secret; the permanent key never reaches the browser.
OpenAI is never called here — an httpx MockTransport stands in for the API."""

import json
import uuid

import httpx
import pytest

from app.ai import config as aiconf
from app.ai import realtime as rt
from app.ai.provider import AIError, AIPolicyError

PERMANENT = "sk-test-SYNTHETIC-REALTIME-0000000000abcd"


@pytest.fixture
def openai_configured(monkeypatch):
    eff = aiconf.EffectiveAI(provider="openai", api_key=PERMANENT, text_model="gpt-test-mini", realtime_model="gpt-realtime-test")
    monkeypatch.setattr(aiconf, "effective", lambda: eff)
    return eff


def test_simulated_without_configuration(as_user):
    s = as_user("frontdesk@harborview.dev").post("/ai/realtime/session", json={})
    if s.status_code == 403:  # role without ai:use — then check with the clinic admin
        s = as_user("clinicadmin@harborview.dev").post("/ai/realtime/session", json={})
    assert s.status_code == 200, s.text
    assert s.json()["mode"] == "simulated" and s.json()["reason"]
    assert as_user("patient@harborview.dev").post("/ai/realtime/session", json={}).status_code == 403


def test_mint_sends_model_and_never_returns_permanent_key(openai_configured):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        seen["safety"] = req.headers.get("openai-safety-identifier")
        return httpx.Response(200, json={"value": "ek_synthetic_ephemeral", "expires_at": 1_900_000_000})

    out = rt.mint_client_secret(org_id=uuid.uuid4(), user_id=uuid.uuid4(), contains_phi=False, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert seen["url"] == rt.CLIENT_SECRETS_URL and seen["auth"] == f"Bearer {PERMANENT}"
    assert seen["body"]["session"]["model"] == "gpt-realtime-test" and "medical advice" in seen["body"]["session"]["instructions"]
    assert seen["safety"] and "@" not in seen["safety"]  # pseudonymous
    assert out["value"] == "ek_synthetic_ephemeral" and out["calls_url"] == rt.CALLS_URL
    assert PERMANENT not in json.dumps(out)


def test_phi_policy_blocks_real_patient_orgs(openai_configured, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ai_phi_allowed", False)
    with pytest.raises(AIPolicyError):
        rt.mint_client_secret(org_id=uuid.uuid4(), user_id=uuid.uuid4(), contains_phi=True,
                              client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))


def test_provider_errors_do_not_leak_key(openai_configured):
    def handler(req):
        return httpx.Response(400, json={"error": {"message": "Unsupported model"}})

    with pytest.raises(AIError) as e:
        rt.mint_client_secret(org_id=uuid.uuid4(), user_id=uuid.uuid4(), contains_phi=False, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert "Unsupported model" in str(e.value) and PERMANENT not in str(e.value)
