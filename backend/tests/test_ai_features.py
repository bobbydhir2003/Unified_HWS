"""Phase 10: chart assistant, automation studio, tasks, AI receptionist, AI monitoring."""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DOCTOR, NURSE, FRONT, ADMIN, PATIENT = ("dr.chen@harborview.dev", "nurse.rivera@harborview.dev", "frontdesk@harborview.dev",
                                        "clinicadmin@harborview.dev", "patient@harborview.dev")


def _pid(api, q="Elena Moreau"):
    return api.get("/patients", params={"q": q}).json()["items"][0]["id"]


# ---------- chart assistant ----------

def test_assistant_answers_with_citations_and_refuses_decisions(as_user):
    doc = as_user(DOCTOR)
    pid = _pid(doc)
    doc.post(f"/patients/{pid}/allergies", json={"substance": "Latex", "severity": "mild", "reaction": "Rash"})
    a = doc.post(f"/patients/{pid}/assistant", json={"question": "What allergies does this patient have?"}).json()
    assert not a["refused"] and a["citations"] and all(c["type"] == "allergy" for c in a["citations"])
    assert "Latex" in a["answer"] and "[S" in a["answer"]
    r = doc.post(f"/patients/{pid}/assistant", json={"question": "Should I prescribe amoxicillin 500 mg?"}).json()
    assert r["refused"] is True and r["citations"] == []
    s = doc.post(f"/patients/{pid}/assistant", json={"question": "Summarize this patient's history"}).json()
    assert "Active medications" in s["answer"] and len(s["citations"]) >= 2
    u = doc.post(f"/patients/{pid}/assistant", json={"question": "colonoscopy polyp pathology"}).json()
    assert u["insufficient"] is True and "couldn't find" in u["answer"]
    audit = as_user(ADMIN).get("/audit", params={"action": "ai.chart_assistant"}).json()["items"][0]
    assert "question" not in audit["details"]  # no free-text (possible PHI) in the audit log


def test_assistant_respects_roles_and_tenancy(as_user):
    pid = _pid(as_user(DOCTOR))
    assert as_user(FRONT).post(f"/patients/{pid}/assistant", json={"question": "allergies?"}).status_code == 403
    assert as_user("dr.lake@lakeside.dev", "lakeside").post(f"/patients/{pid}/assistant", json={"question": "allergies?"}).status_code == 404


# ---------- automation ----------

def _open_tasks(api, scope="mine"):
    return api.get("/tasks", params={"scope": scope}).json()


def test_message_triage_routes_urgent_and_refill(as_user):
    pat, doc, nurse = as_user(PATIENT), as_user(DOCTOR), as_user(NURSE)
    tag = uuid.uuid4().hex[:6]
    pat.post("/portal/messages", json={"subject": f"Feeling unwell {tag}", "body": "I have chest pain since this morning"})
    pat.post("/portal/messages", json={"subject": f"Refill {tag}", "category": "medication", "body": "I ran out of my inhaler, need a refill"})
    doc_tasks = _open_tasks(doc)
    assert any(t["priority"] == "urgent" and "URGENT" in t["title"] for t in doc_tasks)
    assert any("URGENT patient message" in n["title"] for n in doc.get("/notifications").json()["items"])
    nurse_task = next(t for t in _open_tasks(nurse) if "medication" in t["title"])
    done = nurse.post(f"/tasks/{nurse_task['id']}/complete").json()
    assert done["status"] == "done"


def test_no_show_outreach_requires_approval_before_messaging_patient(as_user):
    front, pat, admin = as_user(FRONT), as_user(PATIENT), as_user(ADMIN)
    pid = pat.membership["patient_id"]
    clinic = next(c for c in front.membership["clinics"] if c["code"] == "HDT")
    prov = front.get("/providers").json()[0]
    start = datetime.now(ZoneInfo("America/New_York")).replace(microsecond=0, second=0) + timedelta(days=60, minutes=7)
    for _ in range(20):
        r = front.post("/appointments", json={"patient_id": pid, "provider_id": prov["id"], "clinic_id": clinic["id"], "start_at": start.isoformat(),
                                              "end_at": (start + timedelta(minutes=5)).isoformat(), "override_availability": True})
        if r.status_code == 201:
            break
        start += timedelta(minutes=13)
    appt = r.json()
    before = len(pat.get("/portal/messages").json())
    front.post(f"/appointments/{appt['id']}/status", json={"action": "no_show"})
    pending = [x for x in front.get("/automation/runs", params={"status": "pending_approval"}).json() if x["workflow"] == "No-show outreach"]
    assert pending and pending[0]["sensitive"] is True
    assert len(pat.get("/portal/messages").json()) == before  # nothing sent before approval
    ok = front.post(f"/automation/runs/{pending[0]['id']}/approve").json()
    assert ok["status"] == "succeeded"
    assert len(pat.get("/portal/messages").json()) == before + 1
    assert front.post(f"/automation/runs/{pending[0]['id']}/approve").status_code == 400
    assert any("Reschedule no-show" in t["title"] for t in _open_tasks(front))
    assert admin.get("/automation/workflows").status_code == 200
    assert front.get("/automation/workflows").status_code == 403  # configuring automations needs automation:manage


def test_disabled_workflow_does_not_run_and_document_routing(as_user):
    admin, front, nurse = as_user(ADMIN), as_user(FRONT), as_user(NURSE)
    wfs = {w["template_key"]: w for w in admin.get("/automation/workflows").json()}
    admin.patch(f"/automation/workflows/{wfs['document_routing']['id']}", json={"is_enabled": False})
    d1 = front.post("/documents/samples", json={"kind": "lab_result"}).json()
    assert not any(d1["id"] in (t["link"] or "") for t in _open_tasks(nurse))
    admin.patch(f"/automation/workflows/{wfs['document_routing']['id']}", json={"is_enabled": True})
    d2 = front.post("/documents/samples", json={"kind": "lab_result"}).json()
    assert any(d2["id"] in (t["link"] or "") for t in _open_tasks(nurse))


# ---------- receptionist: replaced by HMS Voice Concierge (tests/test_voice_concierge.py) ----------


def test_ai_monitoring_lists_jobs(as_user):
    data = as_user(ADMIN).get("/ai/jobs").json()
    assert data["provider"] == "simulated" and data["phi_sent_externally_total"] == 0
    assert "chart_qa" in data["summary"] and "document_analysis" in data["summary"]
    assert as_user(DOCTOR).get("/ai/jobs").status_code == 403
