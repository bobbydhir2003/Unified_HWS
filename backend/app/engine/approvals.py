"""Approval gate: proposed actions wait for a human with the required permission; executors re-check on execution.

Separation of duties: a person can't approve their own request. Agents never approve.
"""

import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.security import now
from app.engine.cases import log_event
from app.models import ApprovalRequest, Case
from app.services import audit
from app.services.realtime import publish

Executor = Callable[[Session, ApprovalRequest, uuid.UUID], dict]
EXECUTORS: dict[str, Executor] = {}


class ApprovalError(ValueError):
    pass


def executor(kind: str):
    def deco(fn: Executor) -> Executor:
        EXECUTORS[kind] = fn
        return fn

    return deco


def request_approval(db: Session, org_id: uuid.UUID, *, kind: str, title: str, payload: dict, required_permission: str,
                     summary: str | None = None, case: Case | None = None, patient_id: uuid.UUID | None = None,
                     facility_id: uuid.UUID | None = None, requested_by_user_id: uuid.UUID | None = None,
                     requested_by_agent: str | None = None, conversation_id: uuid.UUID | None = None,
                     agent_run_id: uuid.UUID | None = None, dedupe_key: str | None = None) -> ApprovalRequest:
    if kind not in EXECUTORS:
        raise ApprovalError(f"No executor registered for {kind}")
    # Facility scope: explicit, else the case's facility — approvals lists are filtered by the approver's facilities.
    req = ApprovalRequest(organization_id=org_id, kind=kind, title=title[:250], summary=summary, payload=payload,
                          required_permission=required_permission, case_id=case.id if case else None,
                          patient_id=patient_id or (case.patient_id if case else None),
                          facility_id=facility_id or (case.facility_id if case else None),
                          requested_by_user_id=requested_by_user_id, requested_by_agent=requested_by_agent,
                          conversation_id=conversation_id, agent_run_id=agent_run_id, dedupe_key=dedupe_key)
    db.add(req)
    db.flush()
    if case:
        log_event(db, case, "approval_requested", f"Approval requested: {title[:200]}", actor_id=requested_by_user_id,
                  actor_kind="agent" if requested_by_agent else None, data={"approval_id": str(req.id), "kind": kind})
    audit.record(db, "approval.requested", org_id=org_id, actor_id=requested_by_user_id, resource_type="approval",
                 resource_id=req.id, patient_id=req.patient_id, details={"kind": kind, "agent": requested_by_agent,
                                                                         "conversation_id": str(conversation_id) if conversation_id else None})
    publish(db, org_id, "approvals", approval_id=req.id)
    return req


def decide(db: Session, req: ApprovalRequest, *, approve: bool, actor_id: uuid.UUID, actor_permissions: set[str],
           note: str | None = None) -> ApprovalRequest:
    # Row lock: two approvers clicking at once can't both execute (the second sees the decided status).
    db.refresh(req, with_for_update=True)
    if req.status != "pending":
        raise ApprovalError(f"This request is already {req.status}")
    if req.required_permission not in actor_permissions:
        raise ApprovalError("You don't have permission to approve this action")
    if req.requested_by_user_id is not None and req.requested_by_user_id == actor_id:
        # Same PERSON (user id), whatever workspace/acting role they switched to — role switching can't bypass this.
        raise ApprovalError("You can't approve your own request — a different authorized person must decide")
    if not approve and not (note and note.strip()):
        raise ApprovalError("A reason is required to reject")
    req.decided_by_id, req.decided_at, req.decision_note = actor_id, now(), note
    case = db.get(Case, req.case_id) if req.case_id else None
    if not approve:
        req.status = "rejected"
    else:
        req.status = "approved"
        _run_executor(db, req, actor_id)
    _finish(db, req, actor_id, case, note)
    return req


def _run_executor(db: Session, req: ApprovalRequest, actor_id: uuid.UUID) -> None:
    sp = db.begin_nested()
    try:
        req.result = EXECUTORS[req.kind](db, req, actor_id) or {}
        req.status, req.executed_at, req.error = "executed", now(), None
        sp.commit()
    except Exception as e:  # noqa: BLE001
        sp.rollback()
        req.status, req.error = "failed", f"{type(e).__name__}: {str(e)[:400]}"


def retry(db: Session, req: ApprovalRequest, *, actor_id: uuid.UUID, actor_permissions: set[str]) -> ApprovalRequest:
    """Re-run the executor of an approved-but-failed request (same payload). Same permission + separation rules as decide."""
    db.refresh(req, with_for_update=True)
    if req.status != "failed":
        raise ApprovalError(f"Only failed actions can be retried (this one is {req.status})")
    if req.required_permission not in actor_permissions:
        raise ApprovalError("You don't have permission to retry this action")
    if req.requested_by_user_id is not None and req.requested_by_user_id == actor_id:
        raise ApprovalError("You can't retry your own request — a different authorized person must")
    _run_executor(db, req, actor_id)
    _finish(db, req, actor_id, db.get(Case, req.case_id) if req.case_id else None, "retry")
    return req


def expire_stale(db: Session, older_than) -> int:
    """Pending AGENT proposals older than `older_than` expire (status 'expired'); conversations are told."""
    from sqlalchemy import select

    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.status == "pending", ApprovalRequest.requested_by_agent.is_not(None),
                                                    ApprovalRequest.created_at < older_than).limit(500)).all()
    for r in rows:
        r.status, r.decision_note, r.decided_at = "expired", "Expired without a decision", now()
        _notify_conversation(db, r)
        publish(db, r.organization_id, "approvals", approval_id=r.id)
    return len(rows)


def _notify_conversation(db: Session, req: ApprovalRequest) -> None:
    if req.conversation_id:
        try:
            from app.services.assist import on_approval_changed

            on_approval_changed(db, req)
        except Exception:  # noqa: BLE001 — never let chat sync break the decision itself
            import logging

            logging.getLogger("undeclared.engine.approvals").exception("assist sync failed")


def _finish(db: Session, req: ApprovalRequest, actor_id: uuid.UUID, case: Case | None, note: str | None) -> None:
    if case:
        log_event(db, case, "approval", f"{req.title[:150]}: {req.status}" + (f" — {note}" if note else ""), actor_id=actor_id,
                  data={"approval_id": str(req.id), "status": req.status})
    audit.record(db, f"approval.{req.status}", org_id=req.organization_id, actor_id=actor_id, resource_type="approval",
                 resource_id=req.id, patient_id=req.patient_id, details={"kind": req.kind, "error": req.error})
    _notify_conversation(db, req)
    publish(db, req.organization_id, "approvals", approval_id=req.id)
