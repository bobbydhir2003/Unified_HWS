"""Private demo hospitals (Phases 1, 2, 3, 6): each visitor gets an isolated synthetic hospital, can switch between all
14 roles, configure their own hospital as its Super Admin, reset it, and it expires. Real organizations and accounts are
never touched. OpenAI is never called here."""
from datetime import timedelta

import pytest
from conftest import Visitor
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.permissions import Role
from app.core.security import now
from app.demo import sandbox
from app.models import AuditEvent, Base, DemoSandbox, Organization, PasswordResetToken, User, UserSession
from app.seed import DEV_PASSWORD


def _org_rows(db, org_id) -> int:
    n = 0
    for t in Base.metadata.sorted_tables:
        if "organization_id" in t.c and t.name != "demo_sandboxes":
            n += db.execute(text(f'SELECT count(*) FROM "{t.name}" WHERE organization_id = :o'), {"o": org_id}).scalar()
    return n


def _harborview(db):
    return db.scalar(select(Organization.id).where(Organization.slug == "harborview"))


# ---------------------------------------------------------------------------------------------- Phase 1: isolation

def test_two_visitors_get_separate_hospitals_and_cannot_see_each_other(app, demo):
    db = SessionLocal()
    hv = _harborview(db)
    hv_before = _org_rows(db, hv)
    users_before = db.scalar(select(func.count()).select_from(User).where(User.sandbox_org_id.is_(None)))
    db.close()
    a = Visitor(app, "198.51.100.10").enter("front_desk")
    b = Visitor(app, "198.51.100.20").enter("front_desk")
    assert a.org != b.org and str(hv) not in (a.org, b.org)
    # Each edits their own hospital.
    pa = a.post("/patients", json={"first_name": "Isolde", "last_name": "Visitor-A", "date_of_birth": "1990-01-01", "sex_at_birth": "female"})
    assert pa.status_code == 201, pa.text
    pid = pa.json()["id"]
    assert a.get(f"/patients/{pid}").status_code == 200
    # The other visitor can't read it, not by id, not by search, not by pointing at the other hospital.
    assert b.get(f"/patients/{pid}").status_code == 404
    assert not [p for p in b.get("/patients", params={"q": "Visitor-A"}).json()["items"]]
    assert b.get("/patients", headers={"X-Organization-Id": a.org}).status_code == 403
    assert b.get("/patients", headers={"X-Organization-Id": str(hv)}).status_code == 403
    db = SessionLocal()
    assert _org_rows(db, hv) == hv_before  # the real organization is untouched
    assert db.scalar(select(func.count()).select_from(User).where(User.sandbox_org_id.is_(None))) == users_before
    db.close()


def test_hospital_identities_cannot_use_password_reset_or_invitations(app, demo):
    v = Visitor(app, "198.51.100.30").enter("doctor")
    email = v.me["user"]["email"]
    assert email.endswith(".demo.example.com")
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"email": email, "password": DEV_PASSWORD}).status_code == 401
    c.post("/api/v1/auth/password/forgot", json={"email": email})
    db = SessionLocal()
    u = db.scalar(select(User).where(User.email == email))
    assert u.password_hash is None and u.sandbox_org_id is not None
    assert not db.scalar(select(PasswordResetToken.id).where(PasswordResetToken.user_id == u.id))
    db.close()


# ---------------------------------------------------------------------------------------------- Phase 2: roles

def test_all_fourteen_roles_are_offered_and_switchable(app, demo):
    listed = TestClient(app).get("/api/v1/auth/demo").json()
    assert listed["private_hospitals"] and {a["role"] for a in listed["accounts"]} == {r.value for r in Role}
    v = Visitor(app, "198.51.100.40").enter("super_admin")
    org = v.org
    info = v.get("/auth/demo/session").json()
    assert info["role_key"] == "super_admin" and len(info["roles"]) == 14
    for r in sandbox.ROLES:
        old = v.switch(key=r.key)
        assert v.org == org  # always the same hospital
        assert r.role in v.me["memberships"][0]["roles"], (r.key, v.me["memberships"][0]["roles"])
        assert v.get("/auth/demo/session").json()["role_key"] == r.key
        assert v.c.get("/api/v1/auth/me", headers=old).status_code == 401  # the previous identity's session ended
    db = SessionLocal()
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "demo.role_switched",
                                                                        AuditEvent.organization_id == org)) == 14
    db.close()


