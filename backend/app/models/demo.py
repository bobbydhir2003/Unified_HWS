"""Private demo hospitals (DEMO_MODE only). See app/demo/sandbox.py.

A row tracks one synthetic hospital organization through its life: building → ready (in the pool) → leased (one visitor)
→ releasing → purging → purged. `organization_id` deliberately has NO foreign key: the row must outlive the organization's
deletion so the append-only database triggers can recognise an authorised purge, and so the history stays auditable.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPk

SANDBOX_STATUSES = ("building", "ready", "leased", "releasing", "purging", "purged", "failed")


class DemoSandbox(UUIDPk, Base):
    __tablename__ = "demo_sandboxes"
    __table_args__ = (CheckConstraint(f"status IN {SANDBOX_STATUSES}", name="status"),)

    tag: Mapped[str] = mapped_column(String(12), unique=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
    status: Mapped[str] = mapped_column(String(12), index=True, default="building")
    lease_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)
    root_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # keys the visitor's demo AI settings & limits
    visitor_hash: Mapped[str | None] = mapped_column(String(64), index=True)  # salted hash of the client IP (abuse limits only)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_reason: Mapped[str | None] = mapped_column(String(20))
    build_seconds: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
