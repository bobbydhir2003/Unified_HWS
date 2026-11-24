"""Clinical terminology (shared reference data, not tenant data) and order sets (tenant data).

Code systems are loaded from legally available releases only (ICD-10-CM: CMS/CDC, public domain). Every concept keeps
the release it came from; codes dropped by a newer release are marked retired, never deleted. Licensed systems (CPT,
SNOMED CT, commercial drug knowledge bases) are listed in app/services/terminology.py as not loaded.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, UUIDPk, fk


class TerminologyRelease(UUIDPk, Base):
    __tablename__ = "terminology_releases"
    system: Mapped[str] = mapped_column(String(30))           # e.g. ICD-10-CM
    version: Mapped[str] = mapped_column(String(30))          # e.g. FY2026
    effective_date: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(300))
    license_note: Mapped[str] = mapped_column(String(300))
    concept_count: Mapped[int] = mapped_column(Integer, default=0)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("system", "version"),)


class TerminologyConcept(UUIDPk, Base):
    __tablename__ = "terminology_concepts"
    system: Mapped[str] = mapped_column(String(30))
    code: Mapped[str] = mapped_column(String(20))
    display: Mapped[str] = mapped_column(String(400))
    version: Mapped[str] = mapped_column(String(30))          # release that last contained the code
    status: Mapped[str] = mapped_column(String(10), default="active")  # active | retired

    __table_args__ = (
        UniqueConstraint("system", "code"),
        CheckConstraint("status in ('active','retired')", name="status"),
        Index("ix_terminology_display", "system", func.lower(display)),
    )


class OrderSet(UUIDPk, OrgScoped, Base):
    """A versioned group of orders. Only `published` versions can be applied; applying creates DRAFT orders that a
    clinician reviews and signs one by one (no order is signed by applying a set)."""

    __tablename__ = "order_sets"
    key: Mapped[str] = mapped_column(String(60))              # stable identity across versions
    version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft | published | retired
    is_demonstration: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    published_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    items: Mapped[list["OrderSetItem"]] = relationship(order_by="OrderSetItem.position", lazy="selectin", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "key", "version"),
        CheckConstraint("status in ('draft','published','retired')", name="status"),
    )


class OrderSetItem(UUIDPk, OrgScoped, Base):
    __tablename__ = "order_set_items"
    order_set_id: Mapped[uuid.UUID] = fk("order_sets.id")
    position: Mapped[int] = mapped_column(Integer, default=0)
    order_type: Mapped[str] = mapped_column(String(20))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    priority: Mapped[str] = mapped_column(String(10), default="routine")
    default_selected: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(String(300))
