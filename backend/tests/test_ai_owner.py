"""Phase 1: platform-owner AI controls, persistent owner-managed demo AI, durable limits, kill switches, model-family
validation, Super Admin CLI, email change, and server-validated voice tools. OpenAI is never called (key validation and
provider calls are mocked)."""
import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai import demo_scope, owner_demo, usage
from app.api.routers import ai_admin
from app.core.config import settings
from app.core.db import SessionLocal
from app.models import AIProviderSettings, Task, User

FAKE_KEY = "sk-owner-demo-" + "x" * 30


@pytest.fixture
def no_validate(monkeypatch):
    monkeypatch.setattr(ai_admin, "_validate_key", lambda key: None)


@pytest.fixture(autouse=True)
def _reset_owner_rows():
    yield
    db = SessionLocal()
    for scope in ("demo",):
        row = db.scalar(select(AIProviderSettings).where(AIProviderSettings.scope == scope))
        if row:
            db.delete(row)
    plat = db.scalar(select(AIProviderSettings).where(AIProviderSettings.scope == "platform"))
    if plat and (plat.policy or {}).get("ai_disabled"):
        plat.policy = {**plat.policy, "ai_disabled": False}
    db.commit()
    db.close()
    from app.ai.config import invalidate

    invalidate()


def test_owner_configures_demo_ai_and_key_is_never_returned(as_user, no_validate):
    owner = as_user("admin@undeclared.dev")
    st = owner.get("/admin/ai-owner").json()
    assert st["demo"]["enabled"] is False and st["demo"]["limits"]["visitor_daily_requests"] == 25
    assert st["demo"]["limits"]["global_daily_requests"] == 200 and st["demo"]["limits"]["monthly_budget_usd"] == 10.0
    # Enabling without a key is refused.
    assert owner.put("/admin/ai-owner/demo", json={"enabled": True}).status_code == 400
    r = owner.put("/admin/ai-owner/demo", json={"enabled": True, "api_key": FAKE_KEY, "text_model": "gpt-4.1-mini",
                                                "allowed_agents": ["doctor_assistant", "insurance_guardian"]})
    assert r.status_code == 200, r.text
    assert FAKE_KEY not in r.text and FAKE_KEY[-6:] not in r.text.replace(r.json()["demo"]["dedicated_key"]["hint"] or "", "")
    assert r.json()["demo"]["active"] is True
    policy, eff = owner_demo.load()
    assert eff.source == "owner-demo" and eff.api_key == FAKE_KEY and eff.allowed_agents == ["doctor_assistant", "insurance_guardian"]
    assert demo_scope._default().source == "owner-demo"  # visitors without their own key use the owner provider
    # Emergency disable takes effect immediately (no redeploy).
    assert owner.post("/admin/ai-owner/demo/disable").json()["demo"]["active"] is False
    assert owner_demo.load()[1] is None


def test_operator_env_kill_switch(as_user, no_validate, monkeypatch):
    owner = as_user("admin@undeclared.dev")
    owner.put("/admin/ai-owner/demo", json={"enabled": True, "api_key": FAKE_KEY})
    monkeypatch.setattr(settings, "demo_ai_disabled", True)
    owner_demo.invalidate()
    assert owner_demo.load()[1] is None