def test_role_permissions_still_apply_inside_the_hospital(app, demo):
    v = Visitor(app, "198.51.100.50").enter("front_desk")
    assert v.get("/command/summary").status_code == 403          # receptionist can't open the Command Center
    v.switch(key="patient")
    assert v.get("/patients").status_code == 403                 # a patient sees only the portal
    v.switch(key="super_admin")
    assert v.get("/command/summary").status_code == 200


def test_cannot_switch_to_someone_outside_the_hospital(app, demo):
    a = Visitor(app, "198.51.100.60").enter("doctor")
    b = Visitor(app, "198.51.100.61").enter("doctor")
    other = b.me["user"]["id"]
    assert a.c.post("/api/v1/auth/demo/switch", headers=a.h, json={"user_id": other}).status_code == 404
    db = SessionLocal()
    real = db.scalar(select(User.id).where(User.email == "admin@undeclared.dev"))
    db.close()
    assert a.c.post("/api/v1/auth/demo/switch", headers=a.h, json={"user_id": str(real)}).status_code == 404


# ---------------------------------------------------------------------------------------------- Phase 3: configuration

def test_demo_super_admin_configures_its_own_hospital(app, demo):
    v = Visitor(app, "198.51.100.70").enter("super_admin")
    fac = v.get("/facilities").json()[0]
    r = v.patch(f"/facilities/{fac['id']}", json={"settings": {"demo_note": "edited"}})
    assert r.status_code == 200, r.text
    assert next(f for f in v.get("/facilities").json() if f["id"] == fac["id"])["settings"].get("demo_note") == "edited"  # persists
    assert v.patch("/organization", json={"name": "My Test Hospital"}).status_code == 200
    assert v.get("/organization").json()["name"] == "My Test Hospital"
    r = v.post("/appointment-types", json={"name": "Demo consult", "duration_minutes": 30, "color": "blue"})
    assert r.status_code == 201, r.text
    mons = v.get("/monitors").json()
    key = mons[0]["key"]
    assert v.patch(f"/monitors/{key}", json={"is_enabled": False}).status_code == 200
    assert next(m for m in v.get("/monitors").json() if m["key"] == key)["is_enabled"] is False
    code = v.get("/fee-schedule").json()[0]["code"]
    assert v.put(f"/fee-schedule/{code}", json={"description": "Edited in demo", "price_cents": 12345}).status_code == 200
    # Staff: an "invited" person is created directly and can be switched to.
    r = v.post("/invitations", json={"email": "new.nurse@example.com", "first_name": "Nia", "last_name": "Newhire", "roles": ["nurse"]})
    assert r.status_code == 201, r.text
    people = v.get("/auth/demo/session").json()["people"]
    nia = next(p for p in people if p["name"] == "Nia Newhire")
    v.switch(user_id=nia["user_id"])
    assert v.me["memberships"][0]["roles"] == ["nurse"]
    # Invitations to a demo hospital can never be accepted (that would create a real password account).
    tok = r.json()["invite_link"].split("token=")[1]
    assert TestClient(app).post("/api/v1/auth/invitations/accept", json={"token": tok, "password": "Str0ng-Passw0rd!x"}).status_code == 400


def test_platform_level_actions_stay_blocked(app, demo):
    v = Visitor(app, "198.51.100.80").enter("super_admin")
    assert v.post("/organizations", json={"name": "X", "slug": "x-org", "first_clinic_name": "A", "first_clinic_code": "AAA"}).status_code == 403
    assert v.get("/admin/ai-owner").status_code == 403
    assert v.put("/admin/ai-owner/demo", json={"enabled": True}).status_code == 403
    assert v.post("/auth/password/change", json={"current_password": "x", "new_password": "Another!Pass99"}).status_code == 403
    assert v.post("/auth/mfa/setup").status_code == 403
    assert v.post("/auth/email/change", json={"new_email": "a@b.co", "current_password": "x"}).status_code == 403
    r = v.patch("/organization", json={"settings": {"synthetic_data": False}})
    assert r.status_code == 403 and "synthetic_data" in r.text
    assert v.patch("/organization", json={"status": "suspended"}).status_code == 403
    # AI settings are this visitor's own (never the platform's), and the platform key is never shown.
    s = v.get("/admin/ai-settings").json()
    assert s["source"] == "demo-session" and s["key"]["hint"] is None


