"""Demo AI scope: a one-click demo session configures and tests AI against its OWN isolated settings — never the platform
configuration, never another session's key. OpenAI is never called here (validation/health/realtime are mocked)."""

import json
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai import demo_scope
from app.ai.config import EffectiveAI
from app.ai.provider import AIError
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import AgentConfig, AIProviderSettings, DemoAISettings

DEMO_KEY = "sk-test-SYNTHETIC-DEMO-000000000000abcd"


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_openai_api_key", None)
    from app.api.routers import ai_admin
    monkeypatch.setattr(ai_admin, "_validate_key", lambda key: None)  # no network


def _session(app, key="super_admin"):
    c = TestClient(app)
    r = c.post("/api/v1/auth/demo-login", json={"key": key})
    assert r.status_code == 200, r.text
    me = r.json()["me"]
    return c, {"Authorization": f"Bearer {r.json()['access_token']}", "X-Organization-Id": me["memberships"][0]["organization_id"]}


def _platform_snapshot():
    db = SessionLocal()
    try:
        row = db.scalar(select(AIProviderSettings).where(AIProviderSettings.scope == "platform"))
        return None if not row else (row.provider, row.api_key_encrypted, row.text_model, dict(row.agent_models or {}))
    finally:
        db.close()


def test_demo_session_saves_and_tests_its_own_settings(app, demo_on, monkeypatch, as_user):
    before = _platform_snapshot()
    c, h = _session(app)
    s = c.put("/api/v1/admin/ai-settings", headers=h, json={
        "provider": "openai", "api_key": DEMO_KEY, "text_model": "gpt-4.1-mini", "vision_model": "gpt-4.1-mini",
        "transcription_model": "gpt-4o-mini-transcribe", "realtime_model": "gpt-realtime-test", "agent_models": {"hospital_operations": "gpt-4.1-mini"}})
    assert s.status_code == 200, s.text
    body = s.json()
    assert body["key"]["configured"] and body["key"]["hint"] is None and DEMO_KEY not in json.dumps(body)
    assert body["active_provider"] == "openai" and body["agent_models"] == {"hospital_operations": "gpt-4.1-mini"}
    assert body["demo_scope"]["isolated"] and body["demo_scope"]["expires_at"]
    # Encrypted at rest; platform settings untouched.
    db = SessionLocal()
    try:
        row = db.scalars(select(DemoAISettings).order_by(DemoAISettings.created_at.desc())).first()
        assert row.api_key_encrypted and DEMO_KEY not in row.api_key_encrypted
    finally:
        db.close()
    assert _platform_snapshot() == before
    assert DEMO_KEY not in json.dumps(as_user("admin@undeclared.dev").get("/admin/ai-settings").json())
    # Test connection runs against the session key (health mocked).
    from app.ai import openai_provider

    seen = {}

    def fake_health(self):
        seen["key"] = self.cfg.api_key
        return {"ok": True, "models": {"text": True, "realtime": True}, "available_count": 42}

    monkeypatch.setattr(openai_provider.OpenAICore, "health", fake_health)
    t = c.post("/api/v1/admin/ai-settings/test", headers=h)
    assert t.status_code == 200 and t.json()["ok"] and seen["key"] == DEMO_KEY
    assert c.get("/api/v1/admin/ai-settings", headers=h).json()["last_test"]["ok"] is True
    # Realtime voice mints with the session key.
    from app.ai import realtime

    def handler(req):
        seen["rt_auth"] = req.headers["authorization"]
        return httpx.Response(200, json={"value": "ek_synthetic", "expires_at": 1_900_000_000})

    real_client = httpx.Client
    monkeypatch.setattr(realtime.httpx, "Client", lambda *a, **k: real_client(transport=httpx.MockTransport(handler)))
    rs = c.post("/api/v1/ai/realtime/session", headers=h, json={})
    assert rs.status_code == 200 and rs.json()["value"] == "ek_synthetic" and seen["rt_auth"] == f"Bearer {DEMO_KEY}"
    # Another demo session is isolated: no key, simulated.
    c2, h2 = _session(app)
    other = c2.get("/api/v1/admin/ai-settings", headers=h2).json()
    assert not other["key"]["configured"] and other["active_provider"] == "simulated"


def test_demo_agent_overrides_are_session_scoped(app, demo_on):
    c, h = _session(app)
    assert c.get("/api/v1/agents", headers=h).status_code == 200  # Agent Studio loads (creates default agents)
    db = SessionLocal()
    try:
        original = db.scalar(select(AgentConfig.instructions).where(AgentConfig.key == "hospital_operations").limit(1))
    finally:
        db.close()
    new = "Summarize operations for a live product demonstration. Cite case references and never act without approval."
    r = c.put("/api/v1/agents/hospital_operations", headers=h, json={"instructions": new, "max_tool_calls": 4})
    assert r.status_code == 200 and r.json()["demo_override"] and r.json()["instructions"] == new
    listed = {a["key"]: a for a in c.get("/api/v1/agents", headers=h).json()}
    assert listed["hospital_operations"]["instructions"] == new
    run = c.post("/api/v1/agents/hospital_operations/run", headers=h, json={"input": "Shift summary"})
    assert run.status_code == 200 and run.json()["status"] == "succeeded"  # simulated scope → rule-based, with the override
    db = SessionLocal()
    try:
        assert db.scalar(select(AgentConfig.instructions).where(AgentConfig.key == "hospital_operations").limit(1)) == original
    finally:
        db.close()
    c2, h2 = _session(app)
    assert {a["key"]: a for a in c2.get("/api/v1/agents", headers=h2).json()}["hospital_operations"]["instructions"] == original


def test_demo_limits_enforced(monkeypatch):
    monkeypatch.setattr(settings, "demo_ai_max_requests_per_hour", 2)
    token = f"sess:{uuid.uuid4()}"
    with demo_scope.use(token, EffectiveAI(provider="openai", api_key="sk-x", source="demo-session", text_model="m")):
        for _ in range(2):
            with demo_scope.guard():
                pass
        with pytest.raises(AIError, match="request limit"), demo_scope.guard():
            pass
    with demo_scope.guard():  # outside a demo scope: unaffected
        pass


def test_demo_scope_never_falls_back_to_platform_key(demo_on, monkeypatch):
    monkeypatch.setattr(settings, "demo_openai_api_key", None)
    eff = demo_scope.resolve(f"sess:{uuid.uuid4()}")  # no row
    assert eff.provider == "simulated" and eff.api_key is None
    monkeypatch.setattr(settings, "demo_openai_api_key", "sk-demo-project-key-000000000000")
    eff = demo_scope.resolve(f"sess:{uuid.uuid4()}")
    assert eff.provider == "openai" and eff.api_key == "sk-demo-project-key-000000000000" and eff.source == "demo-project"