def test_only_real_superadmin_can_reach_owner_controls(as_user, app, monkeypatch):
    assert as_user("hospitaladmin@harborview.dev").get("/admin/ai-owner").status_code == 403
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_sandbox_enabled", False)  # legacy shared account; demo hospitals: test_demo_sandbox
    c = TestClient(app)
    r = c.post("/api/v1/auth/demo-login", json={"key": "super_admin"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}", "X-Organization-Id": r.json()["me"]["memberships"][0]["organization_id"]}
    assert c.get("/api/v1/admin/ai-owner", headers=h).status_code == 403
    assert c.put("/api/v1/admin/ai-owner/demo", headers=h, json={"enabled": True}).status_code == 403
    assert c.put("/api/v1/admin/ai-owner/platform", headers=h, json={"ai_disabled": True}).status_code == 403


def test_platform_kill_switch_turns_ai_into_labelled_simulation(as_user):
    from app.ai.config import effective, invalidate

    owner = as_user("admin@undeclared.dev")
    assert owner.put("/admin/ai-owner/platform", json={"ai_disabled": True}).json()["platform"]["ai_disabled"] is True
    invalidate()
    e = effective()
    assert e.provider == "simulated" and e.api_key is None and "turned off" in (e.reason or "")
    owner.put("/admin/ai-owner/platform", json={"ai_disabled": False})


def test_model_family_validation(as_user):
    owner = as_user("admin@undeclared.dev")
    r = owner.put("/admin/ai-settings", json={"provider": "openai", "text_model": "gpt-4.1-mini", "transcription_model": "gpt-realtime"})
    assert r.status_code == 422 and "transcri" in r.text.lower()
    r = owner.put("/admin/ai-settings", json={"provider": "openai", "text_model": "gpt-4o-mini-transcribe"})
    assert r.status_code == 422


def test_request_limit_is_atomic_under_concurrency():
    key = f"test:atomic:{uuid.uuid4()}"
    results = []
    threads = [threading.Thread(target=lambda: results.append(usage.take_request(key, 5))) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 5 and usage.read(key)["requests"] == 5


def test_budget_reservation_never_exceeds_budget():
    key = f"test:budget:{uuid.uuid4()}"
    assert usage.reserve_cost(key, 0.06, 0.10) and not usage.reserve_cost(key, 0.06, 0.10)
    assert usage.read(key)["cost_usd"] == pytest.approx(0.06)


def test_shared_demo_limits_per_visitor_and_refund_on_refusal():
    from app.ai.config import EffectiveAI

    eff = EffectiveAI(provider="openai", api_key="sk-x", text_model="gpt-4.1-mini", source="owner-demo", allowed_models=["gpt-4.1-mini"],
                      limits={**owner_demo.DEFAULT_POLICY["limits"], "visitor_daily_requests": 1})
    token = f"sess:{uuid.uuid4()}"
    with demo_scope.use(token, eff):
        with demo_scope.guard("gpt-4.1-mini") as t:
            t.record("gpt-4.1-mini", 1000, 100)
        with pytest.raises(demo_scope.DemoLimitError):
            with demo_scope.guard("gpt-4.1-mini"):
                pass
        with pytest.raises(demo_scope.DemoLimitError):  # model not on the allow-list
            with demo_scope.guard("gpt-5"):
                pass
        with pytest.raises(demo_scope.DemoLimitError):  # realtime off by default
            with demo_scope.guard("gpt-realtime", kind="realtime"):
                pass


# ------------------------------------------------------------------------------------------------ CLI & account

def test_cli_create_reset_and_set_email_never_print_secrets(capsys):
    from app import cli

    email = f"owner.{uuid.uuid4().hex[:6]}@example.com"
    pw = "Str0ng-Owner-Passw0rd!"
    with pytest.raises(cli.CLIError):
        cli.create_superadmin(email, "Ada", "Owner", None, ask=lambda _: "yes", secret=lambda _: pw)
    assert cli.create_superadmin(email, "Ada", "Owner", None, ask=lambda _: f"CREATE SUPERADMIN {email}", secret=lambda _: pw) == "created"
    with pytest.raises(cli.CLIError):  # mismatched passwords
        it = iter([pw, pw + "x"])
        cli.reset_password(email, ask=lambda _: f"RESET PASSWORD {email}", secret=lambda _: next(it))
    cli.reset_password(email, ask=lambda _: f"RESET PASSWORD {email}", secret=lambda _: pw + "2")
    new = email.replace("owner.", "owner2.")
    cli.set_email(email, new, ask=lambda _: f"CHANGE EMAIL {email} TO {new}")
    assert new in cli.list_superadmins(out=lambda *_: None)
    out = capsys.readouterr()
    assert pw not in out.out + out.err and "$2b$" not in out.out + out.err
    db = SessionLocal()
    u = db.scalar(select(User).where(User.email == new))
    assert u.is_superadmin
    db.delete(u)
    db.commit()
    db.close()


def test_email_change_requires_password_and_is_unique(as_user):
    from app.core.security import hash_password
    from app.seed import DEV_PASSWORD

    db = SessionLocal()
    email = f"emailchange.{uuid.uuid4().hex[:6]}@example.com"
    u = User(email=email, first_name="E", last_name="C", password_hash=hash_password(DEV_PASSWORD))
    db.add(u)
    db.commit()
    db.close()
    api = as_user(email, None)
    c, h = api.c, api.headers
    assert c.post("/api/auth/email/change", headers=h, json={"new_email": "x.y@example.com", "current_password": "wrong"}).status_code == 400
    assert c.post("/api/auth/email/change", headers=h, json={"new_email": "admin@undeclared.dev", "current_password": DEV_PASSWORD}).status_code == 400
    new = email.replace("emailchange", "changed")
    r = c.post("/api/auth/email/change", headers=h, json={"new_email": new, "current_password": DEV_PASSWORD})
    assert r.status_code == 200 and r.json()["user"]["email"] == new


# ------------------------------------------------------------------------------------------------ voice tools

def test_realtime_tools_are_allow_listed_and_validated(as_user):
    fd = as_user("frontdesk@harborview.dev")
    assert fd.post("/ai/realtime/tools/delete_patient", json={}).status_code == 404
    info = fd.post("/ai/realtime/tools/get_clinic_information", json={}).json()
    assert info["facilities"] and "departments" in info
    assert fd.post("/ai/realtime/tools/request_staff_callback", json={"topic": "x" * 500}).status_code == 422
    r = fd.post("/ai/realtime/tools/request_staff_callback", json={"topic": "Change appointment time", "caller_first_name": "Sam"})
    assert r.status_code == 200 and "Nothing has been booked" in r.json()["message"]
    db = SessionLocal()
    t = db.scalar(select(Task).where(Task.kind == "callback", Task.title.like("%Sam%")).order_by(Task.created_at.desc()))
    assert t and t.assigned_role == "receptionist" and t.source == "voice_ai"
    db.close()
    assert as_user("billing@harborview.dev").post("/ai/realtime/tools/get_clinic_information", json={}).status_code == 403
