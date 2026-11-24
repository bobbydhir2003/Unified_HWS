"""Terminology (full ICD-10-CM release, validation, unlicensed systems reported) and versioned order sets
(authorized publishing, versioning, apply → draft orders only, all-or-nothing validation, audit)."""

DOC, ADMIN, NURSE = "dr.santos@harborview.dev", "hospitaladmin@harborview.dev", "nurse.kim@harborview.dev"


def test_icd10cm_release_search_and_validation(as_user):
    doc = as_user(DOC)
    systems = {s["system"]: s for s in doc.get("/terminology/systems").json()}
    assert systems["ICD-10-CM"]["status"] == "loaded" and systems["ICD-10-CM"]["concepts"] > 70000
    assert systems["CPT"]["status"] == "not_licensed"  # an unlicensed dependency is reported, not hidden
    hits = doc.get("/codes/icd10", params={"q": "type 2 diabetes without complications"}).json()
    assert any(h["code"] == "E11.9" for h in hits)
    assert doc.get("/codes/icd10", params={"q": "J029"}).json()[0]["code"] == "J02.9"
    assert doc.get("/terminology/ICD-10-CM/codes/i10").json()["description"].startswith("Essential")

    p = doc.get("/patients", params={"q": "a"}).json()["items"][0]
    clinic = doc.membership["clinics"][0]
    enc = doc.post("/encounters", json={"patient_id": p["id"], "clinic_id": clinic["id"], "chief_complaint": "Terminology check"}).json()
    bad = doc.put(f"/encounters/{enc['id']}/diagnoses", json=[{"code": "Z99.999", "description": "Made up", "rank": 1}])
    assert bad.status_code == 400 and "not an ICD-10-CM code" in bad.text
    ok = doc.put(f"/encounters/{enc['id']}/diagnoses", json=[{"code": "i10", "description": "Hypertension", "rank": 1}])
    assert ok.status_code == 200, ok.text


def test_order_set_lifecycle_and_apply(as_user):
    doc, admin, nurse = as_user(DOC), as_user(ADMIN), as_user(NURSE)
    item = {"order_type": "lab", "details": {"code": "58410-2"}}
    assert doc.post("/order-sets", json={"name": "Not allowed", "items": [item]}).status_code == 403  # publishing is authorized
    assert admin.post("/order-sets", json={"name": "Bad", "items": [{"order_type": "lab", "details": {"code": "NOPE"}}]}).status_code == 400
    s = admin.post("/order-sets", json={"name": "Test labs (demonstration)", "items": [item, {"order_type": "nursing", "details": {"instruction": "Vital signs", "frequency": "q4h"}}]}).json()
    assert s["status"] == "draft"
    assert all(x["id"] != s["id"] for x in doc.get("/order-sets").json())  # drafts are not offered to clinicians
    v1 = admin.post(f"/order-sets/{s['id']}/publish").json()
    assert v1["status"] == "published" and v1["published_by"]
    v2 = admin.post(f"/order-sets/{s['id']}/new-version").json()
    assert v2["version"] == 2 and v2["status"] == "draft"
    assert admin.put(f"/order-sets/{s['id']}", json={"name": "x" * 5, "items": [item]}).status_code == 400  # published is immutable
    admin.put(f"/order-sets/{v2['id']}", json={"name": "Test labs v2 (demonstration)", "items": [item]})
    admin.post(f"/order-sets/{v2['id']}/publish")
    r = admin.get(f"/order-sets/{s['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "retired"
    assert doc.post(f"/order-sets/{s['id']}/apply", json={"patient_id": "00000000-0000-0000-0000-000000000000", "items": [{"item_id": v1["items"][0]["id"]}]}).status_code == 400

    p = doc.get("/patients", params={"q": "a"}).json()["items"][0]
    v2 = doc.get(f"/order-sets/{v2['id']}").json()
    # All-or-nothing: an invalid edit creates nothing.
    before = len(doc.get(f"/patients/{p['id']}/orders").json())
    bad = doc.post(f"/order-sets/{v2['id']}/apply", json={"patient_id": p["id"], "items": [{"item_id": v2["items"][0]["id"], "details": {"code": "NOPE"}}]})
    assert bad.status_code == 400 and len(doc.get(f"/patients/{p['id']}/orders").json()) == before
    r = doc.post(f"/order-sets/{v2['id']}/apply", json={"patient_id": p["id"], "items": [{"item_id": v2["items"][0]["id"]}]})
    assert r.status_code == 201
    orders = r.json()["orders"]
    assert len(orders) == 1 and orders[0]["status"] == "draft"  # applying never signs
    assert nurse.post(f"/orders/{orders[0]['id']}/sign", json={}).status_code == 403
    assert doc.post(f"/orders/{orders[0]['id']}/sign", json={}).json()["status"] == "transmitted"
