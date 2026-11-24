"""Header role switcher (workspaces): one real account, all 14 roles for a platform Super Admin, enforced on the server
for every request (X-Acting-Role), the real person kept in every audit record, and no safeguard bypassed by switching.
Also: the former Demo Mode is gone (its endpoints no longer exist; its data can be retired)."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.core.db import SessionLocal
from app.core.permissions import Role
from app.models import AuditEvent, InventoryItem, Organization, Patient, User, UserSession

ADMIN = "admin@undeclared.dev"


def test_platform_super_admin_gets_all_fourteen_workspaces(as_user):
    admin = as_user(ADMIN)
    ws = admin.membership["workspaces"]
    assert [w["role"] for w in ws] == [r.value for r in Role] and len(ws) == 14
    assert next(w for w in ws if w["role"] == "doctor")["label"] == "Doctor"
    assert as_user("frontdesk@harborview.dev").membership["workspaces"] == []        # single role: no switcher
    assert {w["role"] for w in as_user("dr.okafor@harborview.dev").membership["workspaces"]} == {"doctor", "clinic_admin"}


def test_the_acting_role_is_enforced_by_the_server(as_user):
    admin = as_user(ADMIN)
    assert admin.get("/command/summary").status_code == 200
    assert admin.act("doctor").get("/command/summary").status_code == 403          # doctors don't have the Command Center
    assert admin.act("doctor").get("/patients").status_code == 200
    assert admin.act("pharmacist").get("/inventory/items").status_code == 200
    assert admin.act("receptionist").get("/inventory/items").status_code == 403
    assert admin.act("patient").get("/patients").status_code == 403                # the patient workspace is the portal only
    assert admin.act("not_a_role").get("/patients").status_code == 400


def test_other_accounts_cannot_switch_beyond_their_own_roles(as_user):
    fd = as_user("frontdesk@harborview.dev")
    assert fd.act("doctor").get("/patients").status_code == 403
    assert fd.act("super_admin").get("/command/summary").status_code == 403
    assert fd.act("receptionist").get("/patients").status_code == 200              # their own role is fine
    okafor = as_user("dr.okafor@harborview.dev")
    assert okafor.act("clinic_admin").get("/staff").status_code == 200
    assert okafor.act("doctor").get("/staff").status_code == 403
    assert okafor.act("billing").get("/patients").status_code == 403
    db = SessionLocal()
    fd_id = db.scalar(select(User.id).where(User.email == "frontdesk@harborview.dev"))
    denied = db.scalars(select(AuditEvent).where(AuditEvent.actor_user_id == fd_id, AuditEvent.action == "access.denied")).all()
    assert any((e.details or {}).get("acting_role") == "super_admin" for e in denied)
    db.close()


def test_audit_keeps_the_real_person_and_records_the_workspace(as_user):
    admin = as_user(ADMIN)
    r = admin.act("receptionist").post("/patients", json={"first_name": "Work", "last_name": f"Space{uuid.uuid4().hex[:4]}",
                                                          "date_of_birth": "1980-01-01", "sex_at_birth": "male", "confirm_not_duplicate": True})
    assert r.status_code == 201, r.text
    db = SessionLocal()
    ev = db.scalar(select(AuditEvent).where(AuditEvent.patient_id == uuid.UUID(r.json()["id"])).order_by(AuditEvent.created_at))
    admin_id = db.scalar(select(User.id).where(User.email == ADMIN))
    assert ev.actor_user_id == admin_id and ev.details.get("acting_role") == "receptionist"
    db.close()


def test_switching_never_bypasses_clinical_or_two_person_safeguards(as_user):
    admin = as_user(ADMIN)
    doc = admin.act("doctor")
    p = doc.post("/patients", json={"first_name": "Safe", "last_name": f"Guard{uuid.uuid4().hex[:4]}", "date_of_birth": "1975-03-03",
                                    "sex_at_birth": "female", "confirm_not_duplicate": True}).json()
    o = doc.post("/orders", json={"patient_id": p["id"], "order_type": "lab", "details": {"code": "57698-3"}}).json()
    r = doc.post(f"/orders/{o['id']}/sign", json={})
    assert r.status_code == 403 and "provider profile" in r.text                 # signing needs a real provider identity
    # Requester and approver are the same person whatever workspace they use.
    db = SessionLocal()
    item = db.scalar(select(InventoryItem.id).join(Organization, Organization.id == InventoryItem.organization_id)
                     .where(Organization.slug == "harborview").limit(1))
    db.close()
    pr = admin.act("pharmacist").post("/purchase-requests", json={"item_id": str(item), "quantity": 5, "reason": "workspace test"})
    assert pr.status_code == 201, pr.text
    r = admin.act("hospital_admin").post(f"/purchase-requests/{pr.json()['id']}/decide", json={"approve": True})
    assert r.status_code == 400 and "own request" in r.text
    # Restricted charts stay restricted in every workspace.
    db = SessionLocal()
    vip = db.scalar(select(Patient.id).where(Patient.is_restricted.is_(True)).limit(1))
    db.close()
    for role in ("super_admin", "doctor", "nurse"):
        assert admin.act(role).get(f"/patients/{vip}").status_code == 403
    # The patient workspace shows only the signed-in person's own record (the admin has none).
    me = admin.act("patient").get("/portal/readiness")
    assert me.status_code in (403, 404), me.text
    assert as_user("patient@harborview.dev").get("/portal/readiness").status_code == 200  # a real patient sees their own


def test_monitors_and_assistants_run_from_workspaces(as_user):
    admin = as_user(ADMIN)
    mons = [m for m in admin.get("/monitors").json() if not m["key"].startswith("test.")]
    assert len(mons) == 22
    assert admin.post(f"/monitors/{mons[0]['key']}/run").status_code == 200
    assert admin.act("doctor").post(f"/monitors/{mons[0]['key']}/run").status_code == 403   # configuration needs an admin workspace
    agents = {a["key"]: a for a in admin.get("/agents").json()}
    assert len(agents) == 10
    r = admin.act("insurance_specialist").post("/agents/insurance_guardian/run", json={"input": "What needs attention today?"})
    assert r.status_code == 200 and r.json()["status"] in ("succeeded", "blocked")
    assert admin.act("receptionist").post("/agents/pharmacy_watchdog/run", json={"input": "Stock status?"}).status_code in (400, 403)


def test_demo_mode_is_gone(app):
    c = TestClient(app)
    for path, method in (("/api/v1/auth/demo", "get"), ("/api/v1/auth/demo-login", "post"), ("/api/v1/auth/demo/switch", "post"),
                         ("/api/v1/auth/demo/reset", "post"), ("/api/v1/auth/demo/session", "get"), ("/api/v1/admin/ai-owner/demo", "put")):
        r = getattr(c, method)(path, json={"key": "doctor"}) if method != "get" else c.get(path)
        assert r.status_code in (404, 405), (path, r.status_code)


def test_retire_demo_removes_only_demo_owned_data(as_user):
    """A leftover demo hospital (as the former Demo Mode left them) is removed; Harborview and real accounts are not."""
    from app import cli
    from app.core.security import now
    from app.models import DemoSandbox, Membership, MembershipRole

    db = SessionLocal()
    hv = db.scalar(select(Organization.id).where(Organization.slug == "harborview"))
    hv_patients = db.scalar(select(func.count()).select_from(Patient).where(Patient.organization_id == hv))
    users_before = db.scalar(select(func.count()).select_from(User).where(User.sandbox_org_id.is_(None)))
    tag = uuid.uuid4().hex[:8]
    org = Organization(name="Old demo hospital", slug=f"demo-{tag}", settings={"synthetic_data": True, "sandbox": True})
    db.add(org)
    db.flush()
    db.add(Patient(organization_id=org.id, mrn=f"D{tag}", first_name="Old", last_name="Demo", date_of_birth=now().date(), sex_at_birth="female"))
    ident = User(email=f"dr.chen@{tag}.demo.example.com", first_name="Maya", last_name="Chen", sandbox_org_id=org.id)
    db.add(ident)
    db.flush()
    m = Membership(user_id=ident.id, organization_id=org.id, all_clinics=True)
    db.add(m)
    db.flush()
    m.roles.append(MembershipRole(role="doctor"))
    lease = uuid.uuid4()
    db.add(UserSession(user_id=ident.id, refresh_token_hash=uuid.uuid4().hex, created_at=now(), last_used_at=now(), expires_at=now(),
                       sandbox_lease_id=lease))
    db.add(DemoSandbox(tag=tag, organization_id=org.id, status="leased", lease_id=lease, created_at=now()))
    db.commit()
    org_id = org.id
    db.close()
    out = cli.retire_demo(ask=lambda _: "RETIRE DEMO")
    assert out["hospitals_removed"] >= 1
    db = SessionLocal()
    assert db.get(Organization, org_id) is None
    assert not db.scalar(select(User.id).where(User.sandbox_org_id == org_id))
    assert db.scalar(select(func.count()).select_from(Patient).where(Patient.organization_id == hv)) == hv_patients
    assert db.scalar(select(func.count()).select_from(User).where(User.sandbox_org_id.is_(None))) == users_before
    assert db.scalar(select(User.is_active).where(User.email == ADMIN))
    # Real organizations' append-only history stays immutable.
    try:
        db.execute(text("SELECT set_config('app.sandbox_purge', :o, true)"), {"o": str(hv)})
        db.execute(text("DELETE FROM audit_events WHERE organization_id = :o"), {"o": hv})
        raise AssertionError("audit history of a real organization was deletable")
    except Exception as e:  # noqa: BLE001
        assert "append-only" in str(e)
    db.rollback()
    db.close()
    as_user(ADMIN).get("/auth/me")  # the platform admin still works
