"""AI Agent Studio (C2) and AI governance analytics/feedback (C7)."""

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.agents import runner as R
from app.agents import tools as T
from app.api.deps import TenantContext, get_ctx, require
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import AgentConfig, AgentConfigVersion, AgentRun, AIFeedback, AIJob

router = APIRouter(tags=["agents"])


def cfg_out(c: AgentConfig, ctx) -> dict:
    return {"key": c.key, "name": c.name, "purpose": c.purpose, "instructions": c.instructions, "allowed_tools": c.allowed_tools, "model": c.model,
            "trigger": c.trigger, "required_permission": c.required_permission, "max_tool_calls": c.max_tool_calls, "timeout_seconds": c.timeout_seconds,
            "max_cost_usd": c.max_cost_usd, "enabled": c.enabled, "facility_overrides": c.facility_overrides, "version": c.version,
            "can_run": c.trigger != "feature" and ctx.can(c.required_permission) and c.enabled}


@router.get("/agents")
def list_agents(ctx: TenantContext = Depends(require(P.AI_USE))):
    R.ensure_defaults(ctx.db, ctx.org_id)
    ctx.db.commit()
    stats = {k: (n, f, c) for k, n, f, c in ctx.db.execute(select(AgentRun.agent_key, func.count(), func.count().filter(AgentRun.status == "failed"),
                                                                    func.coalesce(func.sum(AgentRun.cost_usd), 0)).where(
        AgentRun.organization_id == ctx.org_id, AgentRun.started_at > now() - timedelta(days=30)).group_by(AgentRun.agent_key)).all()}
    rows = ctx.db.scalars(select(AgentConfig).where(AgentConfig.organization_id == ctx.org_id).order_by(AgentConfig.name)).all()
    return [{**cfg_out(c, ctx), "runs_30d": stats.get(c.key, (0, 0, 0))[0], "failed_30d": stats.get(c.key, (0, 0, 0))[1],
             "cost_30d_usd": float(stats.get(c.key, (0, 0, 0))[2])} for c in rows]


@router.get("/agents/tools")
def list_tools(ctx: TenantContext = Depends(require(P.AI_USE))):
    return [{"name": t.name, "description": t.description, "permission": t.permission, "kind": t.kind} for t in T.REGISTRY.values()]


class AgentPatch(BaseModel):
    instructions: str | None = Field(default=None, min_length=20, max_length=8000)
    allowed_tools: list[str] | None = None
    model: str | None = Field(default=None, max_length=80)
    max_tool_calls: int | None = Field(default=None, ge=1, le=20)
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    max_cost_usd: float | None = Field(default=None, ge=0, le=50)
    enabled: bool | None = None
    facility_overrides: dict[str, bool] | None = None
    note: str | None = Field(default=None, max_length=300)


@router.put("/agents/{key}")
def update_agent(key: str, body: AgentPatch, ctx: TenantContext = Depends(require(P.AI_MANAGE))):
    c = ctx.db.scalar(select(AgentConfig).where(AgentConfig.organization_id == ctx.org_id, AgentConfig.key == key))
    if not c:
        raise not_found("Agent")
    if body.allowed_tools is not None:
        unknown = [t for t in body.allowed_tools if t not in T.REGISTRY]
        if unknown:
            raise bad_request(f"Unknown tools: {unknown}")
    data = body.model_dump(exclude_unset=True, exclude={"note"})
    for k, v in data.items():
        setattr(c, k, v)
    c.version, c.updated_by_id = c.version + 1, ctx.user.id
    ctx.db.add(AgentConfigVersion(organization_id=ctx.org_id, agent_key=key, version=c.version, snapshot=R.snapshot(c), changed_by_id=ctx.user.id, note=body.note))
    ctx.audit("agent.config_updated", resource_type="agent", resource_id=key, details={"version": c.version, "fields": list(data)})
    ctx.db.commit()
    return cfg_out(c, ctx)


