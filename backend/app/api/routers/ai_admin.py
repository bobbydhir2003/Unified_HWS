"""Super Admin → AI Settings. The API key is write-only: accepted over HTTPS, encrypted at rest, never returned
(only a masked hint). Model identifiers are configuration; 'Test connection' verifies them against the provider's
model list for this account instead of assuming they exist."""

import re
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select

from app.ai.config import effective, invalidate
from app.api.deps import TenantContext, require
from app.core import demo
from app.core.config import settings
from app.core.crypto import encrypt, mask
from app.core.errors import bad_request
from app.core.permissions import P
from app.core.security import now
from app.models import AIProviderSettings

router = APIRouter(tags=["ai-admin"])

# Suggestions shown in the UI only. They are NOT assumed valid — Test connection checks them against models.list().
SUGGESTED = {"text": "gpt-4.1-mini", "vision": "gpt-4.1-mini", "transcription": "gpt-4o-mini-transcribe", "realtime": "gpt-4o-mini-realtime-preview"}
AGENTS = ["insurance_guardian", "doctor_assistant", "medical_scribe", "document_intelligence", "pharmacy_watchdog", "discharge_coordination",
          "hospital_operations", "claims_review", "patient_communication", "staff_scheduling"]
MODEL_RE = re.compile(r"^[A-Za-z0-9._:\-]{2,80}$")


def _row(ctx: TenantContext) -> AIProviderSettings | None:
    return ctx.db.scalar(select(AIProviderSettings).where(AIProviderSettings.scope == "platform"))


def _out(ctx: TenantContext, row: AIProviderSettings | None) -> dict:
    e = effective()
    return {
        "provider": row.provider if row else settings.ai_provider, "source": "ui" if row else "environment",
        "key": {"configured": bool(row and row.api_key_encrypted) or (not row and bool(settings.openai_api_key)),
                "hint": None if demo.is_demo_user(ctx.user) else (row.api_key_hint if row else (mask(settings.openai_api_key) if settings.openai_api_key else None)),
                "updated_at": row.key_updated_at if row else None},
        "models": {"text": (row.text_model if row else None) or settings.ai_text_model or None,
                   "vision": (row.vision_model if row else None) or settings.ai_vision_model or None,
                   "transcription": (row.transcription_model if row else None) or settings.ai_transcription_model or None,
                   "realtime": row.realtime_model if row else None},
        "agent_models": (row.agent_models if row else {}) or {}, "agents": AGENTS, "suggested": SUGGESTED,
        "last_test": {"at": row.last_test_at, **(row.last_test_result or {})} if row and row.last_test_at else None,
        "active_provider": "openai" if e.provider == "openai" and e.api_key and e.text_model else ("simulated" if e.provider == "openai" else e.provider),
        # One-click demo accounts can view but not change AI configuration (enforced in deps.get_auth_user).
        "demo_restricted": demo.is_demo_user(ctx.user),
        "phi_allowed": settings.ai_phi_allowed, "encryption": "dedicated key" if settings.credentials_encryption_key else "derived from SECRET_KEY (development)",
    }


# ---------------------------------------------------------------------------------------------- demo sessions
# One-click demo accounts get the full AI settings workflow, but against THEIR OWN session-scoped configuration
# (app/ai/demo_scope.py): the platform settings, platform key and other sessions are never read or written.


def _demo_token(ctx: TenantContext) -> str | None:
    from app.ai import demo_scope

    return demo_scope.current_token() if demo.is_demo_user(ctx.user) else None


def _demo_row(ctx: TenantContext, token: str, create: bool = False):
    import uuid as _uuid

    from app.ai import demo_scope
    from app.models import DemoAISettings, UserSession

    sid = _uuid.UUID(token.split(":", 1)[1])
    row = demo_scope.load_row(ctx.db, sid)
    if row or not create:
        return row
    sess = ctx.db.get(UserSession, sid)
    stale = ctx.db.get(DemoAISettings, sid)  # expired row for this session: replace it
    if stale:
        ctx.db.delete(stale)
        ctx.db.flush()
    row = DemoAISettings(session_id=sid, user_id=ctx.user.id, provider="simulated", agent_models={}, agent_overrides={},
                         created_at=now(), updated_at=now(), expires_at=demo_scope.expiry(sess.expires_at if sess else None))
    ctx.db.add(row)
    ctx.db.flush()
    return row


