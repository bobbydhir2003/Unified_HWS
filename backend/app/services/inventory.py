"""Inventory service: every quantity change is a ledger movement + balance update in one transaction.

Rules: no negative stock (DB CHECK + row lock), no dispensing of expired lots, waste and negative adjustments need a
second person's approval (approval gate), receiving updates the purchase request. Forecasting is deliberately simple
(28-day moving average of consumption) and labeled as such.
"""

import math
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import now
from app.engine import approvals as AP
from app.engine.events import emit
from app.models import (
    InventoryItem,
    InventoryLot,
    Location,
    PurchaseRequest,
    StockBalance,
    StockMovement,
    Supplier,
)
from app.services import audit
from app.services.realtime import publish

CONSUMPTION = ("dispense", "waste")


class InventoryError(ValueError):
    pass


def _balance(db: Session, org_id, location_id, lot: InventoryLot, *, lock=True) -> StockBalance:
    q = select(StockBalance).where(StockBalance.location_id == location_id, StockBalance.lot_id == lot.id)
    b = db.scalar(q.with_for_update() if lock else q)
    if b is None:
        b = StockBalance(organization_id=org_id, location_id=location_id, lot_id=lot.id, item_id=lot.item_id, quantity=0)
        db.add(b)
        db.flush()
    return b


def _move(db: Session, *, lot: InventoryLot, location_id, kind: str, qty: int, actor_id, reason=None, ref_type=None, ref_id=None,
          patient_id=None, approved_by_id=None) -> StockMovement:
    if qty <= 0:
        raise InventoryError("Quantity must be positive")
    b = _balance(db, lot.organization_id, location_id, lot)
    delta = qty if kind in ("receive", "transfer_in", "adjust_up", "return") else -qty
    if b.quantity + delta < 0:
        raise InventoryError(f"Only {b.quantity} on hand for lot {lot.lot_number} at this location")
    b.quantity += delta
    m = StockMovement(organization_id=lot.organization_id, item_id=lot.item_id, lot_id=lot.id, location_id=location_id, kind=kind, quantity=qty,
                      balance_after=b.quantity, reason=reason, reference_type=ref_type, reference_id=str(ref_id) if ref_id else None,
                      patient_id=patient_id, actor_id=actor_id, approved_by_id=approved_by_id, at=now())
    db.add(m)
    try:
        db.flush()
    except IntegrityError:
        raise InventoryError("Stock can't go negative") from None
    publish(db, lot.organization_id, "inventory", item_id=lot.item_id)
    return m


def get_or_create_lot(db: Session, item: InventoryItem, lot_number: str, expiry: date | None) -> InventoryLot:
    lot = db.scalar(select(InventoryLot).where(InventoryLot.item_id == item.id, InventoryLot.lot_number == lot_number))
    if lot:
        if expiry and lot.expiry_date and lot.expiry_date != expiry:
            raise InventoryError(f"Lot {lot_number} already exists with expiry {lot.expiry_date}")
        return lot
    lot = InventoryLot(organization_id=item.organization_id, item_id=item.id, lot_number=lot_number, expiry_date=expiry)
    db.add(lot)
    db.flush()
    return lot


def receive(db: Session, item: InventoryItem, *, location: Location, lot_number: str, expiry: date | None, qty: int, actor_id,
            purchase_request: PurchaseRequest | None = None) -> StockMovement:
    if item.kind == "medication" and not expiry:
        raise InventoryError("Medications must be received with an expiry date")
    if expiry and expiry < date.today():
        raise InventoryError("Can't receive an already expired lot")
    lot = get_or_create_lot(db, item, lot_number, expiry)
    m = _move(db, lot=lot, location_id=location.id, kind="receive", qty=qty, actor_id=actor_id,
              ref_type="purchase_request" if purchase_request else None, ref_id=purchase_request.id if purchase_request else None)
    if purchase_request:
        purchase_request.received_quantity += qty
        if purchase_request.received_quantity >= purchase_request.quantity:
            purchase_request.status, purchase_request.received_at = "received", now()
    emit(db, item.organization_id, "inventory.received", {"subject_type": "inventory_item", "subject_id": item.id, "qty": qty}, actor_id=actor_id)
    return m


def transfer(db: Session, lot: InventoryLot, *, src: Location, dst: Location, qty: int, actor_id, reason: str | None) -> None:
    if src.id == dst.id:
        raise InventoryError("Choose a different destination")
    ref = uuid.uuid4()
    _move(db, lot=lot, location_id=src.id, kind="transfer_out", qty=qty, actor_id=actor_id, reason=reason, ref_type="transfer", ref_id=ref)
    _move(db, lot=lot, location_id=dst.id, kind="transfer_in", qty=qty, actor_id=actor_id, reason=reason, ref_type="transfer", ref_id=ref)


