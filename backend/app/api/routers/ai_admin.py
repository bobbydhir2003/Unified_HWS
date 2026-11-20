"""Super Admin → AI Settings. The API key is write-only: accepted over HTTPS, encrypted at rest, never returned
(only a masked hint). Model identifiers are configuration; 'Test connection' verifies them against the provider's
model list for this account instead of assuming they exist."""

import re
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
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
                       "usage": demo_scope.usage(token)},
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
        result = OpenAICore().health()
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