def _demo_out(ctx: TenantContext, token: str) -> dict:
    from app.ai import demo_scope

    row = _demo_row(ctx, token)
    eff = demo_scope.current() or (demo_scope.from_row(row) if row else None)
    live = bool(eff and eff.provider == "openai" and eff.api_key and eff.text_model)
    return {
        "provider": row.provider if row else ("openai" if eff and eff.provider == "openai" else "simulated"), "source": "demo-session",
        "key": {"configured": bool(row and row.api_key_encrypted), "hint": None, "updated_at": row.updated_at if row else None},
        "models": {"text": (row.text_model if row else None) or (eff.text_model if eff else None) or None,
                   "vision": (row.vision_model if row else None) or None, "transcription": (row.transcription_model if row else None) or None,
                   "realtime": (row.realtime_model if row else None) or None},
        "agent_models": (row.agent_models if row else {}) or {}, "agents": AGENTS, "suggested": SUGGESTED,
        "last_test": row.last_test if row else None, "active_provider": "openai" if live else "simulated",
        "phi_allowed": settings.ai_phi_allowed, "encryption": "dedicated key" if settings.credentials_encryption_key else "derived from SECRET_KEY (development)",
        "demo_restricted": False,
        "demo_scope": {"isolated": True, "expires_at": row.expires_at if row else None, "shared_demo_key": bool(settings.demo_openai_api_key),
                       "provider_source": (eff.source if eff else "demo") if live else "simulated",
                       "owner_managed": bool(eff and eff.source == "owner-demo"), "reason": eff.reason if eff and not live else None,
                       "allowed_models": (eff.allowed_models if eff else None), "usage": demo_scope.usage(token)},
    }


def _validate_key(key: str) -> None:
    """Authenticate a visitor-entered key against OpenAI (models.list) before storing it."""
    import openai
    from fastapi import HTTPException

    from app.ai import demo_scope
    from app.ai.provider import AIError

    try:
        with demo_scope.guard():
            openai.OpenAI(api_key=key, timeout=15, max_retries=0).models.list()
    except openai.AuthenticationError:
        raise bad_request("OpenAI rejected this API key. Check that it is active and copied in full.") from None
    except AIError as e:
        raise HTTPException(429, str(e)) from None
    except openai.APIError as e:
        raise bad_request(f"Could not validate the key with OpenAI ({type(e).__name__}).") from None


