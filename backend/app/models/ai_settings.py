"""Platform AI provider settings managed by Super Admins in the UI. The API key is stored encrypted (app.core.crypto)
and never returned. Environment variables remain a fallback when no row exists."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Timestamps, UUIDPk, fk


class AIProviderSettings(UUIDPk, Timestamps, Base):
    __tablename__ = "ai_provider_settings"
    scope: Mapped[str] = mapped_column(String(20), unique=True, default="platform")
    provider: Mapped[str] = mapped_column(String(20), default="openai")  # simulated | openai | anthropic
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    api_key_hint: Mapped[str | None] = mapped_column(String(12))
    key_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    key_updated_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    text_model: Mapped[str | None] = mapped_column(String(80))
    vision_model: Mapped[str | None] = mapped_column(String(80))
    transcription_model: Mapped[str | None] = mapped_column(String(80))
    realtime_model: Mapped[str | None] = mapped_column(String(80))
    agent_models: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"agent_key": "model-id"}
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_result: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"ok": bool, "models": {"text": true, ...}, "error": ...}
    updated_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    # scope="platform": {"ai_disabled": bool}. scope="demo" (owner-managed public demo AI): see app/ai/owner_demo.py.
    policy: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")


class AIUsageCounter(Base):
    """Durable AI usage ledger (survives restarts). Keys like 'demo:global:day:2026-11-23', 'demo:visitor:<sess>:day:…',
    'demo:global:month:2026-11', 'auto:day:…'. Incremented atomically with a limit check (app/ai/usage.py)."""
    __tablename__ = "ai_usage_counters"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(14, 6), default=0)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DemoAISettings(Base):
    """AI configuration owned by ONE demo sign-in session (DEMO_MODE only). Lets a demo visitor try the real AI settings
    workflow — their own key, models, per-agent models and agent overrides — without touching the platform settings or
    the organization's agent configuration. Expires with the session (max DEMO_AI_TTL_HOURS) and is deleted by cleanup."""
    __tablename__ = "demo_ai_settings"
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_sessions.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20), default="simulated")
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    text_model: Mapped[str | None] = mapped_column(String(80))
    vision_model: Mapped[str | None] = mapped_column(String(80))
    transcription_model: Mapped[str | None] = mapped_column(String(80))
    realtime_model: Mapped[str | None] = mapped_column(String(80))
    agent_models: Mapped[dict] = mapped_column(JSONB, default=dict)
    agent_overrides: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_test: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
