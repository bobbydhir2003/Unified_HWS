"""Demo mode: one-click sign-in to allowlisted synthetic accounts only; admin configuration and credential changes are
blocked for demo accounts; the platform administrator is never reachable; refused in production."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core import demo
from app.core.config import Settings, settings
from app.core.db import SessionLocal
from app.core.hardening import production_problems
from app.models import PasswordResetToken


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)


def _demo(app, key):
    c = TestClient(app)
    r = c.post("/api/v1/auth/demo-login", json={"key": key})
    return c, r


def _h(r):
    me = r.json()["me"]
    return {"Authorization": f"Bearer {r.json()['access_token']}", "X-Organization-Id": me["memberships"][0]["organization_id"]}


def test_disabled_by_default(app):
    c = TestClient(app)
    assert c.get("/api/v1/auth/demo").json() == {"enabled": False, "accounts": []}
    assert c.post("/api/v1/auth/demo-login", json={"key": "doctor"}).status_code == 404


def test_every_demo_role_signs_in_to_its_own_role(app, demo_on):
    listed = TestClient(app).get("/api/v1/auth/demo").json()
    assert listed["enabled"] and {a["key"] for a in listed["accounts"]} == {k for k, *_ in demo.DEMO_ACCOUNTS}
    for key, _label, email, role in demo.DEMO_ACCOUNTS:
        c, r = _demo(app, key)
        assert r.status_code == 200, (key, r.text)
        me = r.json()["me"]
        assert me["user"]["email"] == email and not me["user"]["is_superadmin"]
        assert role in me["memberships"][0]["roles"], (key, me["memberships"][0]["roles"])
        assert "refresh" in r.headers.get("set-cookie", "").lower() or r.cookies  # normal session
    assert _demo(app, "platform_admin")[1].status_code == 404  # not on the allowlist


def test_demo_super_admin_can_look_but_not_change_admin_settings(app, demo_on):
    c, r = _demo(app, "super_admin")
    h = _h(r)
    s = c.get("/api/v1/admin/ai-settings", headers=h)
    assert s.status_code == 200 and s.json()["key"]["hint"] is None
    assert c.put("/api/v1/admin/ai-settings", headers=h, json={"text_model": "x"}).status_code == 403
    assert c.post("/api/v1/admin/ai-settings/test", headers=h).status_code == 403
    assert c.delete("/api/v1/admin/ai-settings/key", headers=h).status_code == 403
    assert c.post("/api/v1/invitations", headers=h, json={"email": "x@harborview.dev", "roles": ["doctor"]}).status_code == 403
    assert c.patch("/api/v1/organization", headers=h, json={"name": "Hacked"}).status_code == 403
    assert c.put("/api/v1/agents/hospital_operations", headers=h, json={"enabled": False}).status_code == 403
    assert c.get("/api/v1/outbox", headers=h).status_code == 403   # reset links live there
    assert c.post("/api/v1/auth/password/change", headers=h, json={"current_password": "x", "new_password": "Another!Pass99"}).status_code == 403
    assert c.post("/api/v1/auth/mfa/setup", headers=h).status_code == 403
    # Read-only admin screens and normal operational views work.
    assert c.get("/api/v1/command/summary", headers=h).status_code == 200
    assert c.get("/api/v1/audit", headers=h).status_code == 200
    # Only its own organization, not the platform.
    assert len(c.get("/api/v1/organizations", headers=h).json()) == 1


def test_demo_clinical_workflows_still_work_and_permissions_hold(app, demo_on):
    c, r = _demo(app, "front_desk")
    h = _h(r)
    p = c.post("/api/v1/patients", headers=h, json={"first_name": "Demo", "last_name": "Visitor", "date_of_birth": "1990-01-01",
                                                   "sex_at_birth": "female", "confirm_not_duplicate": True})
    assert p.status_code == 201, p.text
    assert c.get("/api/v1/command/summary", headers=h).status_code == 403  # ordinary role permissions unchanged
    c2, r2 = _demo(app, "patient")
    assert c2.get("/api/v1/patients", headers=_h(r2)).status_code == 403


def test_platform_admin_unaffected_and_demo_resets_suppressed(app, demo_on, as_user):
    admin = as_user("admin@undeclared.dev")
    assert admin.get("/outbox").status_code == 200  # real administration is not restricted
    db = SessionLocal()
    try:
        before = db.scalar(select(func.count()).select_from(PasswordResetToken))
        TestClient(app).post("/api/v1/auth/password/forgot", json={"email": "dr.chen@harborview.dev"})
        assert db.scalar(select(func.count()).select_from(PasswordResetToken)) == before
    finally:
        db.close()


def test_refuses_non_synthetic_org(app, demo_on):
    db = SessionLocal()
    try:
        db.execute(text("update organizations set settings = settings || '{\"synthetic_data\": false}'::jsonb where slug = 'harborview'"))
        db.commit()
        assert _demo(app, "doctor")[1].status_code == 403
    finally:
        db.execute(text("update organizations set settings = settings || '{\"synthetic_data\": true}'::jsonb where slug = 'harborview'"))
        db.commit()
        db.close()


def test_production_refuses_demo_mode():
    s = Settings(environment="production", demo_mode=True)
    assert any("DEMO_MODE" in p for p in production_problems(s))
