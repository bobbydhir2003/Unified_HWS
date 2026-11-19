"""Agent definitions (defaults per organization) and the runner.

Execution: authenticated user (or scheduled trigger) → agent enabled for the facility → user holds the agent's permission →
model call with only the agent's allowed tools → every tool call re-validated server-side (tools.execute) → proposals land
in the approval queue → run logged (tools, tokens, cost, status) + audited. Without an AI provider, a deterministic
read-only plan runs instead and is labeled 'rule_based'."""

import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import tools as T
from app.core.permissions import P
from app.core.security import now
from app.models import AgentConfig, AgentConfigVersion, AgentRun

GUARD = ("You assist hospital staff. You can only use the provided tools; you have no other data access. Never diagnose, prescribe, "
         "change orders, codes or claims. Anything that changes data must be a proposal via a propose_* tool — a person approves it. "
         "Cite case references (e.g. C1042) and sources you used. If tools return nothing relevant, say so.")

DEFAULTS = [
    ("insurance_guardian", "Insurance Guardian", "Helps resolve insurance verification issues before visits.", ["list_open_cases", "get_case", "get_patient_coverage", "propose_task", "propose_patient_message"], P.INSURANCE_WRITE, "manual"),
    ("doctor_assistant", "Doctor Assistant", "Answers questions from one patient's chart with citations (runs in the chart's Ask AI panel).", [], P.CLINICAL_READ, "feature"),
    ("medical_scribe", "Medical Scribe", "Drafts SOAP notes from consented visit conversations (runs in the visit's Scribe panel).", [], P.CLINICAL_WRITE, "feature"),
    ("document_intelligence", "Document Intelligence", "Classifies and extracts incoming documents for staff review (runs on upload).", [], P.DOCUMENTS_REVIEW, "feature"),
    ("pharmacy_watchdog", "Pharmacy Watchdog", "Explains inventory alerts and prepares staff actions.", ["list_open_cases", "get_case", "get_inventory_item", "propose_task"], P.INVENTORY_READ, "manual"),
    ("discharge_coordination", "Discharge Coordination", "Summarizes outstanding discharge tasks and helps coordinate teams.", ["list_open_cases", "get_case", "get_discharge_status", "propose_task"], P.ADT_READ, "manual"),
    ("hospital_operations", "Hospital Operations", "Explains operational issues and recommends administrative actions.", ["get_operations_summary", "list_open_cases", "get_case", "get_recent_volume", "get_staffing_gaps", "propose_task"], P.COMMAND_CENTER, "manual"),
    ("claims_review", "Claims Review", "Identifies possibly missing billing information (never edits claims).", ["list_open_cases", "get_case", "get_claim_findings", "propose_task"], P.BILLING_READ, "manual"),
    ("patient_communication", "Patient Communication", "Drafts routine administrative messages for staff approval.", ["get_patient_coverage", "list_open_cases", "propose_patient_message"], P.MESSAGES, "manual"),
    ("staff_scheduling", "Staff Scheduling", "Explains staffing gaps and solver-generated alternatives (managers decide).", ["get_staffing_gaps", "list_open_cases", "propose_task"], P.ROSTER_MANAGE, "manual"),
]

RULE_PLANS = {
    "insurance_guardian": [("list_open_cases", {"category": "insurance", "limit": 10})],
    "pharmacy_watchdog": [("list_open_cases", {"category": "pharmacy", "limit": 10}), ("list_open_cases", {"category": "inventory", "limit": 10})],
    "discharge_coordination": [("list_open_cases", {"category": "discharge", "limit": 10})],
    "hospital_operations": [("get_operations_summary", {}), ("list_open_cases", {"limit": 8})],
    "claims_review": [("list_open_cases", {"category": "billing", "limit": 10})],
    "staff_scheduling": [("get_staffing_gaps", {})],
    "patient_communication": [("list_open_cases", {"category": "insurance", "limit": 5})],
}


def ensure_defaults(db: Session, org_id) -> None:
    have = set(db.scalars(select(AgentConfig.key).where(AgentConfig.organization_id == org_id)))
    for key, name, purpose, tools, perm, trigger in DEFAULTS:
        if key in have:
            continue
        cfg = AgentConfig(organization_id=org_id, key=key, name=name, purpose=purpose, instructions=f"{purpose} {GUARD}", allowed_tools=tools,
                          required_permission=perm, trigger=trigger)
        db.add(cfg)
        db.flush()
        db.add(AgentConfigVersion(organization_id=org_id, agent_key=key, version=1, snapshot=snapshot(cfg), note="Default configuration"))


def snapshot(c: AgentConfig) -> dict:
    return {k: getattr(c, k) for k in ("name", "purpose", "instructions", "allowed_tools", "model", "trigger", "required_permission",
                                       "max_tool_calls", "timeout_seconds", "max_cost_usd", "enabled", "facility_overrides")}


class AgentError(ValueError):
    pass