@router.get("/agents/{key}/versions")
def versions(key: str, ctx: TenantContext = Depends(require(P.AI_USE))):
    rows = ctx.db.scalars(select(AgentConfigVersion).where(AgentConfigVersion.organization_id == ctx.org_id, AgentConfigVersion.agent_key == key)
                          .order_by(AgentConfigVersion.version.desc())).all()
    return [{"version": v.version, "note": v.note, "created_at": v.created_at, "snapshot": v.snapshot} for v in rows]


class RunIn(BaseModel):
    input: str = Field(min_length=2, max_length=4000)
    facility_id: uuid.UUID | None = None
    subject_type: str | None = None
    subject_id: str | None = None


def run_out(r: AgentRun) -> dict:
    return {"id": r.id, "agent_key": r.agent_key, "agent_version": r.agent_version, "mode": r.mode, "model": r.model, "status": r.status, "input": r.input,
            "output": r.output, "tool_calls": r.tool_calls, "approvals": r.approvals, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
            "cost_usd": float(r.cost_usd) if r.cost_usd is not None else None, "latency_ms": r.latency_ms, "error": r.error, "started_at": r.started_at,
            "user_id": r.user_id}


@router.post("/agents/{key}/run")
def run(key: str, body: RunIn, ctx: TenantContext = Depends(get_ctx)):
    ctx.require(P.AI_USE)
    if body.facility_id:
        ctx.require_facility(body.facility_id)
    try:
        r = R.run_agent(ctx, key, body.input, facility_id=body.facility_id, subject_type=body.subject_type, subject_id=body.subject_id)
    except R.AgentError as e:
        ctx.db.rollback()
        raise bad_request(str(e)) from None
    ctx.db.commit()
    return run_out(r)


@router.get("/agents/runs/list")
def runs(agent: str | None = None, status: str | None = None, ctx: TenantContext = Depends(require(P.AI_USE))):
    q = select(AgentRun).where(AgentRun.organization_id == ctx.org_id)
    if not ctx.can(P.AI_MANAGE):
        q = q.where(AgentRun.user_id == ctx.user.id)
    if agent:
        q = q.where(AgentRun.agent_key == agent)
    if status:
        q = q.where(AgentRun.status == status)
    return [run_out(r) for r in ctx.db.scalars(q.order_by(AgentRun.started_at.desc()).limit(100))]


@router.post("/agents/runs/{rid}/retry")
def retry(rid: uuid.UUID, ctx: TenantContext = Depends(require(P.AI_USE))):
    r = ctx.db.get(AgentRun, rid)
    if not r or r.organization_id != ctx.org_id or (r.user_id != ctx.user.id and not ctx.can(P.AI_MANAGE)):
        raise not_found("Run")
    return run(r.agent_key, RunIn(input=r.input or "retry", facility_id=r.facility_id, subject_type=r.subject_type, subject_id=r.subject_id), ctx=ctx)


class FeedbackIn(BaseModel):
    agent_run_id: uuid.UUID | None = None
    ai_job_id: uuid.UUID | None = None
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=500)


@router.post("/ai/feedback", status_code=201)
def feedback(body: FeedbackIn, ctx: TenantContext = Depends(require(P.AI_USE))):
    if not (body.agent_run_id or body.ai_job_id):
        raise bad_request("Reference an agent run or AI job")
    ctx.db.add(AIFeedback(organization_id=ctx.org_id, user_id=ctx.user.id, **body.model_dump()))
    ctx.db.commit()
    return {"message": "Thanks for the feedback"}


