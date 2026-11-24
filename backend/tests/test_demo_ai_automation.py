"""Phase 5 inside private demo hospitals: the 22 monitors run per hospital (and never touch another), the 10 assistants
open and run on the hospital's own records, scribe / document intelligence / voice tools work with clear simulation
labels, and files are removed with the hospital. No OpenAI call is made in this file (AI is the labelled simulation)."""
from pathlib import Path

from conftest import Visitor
from sqlalchemy import func, select

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Case, DemoSandbox, Document


def _open_cases(org) -> int:
    db = SessionLocal()
    try:
        return db.scalar(select(func.count()).select_from(Case).where(Case.organization_id == org,
                                                                      Case.status.in_(("open", "in_progress", "waiting", "escalated"))))
    finally:
        db.close()


def test_all_22_monitors_run_per_hospital_without_duplicates_or_leaks(app, demo):
    a = Visitor(app, "192.0.2.10").enter("super_admin")
    b = Visitor(app, "192.0.2.11").enter("super_admin")
    mons = [m for m in a.get("/monitors").json() if not m["key"].startswith("test.")]  # other tests register a dummy monitor
    assert len(mons) == 22
    b_before = _open_cases(b.org)
    for m in mons:
        r = a.post(f"/monitors/{m['key']}/run")
        assert r.status_code == 200, (m["key"], r.text)
    first = _open_cases(a.org)
    for m in mons:  # re-running finds the same problems: no duplicate cases
        a.post(f"/monitors/{m['key']}/run")
    assert _open_cases(a.org) == first
    assert _open_cases(b.org) == b_before  # another visitor's hospital is unaffected
    # Outputs appear where intended: Command Center and My work.
    assert a.get("/command/summary").status_code == 200
    a.switch(key="pharmacist")
    assert any(c["category"] in ("pharmacy", "inventory") for c in a.get("/worklist").json()["cases"])


def test_all_ten_assistants_open_and_run_on_the_hospitals_own_records(app, demo):
    v = Visitor(app, "192.0.2.20").enter("super_admin")
    agents = v.get("/agents").json()
    keys = {a["key"] for a in agents}
    assert keys == {"insurance_guardian", "doctor_assistant", "medical_scribe", "document_intelligence", "pharmacy_watchdog",
                    "discharge_coordination", "hospital_operations", "claims_review", "patient_communication", "staff_scheduling"}
    db = SessionLocal()
    own = {str(c) for c in db.scalars(select(Case.id).where(Case.organization_id == v.org))}
    db.close()
    for key in sorted(keys):
        r = v.post(f"/agents/{key}/run", json={"input": "What needs attention today?"})
        assert r.status_code in (200, 400), (key, r.text)
        if r.status_code != 200:
            continue  # e.g. assistants that only run inside their workflow (scribe on a visit, documents on a file)
        run = r.json()
        assert run["mode"] == "rule_based" and run["ai_source"] == "rules" and run["status"] in ("succeeded", "blocked")
        assert "Rule-based" in (run["output"] or "") or run["status"] == "blocked"
        for call in run["tool_calls"] or []:   # every case a tool returned belongs to this hospital
            for item in (call.get("result") or {}).get("cases", []) if isinstance(call.get("result"), dict) else []:
                assert str(item.get("id")) in own, (key, item)
    # Agent configuration saved by this visitor applies to this visitor only.
    assert v.put("/agents/hospital_operations", json={"max_tool_calls": 3}).status_code == 200
    w = Visitor(app, "192.0.2.21").enter("super_admin")
    mine = next(a for a in v.get("/agents").json() if a["key"] == "hospital_operations")
    theirs = next(a for a in w.get("/agents").json() if a["key"] == "hospital_operations")
    assert mine["max_tool_calls"] == 3 and theirs["max_tool_calls"] != 3


def test_scribe_documents_and_voice_tools_in_a_hospital(app, demo):
    v = Visitor(app, "192.0.2.30").enter("doctor")
    pid = v.get("/patients", params={"limit": 5}).json()["items"][0]["id"]
    enc = v.post("/encounters", json={"patient_id": pid}).json()
    s = v.post(f"/encounters/{enc['id']}/scribe", json={"consent_method": "verbal", "consent_confirmed": True}).json()
    v.post(f"/scribe/{s['id']}/demo")
    s = v.get(f"/encounters/{enc['id']}/scribe").json()
    assert s["status"] == "ready" and s["draft"]["provider"] == "simulated"       # labelled simulation, never auto-signed
    d = v.post("/documents/samples", json={"kind": "lab_result", "fidelity": "exact", "patient_id": pid})
    assert d.status_code == 201, d.text
    d = d.json()
    assert d["status"] == "needs_review" and d["ai_provider"] == "simulated" and d["patient_id"] is None  # never auto-filed
    v.switch(key="front_desk")
    info = v.post("/ai/realtime/tools/get_clinic_information", json={}).json()
    assert info["facilities"]
    r = v.post("/ai/realtime/tools/request_staff_callback", json={"topic": "Reschedule", "caller_first_name": "Ana"})
    assert r.status_code == 200 and "Nothing has been booked" in r.json()["message"]
    # Files are stored under the hospital and removed with it.
    db = SessionLocal()
    key = db.scalar(select(Document.storage_key).where(Document.id == d["id"]))
    sb_id = db.scalar(select(DemoSandbox.id).where(DemoSandbox.organization_id == v.org))
    db.close()
    path = Path(settings.storage_local_path).resolve() / key
    assert path.exists()
    from app.demo import sandbox

    db = SessionLocal()
    sandbox.release(db, db.get(DemoSandbox, sb_id), "test")
    db.commit()
    db.close()
    assert sandbox.purge(sb_id) and not path.exists()
