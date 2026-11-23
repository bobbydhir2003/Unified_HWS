"""Case story: the automation lifecycle of one case built ONLY from recorded events and rows (never inferred or invented).

Detected → AI assisted → Action proposed → Waiting for approval → Action executed → Resolution verified.
Each step is done (with its real timestamp), current, pending, skipped (with the recorded reason) or not_used.
"""

from __future__ import annotations

from app.models import ApprovalRequest, Case, CaseEvent

STEPS = [("detected", "Detected"), ("ai_assisted", "AI assisted"), ("proposed", "Action proposed"),
         ("approval", "Waiting for approval"), ("executed", "Action executed"), ("verified", "Resolution verified")]


def build(case: Case, events: list[CaseEvent], approvals: list[ApprovalRequest]) -> list[dict]:
    first = {}
    for e in events:  # events arrive oldest first
        first.setdefault(e.kind, e)
    s: dict[str, dict] = {k: {"key": k, "label": label, "status": "pending", "at": None, "detail": None} for k, label in STEPS}

    s["detected"].update(status="done", at=case.first_detected_at or case.created_at,
                         detail=f"{'Monitor' if case.source == 'monitor' else 'Reported'}: {case.kind.replace('_', ' ')}")
    if (e := first.get("ai_assist")):
        s["ai_assisted"].update(status="done", at=e.at, detail=e.message)
    elif (e := first.get("ai_unavailable")):
        s["ai_assisted"].update(status="skipped", at=e.at, detail=e.message)
    else:
        s["ai_assisted"].update(status="not_used", detail="No AI assistance for this case.")

    proposals = sorted(approvals, key=lambda a: a.created_at)
    pr_event = first.get("purchase_request")
    if proposals or pr_event:
        at = min([a.created_at for a in proposals] + ([pr_event.at] if pr_event else []))
        what = proposals[0].title if proposals else pr_event.message
        s["proposed"].update(status="done", at=at, detail=what)
        pending = [a for a in proposals if a.status == "pending"]
        decided = [a for a in proposals if a.decided_at]
        pr_decided = first.get("purchase_request_decided")
        if pending:
            s["approval"].update(status="current", detail=f"{len(pending)} waiting for an authorized person")
        elif decided or pr_decided:
            at2 = min([a.decided_at for a in decided] + ([pr_decided.at] if pr_decided else []))
            rejected = all(a.status == "rejected" for a in decided) and not pr_decided
            s["approval"].update(status="done", at=at2, label="Rejected" if rejected else "Approved",
                                 detail=(decided[0].decision_note if decided and decided[0].decision_note else None))
        elif pr_event:
            s["approval"].update(status="current", detail="Purchase request waiting for approval")
        executed = [a for a in proposals if a.status == "executed"]
        failed = [a for a in proposals if a.status == "failed"]
        if executed:
            s["executed"].update(status="done", at=min(a.executed_at for a in executed), detail=executed[0].title)
        elif pr_decided and "approved" in pr_decided.message.lower():
            s["executed"].update(status="done", at=pr_decided.at, detail=pr_decided.message)
        elif failed:
            s["executed"].update(status="failed", detail=failed[0].error)
    else:
        for k in ("proposed", "approval", "executed"):
            s[k]["status"] = "not_used"
        s["proposed"]["detail"] = "Handled through tasks and notifications (no approval needed)."

    if case.status == "resolved" and case.resolved_at:
        auto = case.resolution_code in ("verified_active", "condition_cleared")
        s["verified"].update(status="done", at=case.resolved_at, label="Resolution verified" if auto else "Resolved",
                             detail=case.resolution or case.resolution_code)
    elif case.status == "cancelled":
        s["verified"].update(status="skipped", detail="Case cancelled")
    # The first not-yet-done step in a live case is "current".
    if case.status not in ("resolved", "cancelled") and not any(v["status"] == "current" for v in s.values()):
        nxt = next((v for v in s.values() if v["status"] == "pending"), None)
        if nxt:
            nxt["status"] = "current"
    return list(s.values())


def stage(case: Case, pending_approval: bool, executed: bool) -> str:
    """One-word stage for case lists (cheap: no event scan)."""
    if case.status == "resolved":
        return "verified"
    if pending_approval:
        return "waiting_approval"
    if executed:
        return "executed"
    a = (case.data or {}).get("ai_assist") or {}
    if a.get("status") in ("proposed", "no_action"):
        return "ai_assisted"
    return "detected"