def dispense(db: Session, lot: InventoryLot, *, location: Location, qty: int, actor_id, patient_id=None, order_id=None) -> StockMovement:
    if lot.expiry_date and lot.expiry_date < date.today():
        raise InventoryError(f"Lot {lot.lot_number} expired on {lot.expiry_date:%b %d, %Y} and can't be dispensed")
    m = _move(db, lot=lot, location_id=location.id, kind="dispense", qty=qty, actor_id=actor_id, patient_id=patient_id,
              ref_type="order" if order_id else None, ref_id=order_id)
    audit.record(db, "inventory.dispensed", org_id=lot.organization_id, actor_id=actor_id, resource_type="inventory_lot", resource_id=lot.id,
                 patient_id=patient_id, details={"qty": qty, "controlled": lot.item.is_controlled})
    return m


def adjust_up(db: Session, lot: InventoryLot, *, location: Location, qty: int, actor_id, reason: str) -> StockMovement:
    if not reason or len(reason.strip()) < 5:
        raise InventoryError("Explain the adjustment")
    return _move(db, lot=lot, location_id=location.id, kind="adjust_up", qty=qty, actor_id=actor_id, reason=reason)


def request_removal(db: Session, lot: InventoryLot, *, location: Location, qty: int, kind: str, reason: str, actor_id, case=None):
    """Waste / negative adjustment: two-person rule via the approval gate (the requester can't approve)."""
    if kind not in ("waste", "adjust_down"):
        raise InventoryError("Unknown removal type")
    if not reason or len(reason.strip()) < 5:
        raise InventoryError("Explain why the stock is being removed")
    bal = _balance(db, lot.organization_id, location.id, lot, lock=False).quantity
    if qty > bal:
        raise InventoryError(f"Only {bal} on hand")
    title = f"{'Waste' if kind == 'waste' else 'Adjust down'} {qty} × {lot.item.name} (lot {lot.lot_number}) at {location.name}"
    return AP.request_approval(db, lot.organization_id, kind="inventory.removal", title=title, summary=reason,
                               payload={"lot_id": str(lot.id), "location_id": str(location.id), "qty": qty, "kind": kind, "reason": reason},
                               required_permission="pharmacy:verify" if lot.item.kind == "medication" else "procurement:approve",
                               case=case, facility_id=location.facility_id, requested_by_user_id=actor_id)


@AP.executor("inventory.removal")
def _exec_removal(db: Session, req, approver_id) -> dict:
    p = req.payload
    lot = db.get(InventoryLot, uuid.UUID(p["lot_id"]))
    m = _move(db, lot=lot, location_id=uuid.UUID(p["location_id"]), kind=p["kind"], qty=int(p["qty"]), actor_id=req.requested_by_user_id,
              approved_by_id=approver_id, reason=p["reason"], ref_type="approval", ref_id=req.id)
    return {"movement_id": str(m.id), "balance_after": m.balance_after}


# ---------- Reporting / forecasting ----------

def on_hand(db: Session, item_id, facility_id=None) -> int:
    q = select(func.coalesce(func.sum(StockBalance.quantity), 0)).where(StockBalance.item_id == item_id)
    if facility_id:
        q = q.join(Location, Location.id == StockBalance.location_id).where(Location.facility_id == facility_id)
    return int(db.scalar(q) or 0)


def avg_daily_use(db: Session, item_id, days: int = 28) -> float:
    total = db.scalar(select(func.coalesce(func.sum(StockMovement.quantity), 0)).where(
        StockMovement.item_id == item_id, StockMovement.kind.in_(CONSUMPTION), StockMovement.at > now() - timedelta(days=days)))
    return float(total or 0) / days


def recommend_reorder(db: Session, item: InventoryItem, *, horizon_days: int = 14) -> dict:
    """Deterministic: cover lead time + horizon at the 28-day average daily use, at least the configured reorder qty."""
    oh = on_hand(db, item.id)
    use = avg_daily_use(db, item.id)
    sup = db.get(Supplier, item.preferred_supplier_id) if item.preferred_supplier_id else None
    lead = sup.lead_time_days if sup else 3
    need = math.ceil(use * (lead + horizon_days)) - oh
    qty = max(item.reorder_qty, need, 1)
    return {"on_hand": oh, "avg_daily_use": round(use, 2), "lead_time_days": lead, "horizon_days": horizon_days,
            "days_of_supply": round(oh / use, 1) if use else None, "recommended_qty": qty,
            "method": "28-day moving average × (lead time + 14 days) − on hand; floor = reorder quantity"}