@router.get("/ai/governance")
def governance(days: int = 30, ctx: TenantContext = Depends(require(P.AI_MANAGE))):
    """Usage, cost, failures and feedback across AI features and agents (C7). Numbers from ai_jobs/agent_runs/ai_feedback."""
    since = now() - timedelta(days=min(days, 365))
    jobs = ctx.db.execute(select(AIJob.kind, AIJob.provider, func.count(), func.count().filter(AIJob.status == "failed"), func.coalesce(func.sum(AIJob.cost_usd), 0),
                                 func.coalesce(func.sum(AIJob.input_tokens), 0), func.coalesce(func.sum(AIJob.output_tokens), 0), func.avg(AIJob.latency_ms))
                          .where(AIJob.organization_id == ctx.org_id, AIJob.created_at > since).group_by(AIJob.kind, AIJob.provider)).all()
    agents = ctx.db.execute(select(AgentRun.agent_key, AgentRun.mode, func.count(), func.count().filter(AgentRun.status.in_(("failed", "limit_reached", "blocked"))),
                                   func.coalesce(func.sum(AgentRun.cost_usd), 0), func.avg(AgentRun.latency_ms))
                            .where(AgentRun.organization_id == ctx.org_id, AgentRun.started_at > since).group_by(AgentRun.agent_key, AgentRun.mode)).all()
    fb = dict(ctx.db.execute(select(AIFeedback.rating, func.count()).where(AIFeedback.organization_id == ctx.org_id, AIFeedback.created_at > since)
                             .group_by(AIFeedback.rating)).all())
    failures = ctx.db.scalars(select(AgentRun).where(AgentRun.organization_id == ctx.org_id, AgentRun.status.in_(("failed", "limit_reached", "blocked")))
                              .order_by(AgentRun.started_at.desc()).limit(20)).all()
    phi_external = ctx.db.scalar(select(func.count()).select_from(AIJob).where(AIJob.organization_id == ctx.org_id, AIJob.phi_sent_externally.is_(True), AIJob.created_at > since))
    from app.ai.config import active_provider
    from app.core.config import settings

    return {"window_days": days, "active_provider": active_provider(), "phi_allowed": settings.ai_phi_allowed, "phi_sent_externally": phi_external,
            "features": [{"kind": k, "provider": p, "calls": n, "failed": f, "cost_usd": float(c), "input_tokens": int(i), "output_tokens": int(o),
                          "avg_latency_ms": round(float(lat)) if lat else None} for k, p, n, f, c, i, o, lat in jobs],
            "agents": [{"agent": k, "mode": m, "runs": n, "problems": f, "cost_usd": float(c), "avg_latency_ms": round(float(lat)) if lat else None}
                       for k, m, n, f, c, lat in agents],
            "feedback": {"up": fb.get("up", 0), "down": fb.get("down", 0)},
            "recent_problems": [run_out(r) for r in failures]}


def eval_out(r) -> dict:
    return {"id": r.id, "suite": r.suite, "provider": r.provider, "model": r.model, "samples": r.samples, "score": r.score, "metrics": r.metrics,
            "cases": r.cases, "created_at": r.created_at}


@router.get("/ai/evaluations")
def evaluations(suite: str | None = None, ctx: TenantContext = Depends(require(P.AI_MANAGE))):
    """Evaluation history (C7). Synthetic labeled samples only; scores describe those samples, not clinical validity."""
    from app.ai.evals import SUITES
    from app.models import AIEvalRun

    q = select(AIEvalRun).where(AIEvalRun.organization_id == ctx.org_id)
    if suite:
        q = q.where(AIEvalRun.suite == suite)
    return {"suites": list(SUITES), "runs": [eval_out(r) for r in ctx.db.scalars(q.order_by(AIEvalRun.created_at.desc()).limit(50))]}


@router.post("/ai/evaluations/{suite}", status_code=201)
def run_evaluation(suite: str, ctx: TenantContext = Depends(require(P.AI_MANAGE))):
    from app.ai.evals import SUITES

    if suite not in SUITES:
        raise not_found("Evaluation suite")
    r = SUITES[suite](ctx)
    ctx.db.flush()
    ctx.audit("ai.evaluation_run", resource_type="ai_eval", resource_id=r.id, details={"suite": suite, "score": r.score, "provider": r.provider})
    ctx.db.commit()
    return eval_out(r)
