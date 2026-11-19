"""Effective AI configuration: Super Admin settings (DB, key encrypted) override environment variables.
Cached in-process for a few seconds; `invalidate()` after an update."""

import logging
import time
from dataclasses import dataclass, field

from app.core.config import settings

log = logging.getLogger("undeclared.ai.config")
_CACHE: dict = {"at": 0.0, "value": None}
TTL = 15.0


@dataclass
class EffectiveAI:
    provider: str
    api_key: str | None = field(repr=False, default=None)
    key_hint: str | None = None
    source: str = "env"  # env | ui
    text_model: str = ""
    vision_model: str = ""
    transcription_model: str = ""
    realtime_model: str = ""
    agent_models: dict = field(default_factory=dict)

    def model_for(self, agent_key: str | None) -> str:
        return (self.agent_models or {}).get(agent_key or "", "") or self.text_model


def _load() -> EffectiveAI:
    eff = EffectiveAI(provider=settings.ai_provider, api_key=settings.openai_api_key,
                      key_hint=f"…{settings.openai_api_key[-4:]}" if settings.openai_api_key else None, source="env",
                      text_model=settings.ai_text_model, vision_model=settings.ai_vision_model or settings.ai_text_model,
                      transcription_model=settings.ai_transcription_model, realtime_model="")
    try:
        from sqlalchemy import select

        from app.core.crypto import decrypt
        from app.core.db import SessionLocal
        from app.models import AIProviderSettings

        db = SessionLocal()
        try:
            row = db.scalar(select(AIProviderSettings).where(AIProviderSettings.scope == "platform"))
        finally:
            db.close()
        if row:
            eff.provider, eff.source = row.provider, "ui"
            if row.api_key_encrypted:
                try:
                    eff.api_key, eff.key_hint = decrypt(row.api_key_encrypted), row.api_key_hint
                except ValueError:
                    log.error("stored AI key cannot be decrypted; falling back to simulation")
                    eff.api_key, eff.key_hint = None, None
            eff.text_model = row.text_model or eff.text_model
            eff.vision_model = row.vision_model or eff.text_model
            eff.transcription_model = row.transcription_model or eff.transcription_model
            eff.realtime_model = row.realtime_model or ""
            eff.agent_models = row.agent_models or {}
    except Exception:  # noqa: BLE001 — table missing during migrations etc.
        log.debug("AI settings unavailable; using environment")
    return eff


def effective() -> EffectiveAI:
    now = time.monotonic()
    if _CACHE["value"] is None or now - _CACHE["at"] > TTL:
        _CACHE["value"], _CACHE["at"] = _load(), now
    return _CACHE["value"]


def invalidate() -> None:
    _CACHE["value"] = None


def active_provider() -> str:
    """The provider actually used: 'openai' only when a key and text model are configured, else the configured one."""
    e = effective()
    if e.provider == "openai" and not (e.api_key and e.text_model):
        return "simulated"
    return e.provider
