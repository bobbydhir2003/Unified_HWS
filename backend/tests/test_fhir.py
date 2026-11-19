"""FHIR R4 read API: resource shape, bundles, scoping, OperationOutcome errors, isolation."""

DOCTOR, FRONT, PATIENT = "dr.chen@harborview.dev", "frontdesk@harborview.dev", "patient@harborview.dev"


def test_capability_statement(as_user):
    r = as_user(DOCTOR).get("/fhir/R4/metadata")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/fhir+json")
    cs = r.json()
    assert cs["resourceType"] == "CapabilityStatement" and cs["fhirVersion"] == "4.0.1"
    assert {x["type"] for x in cs["rest"][0]["resource"]} >= {"Patient", "Observation", "Condition"}


def test_patient_read_and_clinical_bundles(as_user):
    doc = as_user(DOCTOR)
    pid = doc.get("/patients", params={"q": "Elena Moreau"}).json()["items"][0]["id"]
    p = doc.get(f"/fhir/R4/Patient/{pid}").json()
    assert p["resourceType"] == "Patient" and p["identifier"][0]["value"].startswith("UD") and p["birthDate"] == "1986-04-12"
    for rtype in ("Encounter", "Condition", "AllergyIntolerance", "MedicationStatement", "Observation"):
        b = doc.get(f"/fhir/R4/{rtype}", params={"patient": f"Patient/{pid}"}).json()
        assert b["resourceType"] == "Bundle" and b["type"] == "searchset" and b["total"] == len(b["entry"])
        assert all(e["resource"]["resourceType"] == rtype for e in b["entry"])
    vit = doc.get("/fhir/R4/Observation", params={"patient": pid, "category": "vital-signs"}).json()
    if vit["entry"]:
        codes = {c["code"]["coding"][0]["code"] for e in vit["entry"] for c in e["resource"]["component"]}
        assert codes & {"8480-6", "8867-4"}  # LOINC systolic / heart rate
    s = doc.get("/fhir/R4/Patient", params={"family": "Moreau", "birthdate": "1986-04-12"}).json()
    assert any(e["resource"]["id"] == pid for e in s["entry"])


def test_fhir_errors_are_operation_outcomes_and_access_is_enforced(as_user):
    doc, front, pat = as_user(DOCTOR), as_user(FRONT), as_user(PATIENT)
    r = doc.get("/fhir/R4/Condition")
    assert r.status_code == 400 and r.json()["resourceType"] == "OperationOutcome"
    pid = doc.get("/patients", params={"q": "Elena Moreau"}).json()["items"][0]["id"]
    r = front.get("/fhir/R4/Condition", params={"patient": pid})  # receptionist lacks clinical:read
    assert r.status_code == 403 and r.json()["resourceType"] == "OperationOutcome"
    own = pat.get("/fhir/R4/Patient").json()
    assert own["total"] == 1 and own["entry"][0]["resource"]["id"] == pat.membership["patient_id"]
    other = doc.get("/patients", params={"q": "Victor Ashford"}).json()["items"][0]["id"]
    assert doc.get(f"/fhir/R4/Patient/{other}").status_code == 403  # restricted chart still enforced via FHIR
    lake = as_user("dr.lake@lakeside.dev", "lakeside")
    r = lake.get(f"/fhir/R4/Patient/{pid}")
    assert r.status_code == 404 and r.json()["resourceType"] == "OperationOutcome"
