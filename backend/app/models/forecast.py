"""Forecast store (C4). Predictions are kept so they can be backtested against what actually happened.
All models here are simple statistical baselines, labeled unvalidated and used in shadow mode only."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScoped, UUIDPk


class Prediction(UUIDPk, OrgScoped, Base):
    __tablename__ = "predictions"
    target: Mapped[str] = mapped_column(String(40))  # census | discharges | ed_arrivals | no_shows | nurses_needed
    target_date: Mapped[date] = mapped_column(Date)
    model: Mapped[str] = mapped_column(String(40))
    value: Mapped[float] = mapped_column(Float)
    lower: Mapped[float | None] = mapped_column(Float)
    upper: Mapped[float | None] = mapped_column(Float)
    actual: Mapped[float | None] = mapped_column(Float)
    generated_on: Mapped[date] = mapped_column(Date)
    inputs: Mapped[dict] = mapped_column(JSONB, default=dict)
    facility_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("organization_id", "target", "target_date", "generated_on", "model"),
                      Index("ix_predictions_target", "organization_id", "target", "target_date"))


class AIEvalRun(UUIDPk, OrgScoped, Base):
    """One execution of an AI evaluation suite (C7) over synthetic labeled samples. Results are kept for trend review."""
    __tablename__ = "ai_eval_runs"
    suite: Mapped[str] = mapped_column(String(60), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(80))
    samples: Mapped[int] = mapped_column(default=0)
    score: Mapped[float] = mapped_column(Float)  # 0..1
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    cases: Mapped[list] = mapped_column(JSONB, default=list)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