def _summarize(key: str, calls: list[dict]) -> str:
    lines = []
    for c in calls:
        r = c["result"]
        if "cases" in r:
            cs = r["cases"]
            label = (c["arguments"].get("category") or "operational").replace("_", " ")
            lines.append(f"{len(cs)} open {label} case(s)" + (": " + "; ".join(f"{x['title']} [{x['ref']}]" for x in cs[:5]) if cs else "."))
        elif "tiles" in r:
            lines.append("Operations: " + "; ".join(f"{t['metric']} {t['value']}" for t in r["tiles"][:8]) + ".")
        elif "gaps" in r:
            g = r["gaps"]
            lines.append(f"{len(g)} staffing gap(s)" + (": " + "; ".join(f"{x['department']} {x['short']} {x['role']} {x['window']} {x['start'][:16]}" for x in g[:5]) if g else "."))
    if key == "patient_communication":
        lines.append("Drafting patient messages needs an AI provider; use the case worklist to message patients directly.")
    return "\n".join(lines) or "Nothing relevant found."


def run_agent(ctx, key: str, user_input: str, *, facility_id: uuid.UUID | None = None, subject_type: str | None = None,
              subject_id: str | None = None) -> AgentRun:
    ensure_defaults(ctx.db, ctx.org_id)
    cfg = ctx.db.scalar(select(AgentConfig).where(AgentConfig.organization_id == ctx.org_id, AgentConfig.key == key))
    if not cfg:
        raise AgentError("Unknown agent")
    if cfg.trigger == "feature":
        raise AgentError(f"{cfg.name} runs inside its own workflow screen")
    enabled = cfg.facility_overrides.get(str(facility_id), cfg.enabled) if facility_id else cfg.enabled
    if not enabled:
        raise AgentError(f"{cfg.name} is disabled" + (" for this facility" if facility_id else ""))
    if not ctx.can(cfg.required_permission):
        raise AgentError(f"You need {cfg.required_permission} to use {cfg.name}")
    from app.ai.config import effective
    from app.ai.openai_provider import OpenAICore, available

    live = available()
    run = AgentRun(organization_id=ctx.org_id, agent_key=key, agent_version=cfg.version, user_id=ctx.user.id, facility_id=facility_id,
                   subject_type=subject_type, subject_id=subject_id, input=(user_input or "")[:4000], mode="openai" if live else "rule_based",
                   model=(cfg.model or effective().model_for(key)) if live else "rules-v1")
    ctx.db.add(run)
    ctx.db.flush()
    start = time.perf_counter()
    calls: list[dict] = []

    def execute(name: str, args: dict) -> dict:
        if time.perf_counter() - start > cfg.timeout_seconds:
            return {"error": "agent time limit reached"}
        result = T.execute(ctx, key, list(cfg.allowed_tools), name, args)
        calls.append({"tool": name, "arguments": args, "ok": "error" not in result, "result": result})
        return result

    try:
        if live:
            from app.ai.policy import contains_phi

            text, meta = OpenAICore().tool_loop(system=cfg.instructions, user=f"<request>{user_input}</request>", tools=T.openai_tool_specs(list(cfg.allowed_tools)),
                                                execute=execute, contains_phi=contains_phi(ctx.db, ctx.org_id), model=run.model, max_steps=cfg.max_tool_calls)
            run.output, run.input_tokens, run.output_tokens, run.cost_usd = text, meta.input_tokens, meta.output_tokens, meta.cost_usd
            run.status = "limit_reached" if "tool-call limit" in text else "succeeded"
            if meta.cost_usd is not None and meta.cost_usd > cfg.max_cost_usd:
                run.status, run.error = "limit_reached", f"cost {meta.cost_usd:.4f} exceeded limit {cfg.max_cost_usd:.2f}"
        else:
            for name, args in RULE_PLANS.get(key, [])[: cfg.max_tool_calls]:
                execute(name, args)
            run.output = _summarize(key, calls) + "\n\n(Rule-based summary — no AI provider configured.)"
            run.status = "succeeded"
    except Exception as e:  # noqa: BLE001
        run.status, run.error = "failed", f"{type(e).__name__}: {str(e)[:300]}"
    run.tool_calls = [{k: v for k, v in c.items() if k != "result"} | {"result_preview": str(c["result"])[:300]} for c in calls]
    run.approvals = [c["result"].get("approval_id") for c in calls if c["result"].get("approval_id")]
    if any(not c["ok"] and "permission denied" in str(c["result"]) for c in calls) and run.status == "succeeded" and not live:
        run.status = "blocked"
    run.latency_ms, run.finished_at = int((time.perf_counter() - start) * 1000), now()
    ctx.audit("agent.run", resource_type="agent", resource_id=key, details={"run_id": str(run.id), "mode": run.mode, "status": run.status,
                                                                            "tools": [c["tool"] for c in calls], "proposals": len(run.approvals)})
    return run
