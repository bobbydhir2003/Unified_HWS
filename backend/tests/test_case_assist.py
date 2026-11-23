"""AI case assistance (Phase 3): detect → AI assists → proposal → human approval → existing executor → monitor verifies.
OpenAI is MOCKED here (structured call replaced); live behaviour is verified separately and reported as such."""
import uuid

import pytest
from sqlalchemy import select

from app.agents import case_assist as CA
from app.ai.config import EffectiveAI
from app.core.db import SessionLocal
from app.engine.cases import Finding, open_case
from app.models import AgentRun, ApprovalRequest, Case, CaseEvent, Organization, Patient, PurchaseRequest


def _org(db):
    return db.scalar(select(Organization.id).where(Organization.slug == "harborview"))


FAKE = EffectiveAI(provider="openai", api_key="sk-test-not-real", text_model="gpt-4.1-mini", source="ui")


class _Meta:
    input_tokens, output_tokens, cost_usd, model = 120, 40, 0.0001, "gpt-4.1-mini"


@pytest.fixture(autouse=True)
def _cleanup():
    """Cancel the cases these tests open so monitors and dashboard counts in other tests are unaffected."""
    yield
    from sqlalchemy import update

    db = SessionLocal()
    db.execute(update(Case).where(Case.dedupe_key.like("test.%"), Case.status != "cancelled").values(status="cancelled"))
    db.execute(update(PurchaseRequest).where(PurchaseRequest.case_id.in_(select(Case.id).where(Case.dedupe_key.like("test.%")))).values(status="cancelled"))
    db.commit()
    db.close()


@pytest.fixture
def ai(monkeypatch):
    """Platform provider present; the structured call returns whatever the test sets."""
    box = {"out": None, "calls": 0}
    monkeypatch.setattr(CA, "_provider", lambda db, org, agent: (FAKE, None, None))

    def structured(self, **kw):
        box["calls"] += 1
        assert "<case>" in kw["content"][0]["text"] and kw["schema"] is CA.Suggestion
        return box["out"], _Meta()

    from app.ai import openai_provider

    monkeypatch.setattr(openai_provider.OpenAICore, "structured", structured)
    return box


def _low_stock_case(db, qty=100):
    org = _org(db)
    from app.models import Clinic, InventoryItem

    it = db.scalar(select(InventoryItem).where(InventoryItem.organization_id == org).limit(1))
    fac = db.scalar(select(Clinic.id).where(Clinic.organization_id == org, Clinic.facility_type == "hospital").limit(1))
    case, _ = open_case(db, org, Finding(dedupe_key=f"test.low:{uuid.uuid4()}", title=f"Low stock: {it.name}", category="pharmacy",
                                         kind="inventory.low_stock", facility_id=fac, assign_role="pharmacist",
                                         evidence={"recommended_qty": qty, "item": it.name}, data={"item_id": str(it.id)}),
                        rule_key="inventory.low_stock")
    pr = PurchaseRequest(organization_id=org, facility_id=fac, item_id=it.id, quantity=qty, status="submitted", source="watchdog", case_id=case.id)
    db.add(pr)
    db.commit()
    return case.id, pr.id


def test_low_stock_proposal_approval_executes_existing_backend(ai, as_user):
    db = SessionLocal()
    cid, prid = _low_stock_case(db)
    assert CA._claim(db, cid, "case_open") and not CA._claim(db, cid, "case_open")  # idempotent per trigger
    db.commit()
    ai["out"] = CA.Suggestion(summary="C? usage spiked; order more.", action="adjust_purchase_request", reason="28-day use rose 40%", quantity=150)
    run = CA.assist(db, cid, "case_open")
    assert run.status == "succeeded" and run.trigger == "case_open" and run.ai_source == "platform" and len(run.approvals) == 1
    req = db.get(ApprovalRequest, uuid.UUID(run.approvals[0]))
    assert req.status == "pending" and req.case_id == cid and req.requested_by_agent == "pharmacy_watchdog"
    assert db.get(PurchaseRequest, prid).quantity == 100  # nothing changes before a human approves
    kinds = [e.kind for e in db.scalars(select(CaseEvent).where(CaseEvent.case_id == cid))]
    assert "ai_assist" in kinds and "approval_requested" in kinds
    rx = as_user("pharmacist@harborview.dev")  # lacks procurement:approve
    assert rx.post(f"/approvals/{req.id}/decide", json={"approve": True}).status_code in (400, 403)
    admin = as_user("hospitaladmin@harborview.dev")
    r = admin.post(f"/approvals/{req.id}/decide", json={"approve": True})
    assert r.status_code == 200 and r.json()["status"] == "executed", r.text
    db.expire_all()
    assert db.get(PurchaseRequest, prid).quantity == 150 and db.get(PurchaseRequest, prid).status == "submitted"  # purchase still needs its own approval
    db.close()


def test_out_of_bounds_proposal_is_rejected_and_logged(ai):
    db = SessionLocal()
    cid, prid = _low_stock_case(db)
    ai["out"] = CA.Suggestion(summary="Order a lot.", action="adjust_purchase_request", reason="x", quantity=5000)
    run = CA.assist(db, cid, "case_open")
    assert run.status == "failed" and not run.approvals and db.get(PurchaseRequest, prid).quantity == 100
    ev = db.scalars(select(CaseEvent).where(CaseEvent.case_id == cid, CaseEvent.kind == "ai_unavailable")).all()
    assert ev and "standard workflow continues" in ev[0].message
    db.close()