def test_demo_ai_scope_is_per_visitor_and_survives_role_switches(app, demo):
    v = Visitor(app, "198.51.100.90").enter("super_admin")
    r = v.put("/admin/ai-settings", json={"provider": "simulated", "text_model": "gpt-4.1-mini"})
    assert r.status_code == 200, r.text
    assert v.get("/admin/ai-settings").json()["models"]["text"] == "gpt-4.1-mini"
    v.switch(key="doctor")
    v.switch(key="super_admin")
    assert v.get("/admin/ai-settings").json()["models"]["text"] == "gpt-4.1-mini"  # same lease → same AI settings
    w = Visitor(app, "198.51.100.91").enter("super_admin")
    assert w.get("/admin/ai-settings").json()["agent_models"] == {}  # another visitor starts from the defaults
    assert w.get("/admin/ai-settings").json()["key"]["configured"] is False


def test_platform_ai_key_is_never_used_for_a_demo_hospital(app, demo, monkeypatch):
    from app.agents import case_assist
    from app.ai import config as aiconfig
    from app.ai.config import EffectiveAI

    v = Visitor(app, "198.51.100.95").enter("pharmacist")
    plat = EffectiveAI(provider="openai", api_key="sk-platform-not-for-demo", text_model="gpt-4.1-mini", source="ui")
    monkeypatch.setattr(aiconfig, "platform_effective", lambda: plat)
    import uuid

    eff, scope, why = case_assist._provider(SessionLocal(), uuid.UUID(v.org), "pharmacy_watchdog")
    assert eff is None or eff.api_key != "sk-platform-not-for-demo"
    db = SessionLocal()
    assert sandbox.default_ai_scope(db, uuid.UUID(v.org)) == f"org:{v.org}"
    assert sandbox.default_ai_scope(db, _harborview(db)) is None
    db.close()


# ---------------------------------------------------------------------------------------------- Phase 6: reset & expiry

def test_reset_gives_a_fresh_hospital_and_removes_only_the_old_one(app, demo):
    db = SessionLocal()
    hv = _harborview(db)
    hv_before = _org_rows(db, hv)
    db.close()
    v = Visitor(app, "198.51.100.110").enter("doctor")
    other = Visitor(app, "198.51.100.111").enter("doctor")
    other_before = None
    db = SessionLocal()
    other_before = _org_rows(db, other.org)
    db.close()
    old_org, old_h = v.org, dict(v.h)
    pid = v.post("/patients", json={"first_name": "Reset", "last_name": "Me", "date_of_birth": "1980-02-02", "sex_at_birth": "male"}).json()["id"]
    assert v.c.post("/api/v1/auth/demo/reset", headers=v.h, json={"confirm": "nope"}).status_code == 400
    r = v.c.post("/api/v1/auth/demo/reset", headers=v.h, json={"confirm": "RESET"})
    assert r.status_code == 200, r.text
    v._accept(r.json())
    assert v.org != old_org and v.get("/auth/demo/session").json()["role_key"] == "doctor"
    assert v.get(f"/patients/{pid}").status_code == 404                      # fresh initial state
    assert v.c.get("/api/v1/auth/me", headers=old_h).status_code == 401       # old hospital's sessions are gone
    db = SessionLocal()
    assert _org_rows(db, old_org) == 0                                        # every record of the old hospital removed
    assert not db.scalar(select(User.id).where(User.sandbox_org_id == old_org))
    assert db.get(Organization, old_org) is None
    assert _org_rows(db, hv) == hv_before                                     # real organization untouched
    assert _org_rows(db, other.org) == other_before                           # the other visitor untouched
    assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "demo.sandbox_purged"))  # lifecycle kept platform-level
    db.close()
    assert other.get("/patients").status_code == 200


