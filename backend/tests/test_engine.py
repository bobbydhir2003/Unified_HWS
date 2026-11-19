"""Automation engine invariants: durable outbox, exactly-once effects, dedupe, verification, escalation, approvals."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.security import now
from app.engine import approvals as A
from app.engine import cases as C
from app.engine.events import dispatch_pending, emit, handler
from app.engine.monitors import REGISTRY, Monitor, register, run_monitor
from app.engine.notifications import deliver
from app.models import Case, CaseEvent, EventHandling, NotificationDelivery, Organization, User

CALLS: list[str] = []
FLAKY = {"fail_next": 0}


@handler("test_counter", "test.ping")
def _counter(db, ev):
    if FLAKY["fail_next"] > 0:
        FLAKY["fail_next"] -= 1
        raise RuntimeError("transient failure")
    CALLS.append(str(ev.id))


FINDINGS: list[C.Finding] = []


class DummyMonitor(Monitor):
    key = "test.dummy"
    name = "Test monitor"
    category = "operations"

    def evaluate(self, db, org_id, cfg):
        return list(FINDINGS)


register(DummyMonitor())


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def _org(db):
    return db.scalar(select(Organization.id).where(Organization.slug == "harborview"))


def test_outbox_is_transactional_retried_and_exactly_once(db):
    org = _org(db)
    CALLS.clear()
    # Rolled-back business change → no event.
    emit(db, org, "test.ping", {"n": 0})
    db.rollback()
    assert not CALLS
    # Committed change with a transient handler failure → retried later, effect applied exactly once.
    FLAKY["fail_next"] = 1
    ev = emit(db, org, "test.ping", {"n": 1})
    db.commit()  # after-commit kick dispatches inline (eager mode); first attempt fails
    db.refresh(ev)
    assert ev.status == "pending" and ev.attempts == 1 and not CALLS
    ev.next_attempt_at = now()
    db.commit()
    dispatch_pending()
    db.refresh(ev)
    assert ev.status == "done" and CALLS == [str(ev.id)]
    # Redelivery (e.g. worker crash after commit, manual replay) never repeats the effect.
    ev.status = "pending"
    db.commit()
    dispatch_pending()
    assert CALLS == [str(ev.id)]
    assert db.scalar(select(func.count()).select_from(EventHandling).where(EventHandling.event_id == ev.id,
                                                                           EventHandling.handler == "test_counter")) == 1


def test_monitor_dedupes_and_verifies_resolution(db):
    org = _org(db)
    key = f"test:{uuid.uuid4()}"
    FINDINGS[:] = [C.Finding(dedupe_key=key, title="Synthetic problem", category="operations", kind="test.dummy",
                             severity="medium", assign_role="clinic_admin")]
    r1 = run_monitor(db, org, "test.dummy")
    r2 = run_monitor(db, org, "test.dummy")
    db.commit()
    assert (r1.opened, r2.opened) == (1, 0)
    assert db.scalar(select(func.count()).select_from(Case).where(Case.dedupe_key == key)) == 1
    # Severity worsens → same case, severity raised.
    FINDINGS[0].severity = "high"
    run_monitor(db, org, "test.dummy")
    case = db.scalar(select(Case).where(Case.dedupe_key == key))
    assert case.severity == "high"
    # Condition clears → monitor verifies and resolves the case automatically.
    FINDINGS.clear()
    r = run_monitor(db, org, "test.dummy")
    db.commit()
    db.refresh(case)
    assert r.closed >= 1 and case.status == "resolved" and case.resolution_code == "condition_cleared"
    kinds = [e.kind for e in db.scalars(select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.at))]
    assert kinds[0] == "created" and "severity" in kinds and kinds[-1] == "resolved"
    # The same problem recurring later opens a fresh case (the old one stays resolved).
    FINDINGS[:] = [C.Finding(dedupe_key=key, title="Synthetic problem", category="operations", kind="test.dummy")]
    assert run_monitor(db, org, "test.dummy").opened == 1
    FINDINGS.clear()
    run_monitor(db, org, "test.dummy")
    db.commit()


def test_notification_steps_deliver_once(db):
    org = _org(db)
    admin = db.scalar(select(User.id).where(User.email == "clinicadmin@harborview.dev"))
    k = f"test:notify:{uuid.uuid4()}"
    d1 = deliver(db, org, channel="in_app", dedupe=k, subject="Hello", body="x", user_id=admin)
    d2 = deliver(db, org, channel="in_app", dedupe=k, subject="Hello", body="x", user_id=admin)
    db.commit()
    assert d1 is not None and d1.status == "sent" and d2 is None
    assert db.scalar(select(func.count()).select_from(NotificationDelivery).where(NotificationDelivery.dedupe_key == k)) == 1


def test_escalation_fires_once_per_level(db):
    org = _org(db)
    c, _ = C.open_case(db, org, C.Finding(dedupe_key=f"test:esc:{uuid.uuid4()}", title="Overdue thing", category="operations",
                                          kind="test.esc", severity="high", assign_role="nurse"))
    c.due_at = now() - timedelta(minutes=1)
    db.commit()
    C.escalate_due(db)
    C.escalate_due(db)  # second sweep: no double escalation
    db.commit()
    db.refresh(c)
    assert c.escalation_level == 1 and c.status == "escalated" and c.assigned_role == "clinic_admin"
    esc_events = db.scalar(select(func.count()).select_from(CaseEvent).where(CaseEvent.case_id == c.id, CaseEvent.kind == "escalated"))
    assert esc_events == 1
    C.resolve(db, c, "done in test")
    db.commit()


def test_approval_separation_of_duties(db):
    org = _org(db)
    nurse = db.scalar(select(User.id).where(User.email == "nurse.rivera@harborview.dev"))
    doctor = db.scalar(select(User.id).where(User.email == "dr.chen@harborview.dev"))
    hits = []

    @A.executor("test.action")
    def _exec(db_, req, actor):
        hits.append(actor)
        return {"ok": True}

    req = A.request_approval(db, org, kind="test.action", title="Do thing", payload={}, required_permission="clinical:sign",
                             requested_by_user_id=nurse)
    with pytest.raises(A.ApprovalError):  # requester lacks permission
        A.decide(db, req, approve=True, actor_id=nurse, actor_permissions={"clinical:write"})
    with pytest.raises(A.ApprovalError):  # can't approve own request even with permission
        A.decide(db, req, approve=True, actor_id=nurse, actor_permissions={"clinical:sign"})
    A.decide(db, req, approve=True, actor_id=doctor, actor_permissions={"clinical:sign"})
    assert req.status == "executed" and hits == [doctor]
    with pytest.raises(A.ApprovalError):  # no double execution
        A.decide(db, req, approve=True, actor_id=doctor, actor_permissions={"clinical:sign"})
    db.commit()


def test_case_api_requires_snooze_reason_and_scopes(as_user):
    admin = as_user("clinicadmin@harborview.dev")
    c = admin.post("/cases", json={"title": "Broken wheelchair in lobby", "category": "equipment", "severity": "low"})
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    assert admin.post(f"/cases/{cid}/snooze", json={"hours": 2, "reason": "no"}).status_code == 422
    assert admin.post(f"/cases/{cid}/snooze", json={"hours": 2, "reason": "Waiting for vendor visit"}).json()["status"] == "snoozed"
    assert admin.post(f"/cases/{cid}/transition", json={"to": "resolved"}).status_code == 400  # note required
    r = admin.post(f"/cases/{cid}/transition", json={"to": "resolved", "note": "Vendor replaced wheel"})
    assert r.json()["status"] == "resolved"
    detail = admin.get(f"/cases/{cid}").json()
    assert [e["kind"] for e in detail["events"]] == ["created", "status", "resolved"]
    # Patients and other organizations can't see cases.
    assert as_user("patient@harborview.dev").get(f"/cases/{cid}").status_code == 403
    assert as_user("dr.lake@lakeside.dev", "lakeside").get(f"/cases/{cid}").status_code == 404
    assert REGISTRY  # registry populated
