"""AI assistance for automation cases: detect → AI assists → action proposed → human approves → backend executes → monitor verifies.

* Selective: only the case kinds in RULES, once per case per trigger (case opened, or escalated) — never on every monitor
  cycle or routine update. Per-organization daily cap (AI_AUTO_ASSIST_DAILY_LIMIT, durable counter).
* Bounded: the model sees the case (title, summary, evidence, recent timeline) and returns a typed choice from that case
  kind's action allow-list. The server validates the choice and creates an ApprovalRequest handled by an existing executor.
  The AI never executes anything, never writes clinical data, never prescribes, dispenses, codes or submits claims.
* Honest: every attempt is an AgentRun (trigger, provider source, tokens, estimated cost) and a case event. If AI is off,
  over a limit, blocked by policy or failing, the case gets a plain "AI assistance unavailable" event and the deterministic
  workflow (tasks, reminders, purchase requests, verification) continues unchanged.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import P
from app.core.security import now
from app.models import AgentRun, Case, CaseEvent
from app.models.engine import CASE_OPEN

log = logging.getLogger("undeclared.agents.case_assist")

ActionName = Literal["none", "create_task", "patient_message", "adjust_purchase_request", "request_insurance_update"]

# rule_key → which assistant helps, when, and the ONLY actions it may propose (plus which roles a task may go to).
RULES: dict[str, dict] = {
    "inventory.low_stock": {"agent": "pharmacy_watchdog", "trigger": "case_open", "actions": ["create_task", "adjust_purchase_request"],
                            "roles": ["pharmacist", "hospital_admin"],
                            "brief": "Low stock. A purchase request may already exist (never create another). You may propose adjusting "
                                     "its quantity within 50-200% of the recommendation, or a staff task. Never prescribe or dispense."},
    "pharmacy.expiring": {"agent": "pharmacy_watchdog", "trigger": "case_open", "actions": ["create_task"],
                          "roles": ["pharmacist"],
                          "brief": "Expiring stock. Suggest a concrete use-first/transfer/waste task. Waste needs a second pharmacist."},
    "insurance.visit_readiness": {"agent": "insurance_guardian", "trigger": "case_open",
                                  "actions": ["create_task", "patient_message", "request_insurance_update"],
                                  "roles": ["insurance_specialist", "receptionist"],
                                  "brief": "Coverage not ready before a visit. Payer checks here are SIMULATED — never claim a payer "
                                           "confirmed anything. A patient message must be administrative only."},
    "discharge.not_departed": {"agent": "discharge_coordination", "trigger": "case_open", "actions": ["create_task"],
                               "roles": ["nurse", "bed_manager"],
                               "brief": "Discharge ordered but patient has not left. Suggest a coordination task for the blocking item. "
                                        "The responsible clinician keeps discharge authority — never decide clinical readiness."},
    "billing.claims_on_hold": {"agent": "claims_review", "trigger": "case_open", "actions": ["create_task"],
                               "roles": ["billing"],
                               "brief": "Claim on hold. Suggest a review task for the billing team. Never invent codes, never edit or "
                                        "submit claims."},
    "staffing.coverage_gap": {"agent": "staff_scheduling", "trigger": "case_escalation", "actions": ["create_task"],
                              "roles": ["hospital_admin", "clinic_admin"],
                              "brief": "Escalated staffing gap. Suggest a task for a manager to review options. Never change "
                                       "assignments — managers decide."},
}
# Monitors integrated later (Phase 6). Available per monitor but OFF until an administrator enables them.
RULES.update({
    "pharmacy.unusual_usage": {"agent": "pharmacy_watchdog", "trigger": "case_open", "actions": ["create_task"], "roles": ["pharmacist"],
                               "default": False,
                               "brief": "Unusual consumption of a medication. Suggest a review task for a pharmacist (reconcile counts, check "
                                        "for diversion signals per policy). Never accuse anyone; never change stock."},
    "adt.pending_admission": {"agent": "hospital_operations", "trigger": "case_escalation", "actions": ["create_task"],
                              "roles": ["bed_manager", "hospital_admin"], "default": False,
                              "brief": "Escalated: an admitted patient is still waiting for a bed. Suggest a bed-management task. Never "
                                       "assign beds or move patients."},
    "beds.cleaning_delay": {"agent": "hospital_operations", "trigger": "case_escalation", "actions": ["create_task"],
                            "roles": ["bed_manager", "hospital_admin"], "default": False,
                            "brief": "Escalated: a bed is waiting for cleaning. Suggest a follow-up task for bed management / EVS. Never "
                                     "change bed status."},
    "ed.boarding": {"agent": "hospital_operations", "trigger": "case_escalation", "actions": ["create_task"],
                    "roles": ["bed_manager", "hospital_admin"], "default": False,
                    "brief": "Escalated: an ED patient admitted but boarding. Suggest an operational task (bed placement review). The "
                             "clinical team keeps all clinical decisions."},
    "billing.prior_auth_required": {"agent": "claims_review", "trigger": "case_open", "actions": ["create_task"],
                                    "roles": ["billing", "insurance_specialist"], "default": False,
                                    "brief": "A service needs prior authorization. Suggest a task to start or chase the authorization. Never "
                                             "submit anything to a payer."},
    "billing.prior_auth_expiring": {"agent": "claims_review", "trigger": "case_open", "actions": ["create_task"],
                                    "roles": ["billing", "insurance_specialist"], "default": False,
                                    "brief": "A prior authorization expires before the service. Suggest a renewal/extension task. Never "
                                             "submit anything to a payer."},
    "journey.follow_up_not_booked": {"agent": "patient_communication", "trigger": "case_open", "actions": ["create_task", "patient_message"],
                                     "roles": ["receptionist"], "default": False,
                                     "brief": "A planned follow-up visit is not booked. Suggest a scheduling task or a short administrative "
                                              "portal reminder. No clinical advice, no urgency claims."},
})
# Safety-critical monitors stay strictly rule-based: AI is never in (or enabled for) their path.
SAFETY_RULE_ONLY = {"lab.critical_unacknowledged", "radiology.critical_unacknowledged", "ed.door_to_provider"}


def ai_enabled_for(db: Session, org_id: uuid.UUID, rule_key: str) -> bool:
    """Per-monitor AI switch (MonitorConfig.config['ai_assist']; default from RULES). Safety-critical monitors: always False."""
    rule = RULES.get(rule_key)
    if not rule or rule_key in SAFETY_RULE_ONLY:
        return False
    from app.models import MonitorConfig

    row = db.scalar(select(MonitorConfig).where(MonitorConfig.organization_id == org_id, MonitorConfig.monitor_key == rule_key,
                                                MonitorConfig.facility_id.is_(None)))
    v = (row.config or {}).get("ai_assist") if row else None
    return bool(rule.get("default", True) if v is None else v)


def _agent_ok(db: Session, org_id: uuid.UUID, agent: str, facility_id=None) -> tuple[object | None, str | None]:
    from app.agents.runner import AgentError, load_policy

    try:
        return load_policy(db, org_id, agent, facility_id), None
    except AgentError as e:
        return None, str(e)


MAX_PER_SWEEP = 4          # per organization per sweep — keeps cost and queue bounded
OPEN_WINDOW = timedelta(hours=24)
RETRY_AFTER = timedelta(minutes=30)
MAX_ATTEMPTS = 2

INSTRUCTIONS = ("You help a hospital operations team with ONE automation case. Read the case and choose at most one next action "
                "from the allowed list, or 'none' if nothing useful can be proposed. A person reviews and approves every action; "
                "you execute nothing. Use only facts in the case — do not invent clinical information, codes, payer results or "
                "names. Keep the summary to two sentences and cite the case reference.")


class Suggestion(BaseModel):
    summary: str = Field(max_length=600, description="What is going on and why the action helps (cite the case ref)")
    action: ActionName
    reason: str = Field(max_length=400)
    task_title: str | None = Field(default=None, max_length=180)
    task_role: str | None = None
    task_priority: Literal["low", "normal", "high", "urgent"] | None = None
    quantity: int | None = Field(default=None, description="adjust_purchase_request only")
    message_subject: str | None = Field(default=None, max_length=140)
    message_body: str | None = Field(default=None, max_length=1200)


# ---------------------------------------------------------------------------------------------- selection (sweep)

def _claim(db: Session, case_id: uuid.UUID, trigger: str) -> bool:
    """Atomically mark a case as being assisted for this trigger (idempotent across workers and sweeps)."""
    res = db.execute(text("""UPDATE cases SET data = jsonb_set(coalesce(data, '{}'::jsonb), '{ai_assist}',
                               jsonb_build_object('trigger', CAST(:t AS text), 'status', 'queued', 'attempts',
                                 coalesce((data->'ai_assist'->>'attempts')::int, 0) + 1, 'at', CAST(:at AS text)))
                             WHERE id = :id AND (data->'ai_assist' IS NULL OR data->'ai_assist'->>'trigger' <> :t
                               OR (data->'ai_assist'->>'status' = 'failed' AND coalesce((data->'ai_assist'->>'attempts')::int, 0) < :max
                                   AND (data->'ai_assist'->>'at')::timestamptz < :retry))"""),
                     {"id": case_id, "t": trigger, "at": now().isoformat(), "max": MAX_ATTEMPTS, "retry": now() - RETRY_AFTER})
    return res.rowcount == 1


def candidates(db: Session, org_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
    out: list[tuple[uuid.UUID, str]] = []
    for key, rule in RULES.items():
        if not ai_enabled_for(db, org_id, key) or _agent_ok(db, org_id, rule["agent"])[0] is None:
            continue  # monitor AI off, or the assistant is disabled — no claim, no call
        q = select(Case.id, Case.data).where(Case.organization_id == org_id, Case.rule_key == key, Case.status.in_(CASE_OPEN))
        if rule["trigger"] == "case_open":
            q = q.where(Case.created_at > now() - OPEN_WINDOW)
        else:
            q = q.where(Case.status == "escalated")
        for cid, data in db.execute(q.order_by(Case.created_at.desc()).limit(MAX_PER_SWEEP * 2)).all():
            a = (data or {}).get("ai_assist") or {}
            if a.get("trigger") == rule["trigger"] and a.get("status") != "failed":
                continue
            out.append((cid, rule["trigger"]))
    return out[:MAX_PER_SWEEP]


def sweep(db: Session, org_ids: list[uuid.UUID] | None = None) -> int:
    """Queue AI assistance for newly opened/escalated cases of the selected kinds. Call AFTER the engine committed."""
    from app.models import Organization

    if org_ids is None:
        org_ids = list(db.scalars(select(Organization.id).where(Organization.status == "active")))
    queued = 0
    for org_id in org_ids:
        for cid, trig in candidates(db, org_id):
            if _claim(db, cid, trig):
                db.commit()
                queued += 1
                _enqueue(cid, trig)
    return queued


def _enqueue(case_id: uuid.UUID, trigger: str) -> None:
    try:
        from app.tasks import case_assist_task

        case_assist_task.delay(str(case_id), trigger)
    except Exception:  # noqa: BLE001 — broker down: the claim stays 'queued'; mark failed so a later sweep retries
        log.exception("could not queue case assistance")
        from app.core.db import SessionLocal

        with SessionLocal() as db:
            _mark(db, db.get(Case, case_id), status="failed", error="queue unavailable")
            db.commit()


# ---------------------------------------------------------------------------------------------- one case

def _mark(db: Session, case: Case | None, **fields) -> None:
    if case:
        case.data = {**(case.data or {}), "ai_assist": {**((case.data or {}).get("ai_assist") or {}), **fields, "at": now().isoformat()}}


def _provider(db: Session, org_id: uuid.UUID, agent: str):
    """(EffectiveAI | None, scope token | None, reason): the platform AI configuration, if it serves this assistant."""
    from app.ai.config import platform_effective

    plat = platform_effective()
    if plat.provider == "openai" and plat.api_key and plat.text_model and (not plat.allowed_agents or agent in plat.allowed_agents):
        return plat, None, None
    return None, None, plat.reason or "No AI provider is configured for automatic assistance."


def _context(db: Session, case: Case) -> str:
    ev = db.scalars(select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.at.desc()).limit(8)).all()
    lines = [f"Case C{case.number} [{case.kind}] severity={case.severity} status={case.status} owner_role={case.assigned_role}",
             f"Title: {case.title}", f"Summary: {case.summary or '-'}", f"Evidence: {case.evidence}",
             "Recent timeline: " + " | ".join(f"{e.at:%m-%d %H:%M} {e.message}" for e in reversed(ev))]
    return "\n".join(lines)[:6000]


def assist(db: Session, case_id: uuid.UUID, trigger: str) -> AgentRun | None:
    from app.agents.runner import ai_source
    from app.ai import demo_scope, usage
    from app.ai.openai_provider import OpenAICore
    from app.ai.policy import contains_phi
    from app.ai.provider import AIError, AIPolicyError
    from app.engine.cases import log_event

    case = db.get(Case, case_id)
    rule = RULES.get(case.rule_key or "") if case else None
    if not case or not rule or case.status not in CASE_OPEN:
        _mark(db, case, status="skipped")
        db.commit()
        return None
    agent = rule["agent"]
    # Background re-validation: the monitor's AI switch and the assistant's enabled state are checked again at execution.
    cfg, why = _agent_ok(db, case.organization_id, agent, case.facility_id)
    if cfg is None or not ai_enabled_for(db, case.organization_id, case.rule_key):
        _mark(db, case, status="disabled", error=(why or "AI assistance is turned off for this monitor")[:200])
        db.commit()
        return None
    eff, token, reason = _provider(db, case.organization_id, agent)
    run = AgentRun(organization_id=case.organization_id, agent_key=agent, agent_version=cfg.version, facility_id=case.facility_id,
                   subject_type="case", subject_id=str(case.id), patient_id=case.patient_id, input=f"C{case.number} {case.title}"[:4000],
                   mode="openai" if eff else "rule_based", trigger=trigger, ai_source=ai_source(eff) if eff else "rules",
                   model=(cfg.model or eff.model_for(agent)) if eff else "rules-v1", status="running",
                   context_type="case", context_id=f"C{case.number}")
    db.add(run)
    db.flush()
    start = time.perf_counter()

    def unavailable(why: str, status: str = "unavailable") -> AgentRun:
        run.mode, run.status, run.error = "rule_based", "blocked" if status == "unavailable" else "failed", why[:300]
        run.ai_source = run.ai_source if status == "failed" else "rules"
        log_event(db, case, "ai_unavailable", f"AI assistance unavailable — {why[:200].rstrip('.')}. The standard workflow continues.",
                  data={"agent": agent, "run_id": str(run.id), "trigger": trigger})
        _mark(db, case, status=status, run_id=str(run.id), error=why[:200])
        return run

    try:
        if not eff:
            return unavailable(reason)
        if not usage.take_request(f"auto:{case.organization_id}:day:{usage.day_key()}", settings.ai_auto_assist_daily_limit):
            return unavailable(f"today's automatic AI limit ({settings.ai_auto_assist_daily_limit}) is reached")
        from app.ai import limits

        reserve = float(cfg.max_cost_usd or 0.25)
        if not usage.reserve_cost(limits.org_month_key(case.organization_id), reserve, settings.ai_org_monthly_budget_usd):
            return unavailable(f"the organization's estimated monthly AI budget (${settings.ai_org_monthly_budget_usd:.2f}) is reached")
        reserved = reserve
        with demo_scope.use(token, eff if token else None):
            s, meta = OpenAICore(cfg=eff).structured(
                system=f"{INSTRUCTIONS}\n\nThis case kind: {rule['brief']}\nAllowed actions: {', '.join(['none', *rule['actions']])}. "
                       f"Task roles allowed: {', '.join(rule['roles'])}.",
                content=[{"type": "input_text", "text": f"<case>{_context(db, case)}</case>"}], schema=Suggestion,
                contains_phi=contains_phi(db, case.organization_id), model=run.model, max_output_tokens=1200, name="case_suggestion")
        run.input_tokens, run.output_tokens, run.cost_usd, run.model = meta.input_tokens, meta.output_tokens, meta.cost_usd, meta.model
        if meta.cost_usd is not None:
            usage.adjust(limits.org_month_key(case.organization_id), cost_delta=meta.cost_usd - reserved)
        approval = _propose(db, case, rule, s)
        run.output = s.summary
        run.approvals = [str(approval.id)] if approval else []
        run.tool_calls = [{"tool": f"propose:{s.action}", "ok": approval is not None or s.action == "none", "arguments": {"reason": s.reason[:200]}}]
        run.status = "succeeded"
        log_event(db, case, "ai_assist", f"AI assisted ({agent.replace('_', ' ').title()}): {s.summary[:300]}", actor_kind="agent",
                  data={"agent": agent, "run_id": str(run.id), "model": meta.model, "source": run.ai_source, "trigger": trigger,
                        "action": s.action, "approval_id": str(approval.id) if approval else None})
        _mark(db, case, status="proposed" if approval else "no_action", run_id=str(run.id), approval_id=str(approval.id) if approval else None)
    except demo_scope.DemoLimitError as e:
        unavailable(str(e))
    except AIPolicyError as e:
        unavailable(str(e))
    except (AIError, _Invalid) as e:
        unavailable(f"AI provider error: {str(e)[:200]}", status="failed")
    except Exception as e:  # noqa: BLE001
        log.exception("case assistance failed")
        unavailable(f"{type(e).__name__}", status="failed")
    finally:
        run.latency_ms, run.finished_at = int((time.perf_counter() - start) * 1000), now()
        db.commit()
    return run


class _Invalid(ValueError):
    pass


def _propose(db: Session, case: Case, rule: dict, s: Suggestion):
    """Turn a validated suggestion into ONE approval request handled by an existing executor (or nothing)."""
    import app.agents.tools  # noqa: F401 — registers the executors
    from app.engine import approvals as AP
    from app.models import PurchaseRequest

    agent = rule["agent"]
    if s.action == "none":
        return None
    if s.action not in rule["actions"]:
        raise _Invalid(f"action '{s.action}' is not allowed for {case.kind}")
    if s.action == "create_task":
        role = s.task_role if s.task_role in rule["roles"] else rule["roles"][0]
        if not s.task_title:
            raise _Invalid("task without a title")
        return AP.request_approval(db, case.organization_id, kind="agent.create_task", title=f"AI proposal: {s.task_title}",
                                   summary=s.reason, payload={"title": s.task_title, "role": role, "priority": s.task_priority or "normal",
                                                              "case_id": str(case.id)},
                                   required_permission=P.CASES_WORK, case=case, requested_by_agent=agent)
    if s.action == "adjust_purchase_request":
        pr = db.scalar(select(PurchaseRequest).where(PurchaseRequest.case_id == case.id, PurchaseRequest.status == "submitted"))
        rec = int((case.evidence or {}).get("recommended_qty") or 0)
        if not pr or not s.quantity or rec <= 0:
            raise _Invalid("no submitted purchase request or recommendation to adjust")
        if not (rec * 0.5 <= s.quantity <= rec * 2) or s.quantity == pr.quantity:
            raise _Invalid("quantity outside the allowed range")
        return AP.request_approval(db, case.organization_id, kind="inventory.adjust_purchase_request",
                                   title=f"AI proposal: change purchase request #{pr.number} to {s.quantity}", summary=s.reason,
                                   payload={"purchase_request_id": str(pr.id), "quantity": s.quantity, "from": pr.quantity},
                                   required_permission=P.PROCUREMENT_APPROVE, case=case, requested_by_agent=agent)
    if s.action == "request_insurance_update":
        if not case.patient_id:
            raise _Invalid("case has no patient")
        return AP.request_approval(db, case.organization_id, kind="insurance.request_update", title="AI proposal: ask patient to update insurance",
                                   summary=s.reason, payload={"case_id": str(case.id), "reason": (s.message_body or s.reason)[:300]},
                                   required_permission=P.INSURANCE_WRITE, case=case, requested_by_agent=agent)
    if s.action == "patient_message":
        if not case.patient_id or not s.message_subject or not s.message_body:
            raise _Invalid("message needs a patient, subject and body")
        return AP.request_approval(db, case.organization_id, kind="agent.patient_message", title=f"AI proposal: message patient — {s.message_subject}",
                                   summary=s.message_body, payload={"patient_id": str(case.patient_id), "subject": s.message_subject,
                                                                    "body": s.message_body, "case_id": str(case.id)},
                                   required_permission=P.MESSAGES, case=case, requested_by_agent=agent)
    raise _Invalid("unknown action")
