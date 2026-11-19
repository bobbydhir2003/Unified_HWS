"""Facility hierarchy, department scope, new roles, and PostgreSQL row-level security (defense in depth)."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.db import SessionLocal, bind_tenant
from app.core.rls import RLS_EXEMPT
from app.models import Organization, Patient


def test_every_tenant_table_has_rls():
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT c.table_name, t.relrowsecurity FROM information_schema.columns c JOIN pg_class t ON t.relname = c.table_name "
            "WHERE c.table_schema = 'public' AND c.column_name = 'organization_id'")).all()
        missing = [name for name, rls in rows if not rls and name not in RLS_EXEMPT]
        assert rows and not missing, f"tables without row-level security: {missing}"
    finally:
        db.close()


def test_database_blocks_cross_tenant_even_without_app_filters():
    db = SessionLocal()
    try:
        hv = db.scalar(select(Organization).where(Organization.slug == "harborview"))
        lake = db.scalar(select(Organization).where(Organization.slug == "lakeside"))
        lake_patient = db.scalar(select(Patient.id).where(Patient.organization_id == lake.id))
        db.rollback()
        bind_tenant(db, hv.id)
        # A buggy query with no organization filter still cannot see the other tenant's rows.
        assert db.scalar(text("SELECT count(*) FROM patients WHERE id = :i"), {"i": lake_patient}) == 0
        assert db.scalar(text("SELECT count(DISTINCT organization_id) FROM patients")) == 1
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE patients SET organization_id = :o WHERE organization_id = :h"), {"o": lake.id, "h": hv.id})
        db.rollback()
        with pytest.raises(DBAPIError):
            db.execute(text("INSERT INTO departments (id, organization_id, facility_id, name, code, kind, is_active, settings) "
                            "SELECT gen_random_uuid(), :o, id, 'X', 'X', 'support', true, '{}' FROM clinics LIMIT 1"), {"o": lake.id})
        db.rollback()
    finally:
        db.close()


def _fac(api, code):
    return next(f for f in api.get("/facilities").json() if f["code"] == code)


def test_hierarchy_and_department_scope(as_user):
    admin = as_user("hospitaladmin@harborview.dev")
    pharm = as_user("pharmacist@harborview.dev")
    facs = {f["code"]: f for f in as_user("clinicadmin@harborview.dev").get("/facilities").json()}
    assert facs["HGH"]["facility_type"] == "hospital" and facs["HGH"]["bed_count"] >= 40
    # Pharmacist is scoped to the hospital only.
    assert [f["code"] for f in pharm.get("/facilities").json()] == ["HGH"]
    assert pharm.get("/departments", params={"facility_id": facs["HDT"]["id"]}).status_code == 403
    assert pharm.post("/departments", json={"facility_id": facs["HGH"]["id"], "name": "Dialysis", "code": "DIAL"}).status_code == 403
    # Admin builds a unit and generates rooms/beds; codes are unique per facility.
    d = admin.post("/departments", json={"facility_id": facs["HGH"]["id"], "name": "Dialysis", "code": "DIAL", "kind": "inpatient"})
    assert d.status_code == 201, d.text
    unit = admin.post("/locations", json={"facility_id": facs["HGH"]["id"], "department_id": d.json()["id"], "kind": "unit",
                                          "name": "Dialysis Unit", "code": "DU"}).json()
    made = admin.post(f"/locations/{unit['id']}/generate", json={"rooms": 2, "beds_per_room": 2})
    assert made.status_code == 201 and sum(1 for x in made.json() if x["kind"] == "bed") == 4
    assert all(x["bed_status"] == "available" for x in made.json() if x["kind"] == "bed")
    assert admin.post(f"/locations/{unit['id']}/generate", json={"rooms": 1, "beds_per_room": 1}).status_code == 409
    # A bed cannot be created without a room/unit parent.
    bad = admin.post("/locations", json={"facility_id": facs["HGH"]["id"], "kind": "bed", "name": "Orphan", "code": "ORPH"})
    assert bad.status_code == 400
    # Another organization can't see this facility's locations.
    lake = as_user("dr.lake@lakeside.dev", "lakeside")
    assert lake.get("/locations", params={"facility_id": facs["HGH"]["id"]}).status_code == 404
