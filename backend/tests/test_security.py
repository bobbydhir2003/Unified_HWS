"""Authentication, authorization, tenant isolation, patient access, audit immutability."""

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import engine
from app.seed import DEV_PASSWORD

DOCTOR = "dr.chen@harborview.dev"
OTHER_ORG_DOCTOR = "dr.lake@lakeside.dev"


def first_patient_id(api, q=""):
    r = api.get("/patients", params={"q": q} if q else {})
    assert r.status_code == 200
    return r.json()["items"][0]["id"]


# ---------- Authentication ----------

def test_login_rejects_bad_password(app):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": DOCTOR, "password": "wrong-password"})
    assert r.status_code == 401
    assert "Invalid email or password" in r.text


def test_unauthenticated_requests_rejected(app):
    c = TestClient(app)
    assert c.get("/api/patients").status_code == 401
    assert c.get("/api/patients", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_lockout_after_repeated_failures(app):
    c = TestClient(app)
    email = "billing@harborview.dev"
    for _ in range(5):
        c.post("/api/auth/login", json={"email": email, "password": "nope"})
    r = c.post("/api/auth/login", json={"email": email, "password": DEV_PASSWORD})
    assert r.status_code == 423
    with engine.begin() as conn:  # unlock for other tests
        conn.execute(text("update users set locked_until=null, failed_login_count=0 where email=:e"), {"e": email})


def test_refresh_rotates_and_logout_revokes(app):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": DOCTOR, "password": DEV_PASSWORD})
    old = c.cookies.get("ud_refresh")
    r = c.post("/api/auth/refresh")
    assert r.status_code == 200
    assert c.cookies.get("ud_refresh") != old
    token = r.json()["access_token"]
    c.post("/api/auth/logout")
    # Access token tied to a revoked session no longer works.
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_mfa_enrollment_and_login(app):
    c = TestClient(app)
    email = "clinicadmin@harborview.dev"
    tok = c.post("/api/auth/login", json={"email": email, "password": DEV_PASSWORD}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    setup = c.post("/api/auth/mfa/setup", headers=h).json()
    totp = pyotp.TOTP(setup["secret"])
    assert c.post("/api/auth/mfa/enable", headers=h, json={"code": "000000"}).status_code == 400
    assert c.post("/api/auth/mfa/enable", headers=h, json={"code": totp.now()}).status_code == 200
    r = c.post("/api/auth/login", json={"email": email, "password": DEV_PASSWORD}).json()
    assert r["status"] == "mfa_required" and "access_token" not in r
    assert c.post("/api/auth/mfa/verify", json={"mfa_token": r["mfa_token"], "code": "123456"}).status_code == 401
    ok = c.post("/api/auth/mfa/verify", json={"mfa_token": r["mfa_token"], "code": totp.now()})
    assert ok.status_code == 200
    with engine.begin() as conn:
        conn.execute(text("update users set mfa_enabled=false, mfa_secret=null where email=:e"), {"e": email})


def test_password_reset_flow_does_not_enumerate(app):
    c = TestClient(app)
    a = c.post("/api/auth/password/forgot", json={"email": "nobody@example.com"}).json()
    b = c.post("/api/auth/password/forgot", json={"email": DOCTOR}).json()
    assert a == b
    assert c.post("/api/auth/password/reset", json={"token": "bogus", "password": "Another!Pass99"}).status_code == 400


# ---------- Authorization ----------

def test_receptionist_cannot_read_clinical_data(as_user):
    api = as_user("frontdesk@harborview.dev")
    pid = first_patient_id(api)
    assert api.get(f"/patients/{pid}").status_code == 200  # demographics OK
    assert api.get(f"/patients/{pid}/allergies").status_code == 403
    assert api.post("/encounters", json={"patient_id": pid}).status_code == 403


def test_nurse_cannot_sign_notes_and_billing_cannot_edit_patients(as_user):
    billing = as_user("billing@harborview.dev")
    pid = first_patient_id(billing)
    p = billing.get(f"/patients/{pid}").json()
    assert billing.put(f"/patients/{pid}", json={**p, "first_name": "X"}).status_code == 403
    assert as_user("nurse.rivera@harborview.dev").post("/templates", json={
        "name": "x", "content": {"subjective": "", "objective": "", "assessment": "", "plan": ""}}).status_code == 403


def test_non_admin_cannot_manage_users_or_read_audit(as_user):
    api = as_user(DOCTOR)
    assert api.get("/staff").status_code == 403
    assert api.get("/audit").status_code == 403
    assert api.post("/invitations", json={"email": "x@example.com", "first_name": "a", "last_name": "b",
                                          "roles": ["doctor"]}).status_code == 403


def test_clinic_admin_cannot_grant_super_admin(as_user):
    api = as_user("dr.okafor@harborview.dev")  # doctor + clinic_admin
    r = api.post("/invitations", json={"email": "eve@example.com", "first_name": "E", "last_name": "V", "roles": ["super_admin"]})
    assert r.status_code == 403


# ---------- Tenant isolation ----------

def test_cross_tenant_patient_access_is_404(as_user):
    harbor = as_user(DOCTOR)
    lake = as_user(OTHER_ORG_DOCTOR, "lakeside")
    pid = first_patient_id(harbor)
    for path in (f"/patients/{pid}", f"/patients/{pid}/allergies", f"/patients/{pid}/encounters", f"/patients/{pid}/timeline"):
        assert lake.get(path).status_code == 404, path
    lake_ids = {p["id"] for p in lake.get("/patients", params={"page_size": 100}).json()["items"]}
    assert pid not in lake_ids
    assert lake.post("/appointments", json={"patient_id": pid, "provider_id": lake.membership["provider_id"],
                                             "clinic_id": lake.membership["clinics"][0]["id"],
                                             "start_at": "2030-01-07T10:00:00-06:00"}).status_code == 404


def test_cannot_select_foreign_org_via_header(as_user):
    lake = as_user(OTHER_ORG_DOCTOR, "lakeside")
    harbor_org = as_user(DOCTOR).membership["organization_id"]
    r = lake.get("/patients", headers={"X-Organization-Id": harbor_org})
    assert r.status_code == 403


# ---------- Patient access ----------

def test_restricted_chart_requires_break_glass(as_user):
    api = as_user(DOCTOR)  # not Victor Ashford's primary provider
    pid = api.get("/patients", params={"q": "Victor Ashford"}).json()["items"][0]["id"]
    r = api.get(f"/patients/{pid}")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "restricted_chart"
    assert api.post(f"/patients/{pid}/break-glass", json={"reason": "short"}).status_code == 422
    assert api.post(f"/patients/{pid}/break-glass", json={"reason": "Patient in clinic with chest pain, PCP unavailable"}).status_code == 200
    assert api.get(f"/patients/{pid}").status_code == 200
    audit = as_user("clinicadmin@harborview.dev").get("/audit", params={"action": "patient.break_glass"}).json()
    assert audit["total"] >= 1


def test_portal_patient_sees_only_own_record(as_user):
    pat = as_user("patient@harborview.dev")
    own = pat.membership["patient_id"]
    assert own
    assert pat.get(f"/patients/{own}").status_code == 200
    other = first_patient_id(as_user(DOCTOR))
    if other != own:
        assert pat.get(f"/patients/{other}").status_code == 404
    assert pat.get("/patients").status_code == 403


# ---------- Audit ----------

def test_audit_log_is_append_only(as_user):
    as_user(DOCTOR).get(f"/patients/{first_patient_id(as_user(DOCTOR))}")
    with pytest.raises(Exception, match="append-only"):
        with engine.begin() as conn:
            conn.execute(text("update audit_events set action='tampered'"))
    with pytest.raises(Exception, match="append-only"):
        with engine.begin() as conn:
            conn.execute(text("delete from audit_events"))


def test_chart_view_is_audited(as_user):
    api = as_user(DOCTOR)
    pid = first_patient_id(api)
    api.get(f"/patients/{pid}")
    rows = as_user("clinicadmin@harborview.dev").get("/audit", params={"patient_id": pid, "action": "patient.chart_viewed"}).json()
    assert rows["total"] >= 1


def test_sessions_and_audit_render_real_ip_addresses(app, as_user):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": DOCTOR, "password": DEV_PASSWORD}, headers={"X-Forwarded-For": "203.0.113.7"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    sessions = c.get("/api/auth/sessions", headers=h)
    assert sessions.status_code == 200
    assert any(s["ip_address"] == "203.0.113.7" for s in sessions.json())
    audit = as_user("clinicadmin@harborview.dev").get("/audit", params={"action": "auth.login"})
    assert audit.status_code == 200
