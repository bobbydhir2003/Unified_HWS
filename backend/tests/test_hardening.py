"""Hardening: auth rate limiting, production configuration guard, metrics without identifiers, adapters."""

from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.core.hardening import production_problems


def test_login_rate_limited_per_ip(app, monkeypatch):
    import app.main as main

    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_auth_per_minute", 5)
    main.limiter.hits.clear()
    c = TestClient(app)
    hdr = {"X-Forwarded-For": "198.51.100.23"}
    codes = [c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"}, headers=hdr).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    other = c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"}, headers={"X-Forwarded-For": "198.51.100.99"})
    assert other.status_code == 401  # a different client isn't affected
    main.limiter.hits.clear()


def test_production_guard_rejects_unsafe_config():
    bad = Settings(environment="production")
    problems = production_problems(bad)
    assert any("SECRET_KEY" in p for p in problems) and any("COOKIE_SECURE" in p for p in problems)
    good = Settings(environment="production", secret_key="x" * 48, cookie_secure=True, celery_eager=False, storage_backend="s3",
                    cors_origins=["https://app.example.org"], enforce_mfa=True)
    assert production_problems(good) == []


def test_metrics_use_route_templates_not_ids(as_user, app):
    pid = as_user("dr.chen@harborview.dev").get("/patients", params={"q": "Moreau"}).json()["items"][0]["id"]
    as_user("dr.chen@harborview.dev").get(f"/patients/{pid}")
    body = TestClient(app).get("/api/metrics").text
    assert 'route="/patients/{patient_id}"' in body and pid not in body


def test_system_status_reports_adapters(as_user):
    s = as_user("clinicadmin@harborview.dev").get("/system/status").json()
    assert s["adapters"] == {"order_transmitter": "simulated", "clearinghouse": "simulated", "message_gateway": "outbox",
                           "eligibility": "simulated"}