def test_idle_and_maximum_expiry_end_the_demo(app, demo):
    v = Visitor(app, "198.51.100.120").enter("nurse")
    db = SessionLocal()
    sb = db.scalar(select(DemoSandbox).where(DemoSandbox.organization_id == v.org))
    sb.last_active_at = now() - timedelta(hours=settings.demo_sandbox_idle_hours, minutes=5)
    db.commit()
    db.close()
    r = v.get("/patients")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "demo_expired"
    out = sandbox.maintain(build_limit=0)
    assert out["expired"] >= 1 and out["purged"] >= 1
    db = SessionLocal()
    assert db.get(Organization, v.org) is None
    assert db.scalar(select(func.count()).select_from(UserSession).where(UserSession.sandbox_lease_id == sb.lease_id)) == 0
    db.close()
    w = Visitor(app, "198.51.100.121").enter("nurse")
    db = SessionLocal()
    sb = db.scalar(select(DemoSandbox).where(DemoSandbox.organization_id == w.org))
    sb.expires_at = now() - timedelta(minutes=1)
    db.commit()
    db.close()
    assert w.get("/patients").status_code == 401


def test_append_only_records_of_real_organizations_stay_immutable(app, demo):
    """The purge exception only applies to a registered demo hospital that is being purged."""
    v = Visitor(app, "198.51.100.130").enter("doctor")
    db = SessionLocal()
    hv = _harborview(db)
    for org in (hv, v.org):  # neither a real org nor a LEASED demo hospital can lose audit history
        with pytest.raises(Exception, match="append-only"):
            db.execute(text("SELECT set_config('app.sandbox_purge', :o, true)"), {"o": str(org)})
            db.execute(text("DELETE FROM audit_events WHERE organization_id = :o"), {"o": org})
        db.rollback()
    db.close()


def test_pool_is_replenished_and_stale_pool_hospitals_retired(app, demo, monkeypatch):
    monkeypatch.setattr(settings, "demo_sandbox_pool_size", 1)
    out = sandbox.maintain(build_limit=1)
    assert out["built"] == 1
    db = SessionLocal()
    sb = db.scalar(select(DemoSandbox).where(DemoSandbox.status == "ready"))
    hv = _harborview(db)
    assert sb.organization_id in sandbox.inactive_sandbox_org_ids(db) and hv not in sandbox.inactive_sandbox_org_ids(db)
    sb.ready_at = now() - timedelta(days=1)
    db.commit()
    db.close()
    out = sandbox.maintain(build_limit=0)
    assert out["retired"] == 1 and out["purged"] >= 1


def test_live_integration_adapter_fails_closed(app, demo, monkeypatch):
    monkeypatch.setattr(settings, "clearinghouse_adapter", "live-x12")
    r = TestClient(app, client=("198.51.100.140", 1)).post("/api/v1/auth/demo-login", json={"key": "billing"})
    assert r.status_code == 503 and "external integration" in r.text


def test_demo_mode_off_disables_hospital_identities(app, demo, monkeypatch):
    v = Visitor(app, "198.51.100.150").enter("doctor")
    monkeypatch.setattr(settings, "demo_mode", False)
    assert v.get("/patients").status_code == 401


def test_same_browser_keeps_its_hospital_when_choosing_another_demo_role(app, demo):
    v = Visitor(app, "198.51.100.160").enter("doctor")
    org = v.org
    v.enter("billing")  # same browser (refresh cookie) clicks another demo button
    assert v.org == org and "billing" in v.membership["roles"]
    fresh = Visitor(app, "198.51.100.160").enter("billing")  # a new browser from the same address gets its own hospital
    assert fresh.org != org


def test_per_address_limit(app, demo, monkeypatch):
    monkeypatch.setattr(settings, "demo_sandbox_per_visitor", 1)
    Visitor(app, "198.51.100.170").enter("doctor")
    r = TestClient(app, client=("198.51.100.170", 1)).post("/api/v1/auth/demo-login", json={"key": "doctor"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "demo_unavailable"