def test_disallowed_action_for_case_kind(ai):
    db = SessionLocal()
    cid, _ = _low_stock_case(db)
    ai["out"] = CA.Suggestion(summary="Message the patient.", action="patient_message", reason="x", message_subject="Hi", message_body="Hello there")
    assert CA.assist(db, cid, "case_open").status == "failed"
    assert not db.scalars(select(ApprovalRequest).where(ApprovalRequest.case_id == cid)).all()
    db.close()


def test_no_provider_is_labelled_and_workflow_continues(monkeypatch):
    monkeypatch.setattr(CA, "_provider", lambda db, org, agent: (None, None, "AI is turned off by the platform owner"))
    db = SessionLocal()
    cid, prid = _low_stock_case(db)
    run = CA.assist(db, cid, "case_open")
    assert run.mode == "rule_based" and run.status == "blocked" and run.ai_source == "rules"
    case = db.get(Case, cid)
    assert case.data["ai_assist"]["status"] == "unavailable" and case.status == "open"
    assert db.get(PurchaseRequest, prid).status == "submitted"  # deterministic purchase request untouched
    db.close()


def test_insurance_message_proposal_respects_preferences(ai, as_user):
    db = SessionLocal()
    org = _org(db)
    p = db.scalar(select(Patient).where(Patient.organization_id == org, Patient.portal_user_id.is_not(None)).limit(1))
    case, _ = open_case(db, org, Finding(dedupe_key=f"test.ins:{uuid.uuid4()}", title="Coverage unverified", category="insurance",
                                         kind="insurance.visit_readiness", patient_id=p.id, assign_role="insurance_specialist",
                                         evidence={"state": "unverified"}), rule_key="insurance.visit_readiness")
    db.commit()
    ai["out"] = CA.Suggestion(summary="Ask the patient to upload their card.", action="patient_message", reason="no response",
                              message_subject="Please confirm your insurance", message_body="Please upload your current insurance card in the portal before your visit.")
    run = CA.assist(db, case.id, "case_open")
    req = db.get(ApprovalRequest, uuid.UUID(run.approvals[0]))
    assert req.kind == "agent.patient_message" and req.patient_id == p.id
    r = as_user("insurance@harborview.dev").post(f"/approvals/{req.id}/decide", json={"approve": True})
    assert r.status_code == 200 and r.json()["status"] == "executed", r.text
    assert r.json()["result"]["notification"] in ("sent", "suppressed")
    db.close()


def test_sweep_selects_only_configured_kinds_once(ai, monkeypatch):
    queued = []
    monkeypatch.setattr(CA, "_enqueue", lambda cid, trig: queued.append((cid, trig)))
    db = SessionLocal()
    cid, _ = _low_stock_case(db)
    org = _org(db)
    other, _ = open_case(db, org, Finding(dedupe_key=f"test.lab:{uuid.uuid4()}", title="Lab TAT", category="lab", kind="lab.turnaround"),
                         rule_key="lab.turnaround")
    db.commit()
    CA.sweep(db, [org])
    ids = [c for c, _ in queued]
    assert other.id not in ids
    queued.clear()
    CA.sweep(db, [org])
    assert cid not in [c for c, _ in queued]  # never twice for the same trigger
    db.close()


def test_runs_are_recorded_for_governance(ai):
    db = SessionLocal()
    n = db.scalar(select(AgentRun.id).where(AgentRun.trigger == "case_open").limit(1))
    assert n is not None
    db.close()


def test_case_story_shows_only_real_steps(ai, as_user):
    db = SessionLocal()
    cid, _ = _low_stock_case(db)
    rx, admin = as_user("pharmacist@harborview.dev"), as_user("hospitaladmin@harborview.dev")
    story = {s["key"]: s for s in rx.get(f"/cases/{cid}").json()["story"]}
    assert story["detected"]["status"] == "done" and story["ai_assisted"]["status"] in ("current", "pending", "not_used")
    assert story["executed"]["status"] != "done" and story["verified"]["status"] != "done"  # nothing marked complete early
    ai["out"] = CA.Suggestion(summary="Raise quantity.", action="adjust_purchase_request", reason="usage up", quantity=120)
    run = CA.assist(db, cid, "case_open")
    story = {s["key"]: s for s in rx.get(f"/cases/{cid}").json()["story"]}
    assert story["ai_assisted"]["status"] == "done" and story["proposed"]["status"] == "done" and story["approval"]["status"] == "current"
    admin.post(f"/approvals/{run.approvals[0]}/decide", json={"approve": True})
    story = {s["key"]: s for s in rx.get(f"/cases/{cid}").json()["story"]}
    assert story["approval"]["status"] == "done" and story["executed"]["status"] == "done" and story["executed"]["at"]
    assert story["verified"]["status"] != "done"  # only the monitor's verification closes it
    row = next(c for c in rx.get("/cases", params={"category": "pharmacy"}).json() if c["id"] == str(cid))
    assert row["stage"] == "executed"
    wl = admin.get("/worklist").json()
    assert any(o["type"] == "purchase_request" for o in wl["other_approvals"])
    db.close()
