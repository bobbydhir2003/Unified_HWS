"""Platform AI provider settings managed by Super Admins in the UI. The API key is stored encrypted (app.core.crypto)
and never returned. Environment variables remain a fallback when no row exists."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
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