@router.get("/admin/ai-settings")
def get_ai_settings(ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
    token = _demo_token(ctx)
    if token:
        return _demo_out(ctx, token)
    return _out(ctx, _row(ctx))


class SettingsIn(BaseModel):
    provider: Literal["simulated", "openai"] = "openai"
    api_key: str | None = Field(default=None, min_length=20, max_length=300)  # write-only; omit to keep the current key
    text_model: str | None = None
    vision_model: str | None = None
    transcription_model: str | None = None
    realtime_model: str | None = None
    agent_models: dict[str, str] = {}

    @field_validator("text_model", "vision_model", "transcription_model", "realtime_model")
    @classmethod
    def _model(cls, v):
        if v in (None, ""):
            return None
        if not MODEL_RE.match(v):
            raise ValueError("Model ids contain only letters, digits, '.', '-', '_' or ':'")
        return v

    @field_validator("agent_models")
    @classmethod
    def _agents(cls, v):
        bad = [k for k in v if k not in AGENTS] + [m for m in v.values() if m and not MODEL_RE.match(m)]
        if bad:
            raise ValueError(f"Invalid agent model entries: {bad[:3]}")
        return {k: m for k, m in v.items() if m}

    @field_validator("api_key")
    @classmethod
    def _key(cls, v):
        if v is not None and (any(c.isspace() for c in v) or not v.isprintable()):
            raise ValueError("The API key contains spaces or invalid characters")
        return v

    @model_validator(mode="after")
    def _families(self):
        _check_families(text=self.text_model, vision=self.vision_model, transcription=self.transcription_model,
                        realtime=self.realtime_model, agents=self.agent_models)
        return self


def _check_families(*, agents: dict | None = None, **caps) -> None:
    """Reject a model in the wrong slot (e.g. a realtime model as the transcription model) with a plain explanation."""
    from app.ai.openai_provider import model_family_problem

    problems = [p for cap, m in caps.items() if (p := model_family_problem(cap, m))]
    problems += [p for m in (agents or {}).values() if (p := model_family_problem("agent", m))]
    if problems:
        raise ValueError(" ".join(problems[:3]))


@router.put("/admin/ai-settings")
def put_ai_settings(body: SettingsIn, ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
    token = _demo_token(ctx)
    if token:
        row = _demo_row(ctx, token, create=True)
        changed = []
        if body.api_key:
            _validate_key(body.api_key)
            row.api_key_encrypted, row.last_test = encrypt(body.api_key), None
            changed.append("api_key")
        for f in ("provider", "text_model", "vision_model", "transcription_model", "realtime_model", "agent_models"):
            v = getattr(body, f)
            if getattr(row, f) != v:
                setattr(row, f, v)
                changed.append(f)
        if row.provider == "openai" and not row.text_model:
            raise bad_request("Choose a text model for OpenAI")
        if row.provider == "openai" and not row.api_key_encrypted and not settings.demo_openai_api_key:
            raise bad_request("Enter an OpenAI API key for this demo session")
        row.updated_at = now()
        ctx.audit("ai.demo_settings_updated", resource_type="demo_ai_settings", details={"changed": changed})  # never the key
        ctx.db.commit()
        from app.ai import demo_scope

        demo_scope.set_for_request(token, demo_scope.from_row(row))
        return _demo_out(ctx, token)
    row = _row(ctx)
    if not row:
        row = AIProviderSettings(scope="platform")
        ctx.db.add(row)
    changed = []
    if body.api_key:
        row.api_key_encrypted, row.api_key_hint, row.key_updated_at, row.key_updated_by_id = encrypt(body.api_key), mask(body.api_key), now(), ctx.user.id
        row.last_test_at, row.last_test_result = None, {}
        changed.append("api_key")
    for f in ("provider", "text_model", "vision_model", "transcription_model", "realtime_model", "agent_models"):
        v = getattr(body, f)
        if getattr(row, f) != v:
            setattr(row, f, v)
            changed.append(f)
    if row.provider == "openai" and not row.text_model:
        raise bad_request("Choose a text model for OpenAI")
    row.updated_by_id = ctx.user.id
    ctx.audit("ai.settings_updated", resource_type="ai_settings", details={"changed": changed})  # never the key itself
    ctx.db.commit()
    invalidate()
    return _out(ctx, row)


@router.delete("/admin/ai-settings/key")
def delete_key(ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
    token = _demo_token(ctx)
    if token:
        row = _demo_row(ctx, token)
        if row and row.api_key_encrypted:
            row.api_key_encrypted, row.last_test, row.updated_at = None, None, now()
            ctx.audit("ai.demo_key_removed", resource_type="demo_ai_settings")
            ctx.db.commit()
            from app.ai import demo_scope

            demo_scope.set_for_request(token, demo_scope.from_row(row))
        return _demo_out(ctx, token)
    row = _row(ctx)
    if row and row.api_key_encrypted:
        row.api_key_encrypted = row.api_key_hint = None
        row.key_updated_at, row.key_updated_by_id = now(), ctx.user.id
        ctx.audit("ai.key_removed", resource_type="ai_settings")
        ctx.db.commit()
        invalidate()
    return _out(ctx, row)


@router.post("/admin/ai-settings/test")
def test_connection(ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
    from app.ai.openai_provider import OpenAICore, available

    token = _demo_token(ctx)
    if not token:
        invalidate()
    if not available():
        result = {"ok": False, "error": "OpenAI is not active: choose OpenAI, enter an API key and a text model."}
    else:
        result = OpenAICore().health(probe=True)
    if token:
        row = _demo_row(ctx, token)
        if row:
            row.last_test = {**result, "at": now().isoformat()}
        ctx.audit("ai.demo_connection_tested", resource_type="demo_ai_settings", details={"ok": result.get("ok")})
        ctx.db.commit()
        return result
    row = _row(ctx)
    if row:
        row.last_test_at, row.last_test_result = now(), result
    ctx.audit("ai.connection_tested", resource_type="ai_settings", details={"ok": result.get("ok")})
    ctx.db.commit()
    return result


# ---------------------------------------------------------------------------------------------- platform owner
# Real Super Admins only (never one-click demo accounts — also blocked by app.core.demo for /admin/ writes).
# Manages: the owner-managed public demo AI provider (scope="demo"), its limits/budget, and the platform AI kill switch.

def _require_owner(ctx: TenantContext) -> None:
    from fastapi import HTTPException

    if not ctx.user.is_superadmin or demo.is_demo_user(ctx.user):
        raise HTTPException(403, "Only the platform owner (a real Super Admin account) can manage this.")


def _scoped_row(ctx: TenantContext, scope: str, create: bool = False) -> AIProviderSettings | None:
    row = ctx.db.scalar(select(AIProviderSettings).where(AIProviderSettings.scope == scope))
    if not row and create:
        row = AIProviderSettings(scope=scope, provider="openai", agent_models={}, policy={})
        ctx.db.add(row)
        ctx.db.flush()
    return row


def _owner_out(ctx: TenantContext) -> dict:
    from app.ai import owner_demo, usage

    plat = _row(ctx)
    row = _scoped_row(ctx, "demo")
    policy = owner_demo.merged_policy(row.policy if row else None)
    _, eff = owner_demo.load()
    day, mon = usage.day_key(), usage.month_key()
    g_day, g_mon = usage.read(f"demo:global:day:{day}"), usage.read(f"demo:global:month:{mon}")
    rt = usage.read(f"demo:global:realtime:day:{day}")
    plat_key = bool(plat and plat.api_key_encrypted) or bool(settings.openai_api_key)
    return {
        "platform": {"ai_disabled": bool((plat.policy or {}).get("ai_disabled")) if plat else False, "key_configured": plat_key},
        "demo_mode": demo.enabled(), "operator_disabled": settings.demo_ai_disabled,
        "demo": {**policy, "dedicated_key": {"configured": bool(row and row.api_key_encrypted), "hint": row.api_key_hint if row else None,
                                             "updated_at": row.key_updated_at if row else None},
                 "active": eff is not None, "last_test": {"at": row.last_test_at, **(row.last_test_result or {})} if row and row.last_test_at else None},
        "usage": {"today": {"requests": g_day["requests"], "estimated_cost_usd": round(g_day["cost_usd"], 4),
                            "input_tokens": g_day["input_tokens"], "output_tokens": g_day["output_tokens"], "voice_sessions": rt["requests"]},
                  "month": {"estimated_cost_usd": round(g_mon["cost_usd"], 4), "budget_usd": policy["limits"]["monthly_budget_usd"]},
                  "note": "Estimated from token counts and a price table — not a bill. Also set a spending limit on the OpenAI project."},
        "agents": owner_demo.AGENT_KEYS,
    }


@router.get("/admin/ai-owner")
def owner_status(ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
    _require_owner(ctx)
    return _owner_out(ctx)


class Limits(BaseModel):
    visitor_daily_requests: int = Field(25, ge=0, le=1000)
    global_daily_requests: int = Field(200, ge=0, le=20000)
    monthly_budget_usd: float = Field(10.0, ge=0, le=5000)
    visitor_concurrency: int = Field(2, ge=1, le=10)
    global_concurrency: int = Field(6, ge=1, le=50)
    realtime_enabled: bool = False
    realtime_max_seconds: int = Field(120, ge=30, le=900)
    realtime_daily_sessions: int = Field(20, ge=0, le=1000)


class OwnerDemoIn(BaseModel):
    enabled: bool = False
    key_source: Literal["dedicated", "platform"] = "dedicated"
    api_key: str | None = Field(default=None, min_length=20, max_length=300)  # write-only dedicated demo key
    text_model: str = "gpt-4.1-mini"
    vision_model: str | None = None
    transcription_model: str | None = None
    realtime_model: str | None = None
    allowed_models: list[str] = []
    allowed_agents: list[str] = []
    limits: Limits = Limits()

    @field_validator("text_model", "vision_model", "transcription_model", "realtime_model")
    @classmethod
    def _m(cls, v):
        if v in (None, ""):
            return None
        if not MODEL_RE.match(v):
            raise ValueError("Model ids contain only letters, digits, '.', '-', '_' or ':'")
        return v

    @field_validator("allowed_models")
    @classmethod
    def _am(cls, v):
        bad = [m for m in v if not MODEL_RE.match(m)]
        if bad:
            raise ValueError(f"Invalid model ids: {bad[:3]}")
        return sorted(set(v))

    @field_validator("allowed_agents")
    @classmethod
    def _ag(cls, v):
        bad = [a for a in v if a not in AGENTS]
        if bad:
            raise ValueError(f"Unknown assistants: {bad[:3]}")
        return sorted(set(v))

    @field_validator("api_key")
    @classmethod
    def _key(cls, v):
        if v is not None and (any(c.isspace() for c in v) or not v.isprintable()):
            raise ValueError("The API key contains spaces or invalid characters")
        return v

    @model_validator(mode="after")
    def _families(self):
        _check_families(text=self.text_model, vision=self.vision_model, transcription=self.transcription_model, realtime=self.realtime_model)
        return self


@router.put("/admin/ai-owner/demo")
def owner_demo_update(body: OwnerDemoIn, ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
    from app.ai import owner_demo

    _require_owner(ctx)
    row = _scoped_row(ctx, "demo", create=True)
    changed = []
    if body.api_key:
        _validate_key(body.api_key)
        row.api_key_encrypted, row.api_key_hint, row.key_updated_at, row.key_updated_by_id = encrypt(body.api_key), mask(body.api_key), now(), ctx.user.id
        row.last_test_at, row.last_test_result = None, {}
        changed.append("api_key")
    policy = body.model_dump(exclude={"api_key"})
    policy["vision_model"] = policy["vision_model"] or policy["text_model"]
    policy["transcription_model"] = policy["transcription_model"] or ""
    policy["realtime_model"] = policy["realtime_model"] or ""
    if body.enabled:
        has_key = bool(row.api_key_encrypted) if body.key_source == "dedicated" else bool((_row(ctx) and _row(ctx).api_key_encrypted) or settings.openai_api_key)
        if not has_key:
            raise bad_request("Enter a dedicated demo API key (recommended) or choose the platform key before enabling public demo AI.")
        if policy["limits"]["realtime_enabled"] and not policy["realtime_model"]:
            raise bad_request("Choose a Realtime model before enabling voice for the demo.")
    old = owner_demo.merged_policy(row.policy)
    changed += [k for k in policy if old.get(k) != policy[k]]
    row.policy, row.text_model, row.updated_by_id = policy, policy["text_model"], ctx.user.id
    ctx.audit("ai.owner_demo_updated", resource_type="ai_settings", details={"changed": changed, "enabled": body.enabled})  # never the key
    ctx.db.commit()
    invalidate()
    return _owner_out(ctx)


@router.post("/admin/ai-owner/demo/disable")
def owner_demo_disable(ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
    """Emergency switch: stop all owner-funded demo AI immediately (no redeploy)."""
    _require_owner(ctx)
    row = _scoped_row(ctx, "demo")
    if row:
        row.policy = {**(row.policy or {}), "enabled": False}
        ctx.audit("ai.owner_demo_disabled", resource_type="ai_settings")
        ctx.db.commit()
        invalidate()
    return _owner_out(ctx)


@router.delete("/admin/ai-owner/demo/key")
def owner_demo_delete_key(ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
    _require_owner(ctx)
    row = _scoped_row(ctx, "demo")
    if row and row.api_key_encrypted:
        row.api_key_encrypted = row.api_key_hint = None
        row.key_updated_at, row.key_updated_by_id = now(), ctx.user.id
        if (row.policy or {}).get("key_source", "dedicated") == "dedicated":
            row.policy = {**(row.policy or {}), "enabled": False}
        ctx.audit("ai.owner_demo_key_removed", resource_type="ai_settings")
        ctx.db.commit()
        invalidate()
    return _owner_out(ctx)


@router.post("/admin/ai-owner/demo/test")
def owner_demo_test(ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
    """Owner's own test of the demo provider: models.list + one tiny real call per configured capability."""
    from app.ai import owner_demo
    from app.ai.config import EffectiveAI, platform_effective
    from app.ai.openai_provider import OpenAICore
    from app.core.crypto import decrypt

    _require_owner(ctx)
    row = _scoped_row(ctx, "demo")
    policy = owner_demo.merged_policy(row.policy if row else None)
    key = None
    if policy["key_source"] == "platform":
        key = platform_effective().api_key
    elif row and row.api_key_encrypted:
        key = decrypt(row.api_key_encrypted)
    if not key:
        result = {"ok": False, "error": "No API key for the demo provider yet."}
    else:
        cfg = EffectiveAI(provider="openai", api_key=key, source="owner-demo", text_model=policy["text_model"],
                          vision_model=policy["vision_model"] or policy["text_model"], transcription_model=policy["transcription_model"] or "",
                          realtime_model=policy["realtime_model"] or "")
        result = OpenAICore(cfg=cfg).health(probe=True)
    if row:
        row.last_test_at, row.last_test_result = now(), result
    ctx.audit("ai.owner_demo_tested", resource_type="ai_settings", details={"ok": result.get("ok")})
    ctx.db.commit()
    return result


class PlatformSwitchIn(BaseModel):
    ai_disabled: bool


@router.put("/admin/ai-owner/platform")
def owner_platform_switch(body: PlatformSwitchIn, ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
    """Emergency switch for ALL platform AI: when on, every AI feature returns its labelled simulation."""
    _require_owner(ctx)
    row = _scoped_row(ctx, "platform", create=True)
    row.policy = {**(row.policy or {}), "ai_disabled": body.ai_disabled}
    ctx.audit("ai.platform_switch", resource_type="ai_settings", details={"ai_disabled": body.ai_disabled})
    ctx.db.commit()
    invalidate()
    return _owner_out(ctx)
