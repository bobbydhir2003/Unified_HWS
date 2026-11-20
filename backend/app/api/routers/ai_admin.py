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
        "phi_allowed": settings.ai_phi_allowed, "encryption": "dedicated key" if settings.credentials_encryption_key else "derived from SECRET_KEY (development)",
    }


@router.get("/admin/ai-settings")
def get_ai_settings(ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
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

    invalidate()
    if not available():
        result = {"ok": False, "error": "OpenAI is not active: choose OpenAI, enter an API key and a text model."}
    else:
        result = OpenAICore().health()
    row = _row(ctx)
    if row:
        row.last_test_at, row.last_test_result = now(), result
    ctx.audit("ai.connection_tested", resource_type="ai_settings", details={"ok": result.get("ok")})
    ctx.db.commit()
    return result
