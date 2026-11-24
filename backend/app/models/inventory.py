"""Pharmacy & inventory (Milestone B6/B9): items, lots with expiry, per-location balances, append-only movement ledger,
suppliers, purchase requests, pharmacist order verification.

DB invariants: balances are never negative (CHECK), movement quantities are positive (CHECK), one balance row per
(location, lot) (UNIQUE), the ledger is append-only (trigger). Business rules (no dispensing expired lots, two-person
approval for waste/negative adjustments) live in app/services/inventory.py.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk


class Supplier(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "suppliers"
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    lead_time_days: Mapped[int] = mapped_column(Integer, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("organization_id", "name"),)


class InventoryItem(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "inventory_items"
    kind: Mapped[str] = mapped_column(String(12))  # medication | supply | equipment
    name: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(40))
    ndc: Mapped[str | None] = mapped_column(String(20))
    category: Mapped[str | None] = mapped_column(String(60))
    form: Mapped[str | None] = mapped_column(String(40))
    strength: Mapped[str | None] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(20), default="each")
    is_controlled: Mapped[bool] = mapped_column(Boolean, default=False)
    reorder_point: Mapped[int] = mapped_column(Integer, default=0)
    reorder_qty: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    preferred_supplier_id: Mapped[uuid.UUID | None] = fk("suppliers.id", nullable=True, ondelete="SET NULL", index=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("organization_id", "sku"),
                      CheckConstraint("kind in ('medication','supply','equipment')", name="kind"),
                      CheckConstraint("reorder_point >= 0 and reorder_qty >= 0", name="reorder"))


class InventoryLot(UUIDPk, OrgScoped, Base):
    __tablename__ = "inventory_lots"
    item_id: Mapped[uuid.UUID] = fk("inventory_items.id")
    lot_number: Mapped[str] = mapped_column(String(40))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    item: Mapped[InventoryItem] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("item_id", "lot_number"),)


class StockBalance(UUIDPk, OrgScoped, Base):
    __tablename__ = "stock_balances"
    location_id: Mapped[uuid.UUID] = fk("locations.id")
    lot_id: Mapped[uuid.UUID] = fk("inventory_lots.id")
    item_id: Mapped[uuid.UUID] = fk("inventory_items.id")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("location_id", "lot_id"), CheckConstraint("quantity >= 0", name="non_negative"))


MOVEMENT_KINDS = ("receive", "transfer_out", "transfer_in", "dispense", "waste", "adjust_up", "adjust_down", "return")


class StockMovement(UUIDPk, OrgScoped, Base):
    """Append-only ledger. Balances are derived from it and updated in the same transaction."""

    __tablename__ = "stock_movements"
    item_id: Mapped[uuid.UUID] = fk("inventory_items.id")
    lot_id: Mapped[uuid.UUID] = fk("inventory_lots.id")
    location_id: Mapped[uuid.UUID] = fk("locations.id")
    kind: Mapped[str] = mapped_column(String(15))
    quantity: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(300))
    reference_type: Mapped[str | None] = mapped_column(String(30))  # purchase_request | order | transfer | approval
    reference_id: Mapped[str | None] = mapped_column(String(64))
    patient_id: Mapped[uuid.UUID | None] = fk("patients.id", nullable=True, ondelete="SET NULL")
    actor_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    approved_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive"),
        CheckConstraint("kind in (" + ",".join(f"'{k}'" for k in MOVEMENT_KINDS) + ")", name="kind"),
        Index("ix_movements_item_time", "item_id", "at"),
    )


class PurchaseRequest(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "purchase_requests"
    number: Mapped[int] = mapped_column(BigInteger, server_default=text("nextval('purchase_request_seq')"))
    facility_id: Mapped[uuid.UUID] = fk("clinics.id")
    item_id: Mapped[uuid.UUID] = fk("inventory_items.id")
    supplier_id: Mapped[uuid.UUID | None] = fk("suppliers.id", nullable=True, ondelete="SET NULL", index=False)
    deliver_to_location_id: Mapped[uuid.UUID | None] = fk("locations.id", nullable=True, ondelete="SET NULL", index=False)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="submitted")
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual | watchdog
    reason: Mapped[str | None] = mapped_column(String(500))
    recommendation: Mapped[dict | None] = mapped_column(JSONB)
    case_id: Mapped[uuid.UUID | None] = fk("cases.id", nullable=True, ondelete="SET NULL", index=False)
    requested_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    decided_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(500))
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    po_reference: Mapped[str | None] = mapped_column(String(40))
    received_quantity: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item: Mapped[InventoryItem] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint("status in ('submitted','approved','rejected','ordered','received','cancelled')", name="status"),
        Index("ix_pr_org_status", "organization_id", "status"),
    )


class MedicationVerification(UUIDPk, OrgScoped, Base):
    """Pharmacist decision on a signed inpatient medication order. History is kept: an order can be sent back for
    clarification and verified later, so there may be several rows per order (latest wins, see services/medication.py)."""

    __tablename__ = "medication_verifications"
    order_id: Mapped[uuid.UUID] = fk("orders.id")
    patient_id: Mapped[uuid.UUID] = fk("patients.id")
    status: Mapped[str] = mapped_column(String(12))  # verified | rejected | clarify
    note: Mapped[str | None] = mapped_column(Text)
    pharmacist_id: Mapped[uuid.UUID] = fk("users.id", index=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # True when interaction screening was unavailable and the pharmacist confirmed a manual interaction review.
    manual_interaction_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    __table_args__ = (CheckConstraint("status in ('verified','rejected','clarify')", name="status"),)


class StockPar(UUIDPk, OrgScoped, Base):
    """Department/location par level: the quantity a location should hold (restocked by transfer from the main store)."""

    __tablename__ = "stock_pars"
    location_id: Mapped[uuid.UUID] = fk("locations.id")
    item_id: Mapped[uuid.UUID] = fk("inventory_items.id")
    par_level: Mapped[int] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("location_id", "item_id"), CheckConstraint("par_level >= 0", name="par"))


class Equipment(UUIDPk, Timestamps, OrgScoped, Base):
    __tablename__ = "equipment"
    facility_id: Mapped[uuid.UUID] = fk("clinics.id")
    location_id: Mapped[uuid.UUID | None] = fk("locations.id", nullable=True, ondelete="SET NULL", index=False)
    name: Mapped[str] = mapped_column(String(120))
    asset_tag: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(40), default="clinical")
    manufacturer: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    serial_number: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(15), default="in_service")
    maintenance_interval_days: Mapped[int] = mapped_column(Integer, default=180)
    last_maintenance_on: Mapped[date | None] = mapped_column(Date)
    next_maintenance_due: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("organization_id", "asset_tag"),
                      CheckConstraint("status in ('in_service','out_of_service','maintenance','retired')", name="status"),
                      CheckConstraint("maintenance_interval_days between 1 and 3650", name="interval"))


class MaintenanceLog(UUIDPk, OrgScoped, Base):
    """Append-only equipment service history."""

    __tablename__ = "maintenance_logs"
    equipment_id: Mapped[uuid.UUID] = fk("equipment.id")
    kind: Mapped[str] = mapped_column(String(15))  # preventive | repair | inspection | calibration
    result: Mapped[str] = mapped_column(String(15), default="passed")  # passed | failed | repaired
    notes: Mapped[str | None] = mapped_column(Text)
    performed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL", index=False)
    performed_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
