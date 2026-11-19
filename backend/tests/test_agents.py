"""Agent Studio: permission-gated runs, allow-listed tools re-checked server-side, proposals need human approval,
versioned config, governance analytics. No AI key → rule-based mode (labeled)."""

from types import SimpleNamespace

import pytest

from app.agents import tools as T


def test_rule_based_run_and_permissions(as_user):
    admin, nurse = as_user("hospitaladmin@harborview.dev"), as_user("nurse.kim@harborview.dev")
    agents = {a["key"]: a for a in admin.get("/agents").json()}
    assert len(agents) == 10 and agents["doctor_assistant"]["trigger"] == "feature"
    r = admin.post("/agents/hospital_operations/run", json={"input": "What needs attention this shift?"}).json()
    assert r["mode"] == "rule_based" and r["status"] == "succeeded" and "Rule-based" in r["output"]
    assert {c["tool"] for c in r["tool_calls"]} == {"get_operations_summary", "list_open_cases"}
    assert nurse.post("/agents/hospital_operations/run", json={"input": "status"}).status_code == 400  # lacks command:view
    assert admin.post("/agents/doctor_assistant/run", json={"input": "hi"}).status_code == 400  # feature agents run in their screens


def test_tool_gate_and_proposals(as_user):
    admin = as_user("hospitaladmin@harborview.dev")

    class Ctx:  # minimal stand-in exercising the gate without a request
        def __init__(self, perms):
            self.perms = perms

        def can(self, p):
            return p in self.perms

    assert "not allowed" in T.execute(Ctx({"cases:read"}), "x", ["list_open_cases"], "get_staffing_gaps", {})["error"]
    assert "permission denied" in T.execute(Ctx(set()), "x", ["list_open_cases"], "list_open_cases", {})["error"]
    assert "invalid arguments" in T.execute(Ctx({"cases:read"}), "x", ["list_open_cases"], "list_open_cases", {"limit": 999})["error"]
    # A proposal is only an approval request; approving it (by a person) creates the task.
    r = admin.put("/agents/hospital_operations", json={"max_tool_calls": 4, "note": "tighter limit"}).json()
    assert r["version"] == 2 and admin.get("/agents/hospital_operations/versions").json()[0]["note"] == "tighter limit"
    assert as_user("nurse.kim@harborview.dev").put("/agents/hospital_operations", json={"enabled": False}).status_code == 403


def test_propose_task_executes_only_after_approval(as_user, app):
    from sqlalchemy import select

    from app.api.deps import TenantContext  # noqa: F401
    from app.core.db import SessionLocal
    from app.engine import approvals as AP
    from app.models import ApprovalRequest, Organization, User

    db = SessionLocal()
    try:
        org = db.scalar(select(Organization.id).where(Organization.slug == "harborview"))
        ctx = SimpleNamespace(db=db, org_id=org, can=lambda p: True, facility_ids=None, department_ids=None, roles=["hospital_admin"],
                              user=SimpleNamespace(id=None))
        res = T.execute(ctx, "hospital_operations", ["propose_task"], "propose_task", {"title": "Call EVS supervisor about bed turnover", "role": "bed_manager"})
        req = db.get(ApprovalRequest, __import__("uuid").UUID(res["approval_id"]))
        assert req.status == "pending" and req.requested_by_agent == "hospital_operations"
        approver = db.scalar(select(User.id).where(User.email == "bedmanager@harborview.dev"))
        AP.decide(db, req, approve=True, actor_id=approver, actor_permissions={"cases:work"})
        assert req.status == "executed" and req.result["task_id"]
        db.rollback()
    finally:
        db.close()


def test_governance(as_user):
    g = as_user("hospitaladmin@harborview.dev").get("/ai/governance").json()
    assert "agents" in g and "features" in g and g["active_provider"] == "simulated"
    assert as_user("dr.chen@harborview.dev").get("/ai/governance").status_code == 403
    _ = pytest


def test_evaluation_suites(as_user):
    admin = as_user("hospitaladmin@harborview.dev")
    r = admin.post("/ai/evaluations/document_extraction_v1")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["samples"] >= 8 and 0 <= d["score"] <= 1
    assert set(d["metrics"]["field_accuracy"]) >= {"doc_type", "date_of_birth", "member_id"}
    # Regression floor for the simulated extractor (known misses: discharge date vs admission date, card effective date read as document date,
    # correspondence typed "other"). Live providers are evaluated the same way once configured.
    if d["provider"] == "simulated":
        assert d["score"] >= 0.9 and d["metrics"]["invented_values"] <= 1
    assert all(c["correct"] <= c["total"] for c in d["cases"])
    g = admin.post("/ai/evaluations/tool_gate_v1").json()
    assert g["score"] == 1.0, g["cases"]  # every unsafe probe refused
    hist = admin.get("/ai/evaluations").json()
    assert {"document_extraction_v1", "tool_gate_v1"} <= {x["suite"] for x in hist["runs"]}
    assert admin.post("/ai/evaluations/nope").status_code == 404
    assert as_user("dr.chen@harborview.dev").post("/ai/evaluations/tool_gate_v1").status_code == 403
