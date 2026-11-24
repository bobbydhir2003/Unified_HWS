"""Platform-owner AI controls: the emergency switch, platform-owner-only AI settings, model-family validation, durable
limits, the Super Admin CLI, email change, and server-validated voice tools. OpenAI is never called."""
import threading
import uuid

import pytest
from sqlalchemy import select

from app.ai import usage
from app.core.db import SessionLocal
from app.models import AIProviderSettings, Membership, MembershipRole, Organization, Task, User


@pytest.fixture(autouse=True)
def _reset_owner_rows():
    yield
    db = SessionLocal()
    plat = db.scalar(select(AIProviderSettings).where(AIProviderSettings.scope == "platform"))
    if plat and (plat.policy or {}).get("ai_disabled"):
        plat.policy = {**plat.policy, "ai_disabled": False}
    db.commit()
    db.close()
    from app.ai.config import invalidate

    invalidate()


def test_only_the_platform_owner_reaches_platform_ai_and_org_creation(as_user):
    """An organization-level Super Admin role (or any acting workspace) is not the platform owner."""
    from app.core.security import hash_password
    from app.seed import DEV_PASSWORD

    db = SessionLocal()
    org = db.scalar(select(Organization).where(Organization.slug == "harborview"))
    email = f"orgsuper.{uuid.uuid4().hex[:6]}@example.com"
    u = User(email=email, first_name="Org", last_name="Super", password_hash=hash_password(DEV_PASSWORD))
    db.add(u)
    db.flush()
    m = Membership(user_id=u.id, organization_id=org.id, all_clinics=True)
    db.add(m)
    db.flush()
    m.roles.append(MembershipRole(role="super_admin"))
    db.commit()
    db.close()
    org_super = as_user(email)
    for api in (org_super, as_user("hospitaladmin@harborview.dev")):
        assert api.get("/admin/ai-owner").status_code == 403
        assert api.get("/admin/ai-settings").status_code == 403
        assert api.put("/admin/ai-settings", json={"provider": "simulated"}).status_code == 403
        assert api.put("/admin/ai-owner/platform", json={"ai_disabled": True}).status_code == 403
    assert org_super.post("/organizations", json={"name": "Xx Org", "slug": f"x-{uuid.uuid4().hex[:5]}", "first_clinic_name": "Aa",
                                                  "first_clinic_code": "AAA"}).status_code == 403
    owner = as_user("admin@undeclared.dev")
    assert owner.get("/admin/ai-settings").status_code == 200
    assert owner.act("doctor").get("/admin/ai-settings").status_code == 403  # only in the Super Admin workspace
    st = owner.get("/admin/ai-owner").json()
    assert set(st) == {"platform", "note"} and "api_key" not in str(st)


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
