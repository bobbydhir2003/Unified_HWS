"""OpenAI provider contract tests with a fake SDK client (no network, no key). Live validation is still pending."""

import json
from types import SimpleNamespace

import pytest

from app.ai import openai_provider as op
from app.ai.provider import AIPolicyError, DocumentAnalysis, SimulatedProvider, get_provider
from app.core.config import settings


class FakeResponses:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        return self.outputs.pop(0)


def _resp(text=None, calls=None):
    output = [SimpleNamespace(type="function_call", name=n, arguments=json.dumps(a), call_id=f"c{i}") for i, (n, a) in enumerate(calls or [])]
    if text is not None:
        output.append(SimpleNamespace(type="message", content=[SimpleNamespace(type="output_text", text=text)]))
    return SimpleNamespace(status="completed", output=output, output_text=text or "", model="fake-model",
                           usage=SimpleNamespace(input_tokens=100, output_tokens=50), incomplete_details=None)


@pytest.fixture()
def core(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_text_model", "fake-model")
    monkeypatch.setattr(settings, "ai_prices", {"fake": [2.0, 8.0]})
    c = op.OpenAICore()
    return c


def test_strict_schema_requires_every_field():
    s = op.strict_schema(DocumentAnalysis)
    assert set(s["required"]) == set(s["properties"]) and s["additionalProperties"] is False
    assert "insurance_card" in s["required"]  # optional fields become required-but-nullable for strict mode


def test_structured_output_validated_and_costed(core):
    body = {"doc_type": "lab_result", "title": "Lab", "document_date": None, "sender": None, "summary": "x",
            "patient": {"first_name": "A", "last_name": "B", "date_of_birth": None, "mrn": None}, "key_findings": [], "medications": [],
            "diagnoses_stated": [], "confidence": 0.9, "uncertainties": [], "insurance_card": None}
    core.client = SimpleNamespace(responses=FakeResponses([_resp(json.dumps(body))]))
    data, meta = core.structured(system="s", content=[{"type": "input_text", "text": "t"}], schema=DocumentAnalysis, contains_phi=False)
    assert data.doc_type == "lab_result" and meta.cost_usd == pytest.approx(100 / 1e6 * 2 + 50 / 1e6 * 8)
    sent = core.client.responses.calls[0]
    assert sent["text"]["format"]["strict"] is True and sent["store"] is False and "untrusted data" in sent["instructions"]
    core.client = SimpleNamespace(responses=FakeResponses([_resp("{not json")]))
    with pytest.raises(op.AIError):
        core.structured(system="s", content=[], schema=DocumentAnalysis, contains_phi=False)


def test_phi_blocked_without_approval(core, monkeypatch):
    monkeypatch.setattr(settings, "ai_phi_allowed", False)
    with pytest.raises(AIPolicyError):
        core.structured(system="s", content=[], schema=DocumentAnalysis, contains_phi=True)


def test_tool_loop_executes_server_side_and_is_bounded(core):
    seen = []

    def execute(name, args):
        seen.append((name, args))
        return {"error": "permission denied"} if name == "forbidden_tool" else {"ok": True}

    core.client = SimpleNamespace(responses=FakeResponses([_resp(calls=[("lookup", {"q": 1})]), _resp(calls=[("forbidden_tool", {})]), _resp("done")]))
    text, meta = core.tool_loop(system="s", user="u", tools=[], execute=execute, contains_phi=False)
    assert text == "done" and [n for n, _ in seen] == ["lookup", "forbidden_tool"]
    assert [c["ok"] for c in meta.tool_calls] == [True, False]
    core.client = SimpleNamespace(responses=FakeResponses([_resp(calls=[("lookup", {})])] * 3))
    text, meta = core.tool_loop(system="s", user="u", tools=[], execute=execute, contains_phi=False, max_steps=3)
    assert "tool-call limit" in text and len(meta.tool_calls) == 3


def test_falls_back_to_labeled_simulation_without_key(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", None)
    assert isinstance(get_provider(), SimulatedProvider)


def test_status_endpoint_never_leaks_secret(as_user, monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-secret-value")
    monkeypatch.setattr(settings, "ai_text_model", "")
    r = as_user("clinicadmin@harborview.dev").get("/ai/provider")
    assert r.status_code == 200 and "sk-secret" not in r.text
    assert r.json()["active"] == "simulated" and r.json()["openai_key_configured"] is True and r.json()["org_is_synthetic"] is True
