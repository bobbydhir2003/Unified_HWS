"""Pharmacy & inventory API (B6) incl. purchase requests (B9 base) and pharmacist order verification."""

import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.api.deps import TenantContext, require
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import (
    InventoryItem,
    InventoryLot,
    Location,
    Order,
    PurchaseRequest,
    StockBalance,
    StockMovement,
    Supplier,
    User,
)
from app.services import inventory as I

router = APIRouter(tags=["pharmacy"])


def _err(ctx: TenantContext, fn):
    try:
        return fn()
    except I.InventoryError as e:
        ctx.db.rollback()
        raise bad_request(str(e)) from None


def _item(ctx, iid) -> InventoryItem:
    it = ctx.db.get(InventoryItem, iid)
    if not it or it.organization_id != ctx.org_id:
        raise not_found("Item")
    return it


def _lot(ctx, lid) -> InventoryLot:
    lot = ctx.db.get(InventoryLot, lid)
    if not lot or lot.organization_id != ctx.org_id:
        raise not_found("Lot")
    return lot


def _loc(ctx, lid) -> Location:
    loc = ctx.db.get(Location, lid)
    if not loc or loc.organization_id != ctx.org_id or loc.kind not in ("storage", "area"):
        raise not_found("Stock location")
    ctx.require_facility(loc.facility_id)
    return loc


@router.get("/inventory/locations")
def stock_locations(ctx: TenantContext = Depends(require(P.INVENTORY_READ))):
    q = select(Location).where(Location.organization_id == ctx.org_id, Location.kind.in_(("storage", "area")), Location.is_active.is_(True),
                               or_(Location.code.like("RX-%"), Location.code == "SUPPLY"))
    if ctx.facility_ids is not None:
        q = q.where(Location.facility_id.in_(ctx.facility_ids))
    return [{"id": x.id, "name": x.name, "code": x.code, "facility_id": x.facility_id} for x in ctx.db.scalars(q.order_by(Location.code))]


@router.get("/inventory/items")
def list_items(kind: str | None = None, q: str | None = None, status: Literal["all", "low", "expiring"] = "all",
               ctx: TenantContext = Depends(require(P.INVENTORY_READ))):
    stmt = select(InventoryItem).where(InventoryItem.organization_id == ctx.org_id, InventoryItem.is_active.is_(True))
    if kind:
        stmt = stmt.where(InventoryItem.kind == kind)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(InventoryItem.name).like(like), func.lower(InventoryItem.sku).like(like), InventoryItem.ndc == q))
    items = ctx.db.scalars(stmt.order_by(InventoryItem.name)).all()
    ids = [i.id for i in items]
    oh = dict(ctx.db.execute(select(StockBalance.item_id, func.sum(StockBalance.quantity)).where(StockBalance.item_id.in_(ids))
                             .group_by(StockBalance.item_id)).all()) if ids else {}
    exp = dict(ctx.db.execute(select(InventoryLot.item_id, func.min(InventoryLot.expiry_date)).join(StockBalance, StockBalance.lot_id == InventoryLot.id)
                              .where(InventoryLot.item_id.in_(ids), StockBalance.quantity > 0).group_by(InventoryLot.item_id)).all()) if ids else {}
    since = now() - timedelta(days=28)
    use = dict(ctx.db.execute(select(StockMovement.item_id, func.sum(StockMovement.quantity)).where(
        StockMovement.item_id.in_(ids), StockMovement.kind.in_(I.CONSUMPTION), StockMovement.at > since).group_by(StockMovement.item_id)).all()) if ids else {}
    out = []
    soon = date.today() + timedelta(days=30)
    for it in items:
        on = int(oh.get(it.id) or 0)
        daily = float(use.get(it.id) or 0) / 28
        nearest = exp.get(it.id)
        st = "out" if on == 0 else "low" if on <= it.reorder_point else "ok"
        row = {"id": it.id, "name": it.name, "sku": it.sku, "ndc": it.ndc, "kind": it.kind, "category": it.category, "unit": it.unit,
               "strength": it.strength, "form": it.form, "is_controlled": it.is_controlled, "on_hand": on, "reorder_point": it.reorder_point,
               "reorder_qty": it.reorder_qty, "avg_daily_use": round(daily, 2), "days_of_supply": round(on / daily, 1) if daily else None,
               "nearest_expiry": nearest, "expiring_soon": bool(nearest and nearest <= soon), "stock_status": st,
               "unit_cost_cents": it.unit_cost_cents}
        if status == "low" and st == "ok":
            continue
        if status == "expiring" and not row["expiring_soon"]:
            continue
        out.append(row)
    return out


class ItemIn(BaseModel):
    kind: Literal["medication", "supply", "equipment"]
    name: str = Field(min_length=2, max_length=200)
    sku: str = Field(min_length=2, max_length=40)
    ndc: str | None = Field(default=None, max_length=20)
    category: str | None = Field(default=None, max_length=60)
    form: str | None = Field(default=None, max_length=40)
    strength: str | None = Field(default=None, max_length=40)
    unit: str = Field(default="each", max_length=20)
    is_controlled: bool = False
    reorder_point: int = Field(default=0, ge=0)
    reorder_qty: int = Field(default=0, ge=0)
    unit_cost_cents: int = Field(default=0, ge=0)
    preferred_supplier_id: uuid.UUID | None = None


@router.post("/inventory/items", status_code=201)
def create_item(body: ItemIn, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    if ctx.db.scalar(select(InventoryItem.id).where(InventoryItem.organization_id == ctx.org_id, InventoryItem.sku == body.sku)):
        raise bad_request("An item with that SKU exists")
    it = InventoryItem(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(it)
    ctx.audit("inventory.item_created", resource_type="inventory_item", details={"sku": body.sku})
    ctx.db.commit()
    return {"id": it.id}


@router.get("/inventory/items/{iid}")
def item_detail(iid: uuid.UUID, ctx: TenantContext = Depends(require(P.INVENTORY_READ))):
    it = _item(ctx, iid)
    rows = ctx.db.execute(select(StockBalance, InventoryLot, Location).join(InventoryLot, InventoryLot.id == StockBalance.lot_id)
                          .join(Location, Location.id == StockBalance.location_id)
                          .where(StockBalance.item_id == it.id, StockBalance.quantity > 0).order_by(InventoryLot.expiry_date.nulls_last())).all()
    moves = ctx.db.execute(select(StockMovement, InventoryLot.lot_number, Location.name, User.first_name + " " + User.last_name)
                           .join(InventoryLot, InventoryLot.id == StockMovement.lot_id).join(Location, Location.id == StockMovement.location_id)
                           .outerjoin(User, User.id == StockMovement.actor_id)
                           .where(StockMovement.item_id == it.id).order_by(StockMovement.at.desc()).limit(50)).all()
    prs = ctx.db.scalars(select(PurchaseRequest).where(PurchaseRequest.item_id == it.id).order_by(PurchaseRequest.created_at.desc()).limit(10)).all()
    sup = ctx.db.get(Supplier, it.preferred_supplier_id) if it.preferred_supplier_id else None
    return {"item": {"id": it.id, "name": it.name, "sku": it.sku, "ndc": it.ndc, "kind": it.kind, "unit": it.unit, "strength": it.strength, "form": it.form,
                     "is_controlled": it.is_controlled, "reorder_point": it.reorder_point, "reorder_qty": it.reorder_qty, "category": it.category,
                     "supplier": sup.name if sup else None},
            "lots": [{"lot_id": lot.id, "lot_number": lot.lot_number, "expiry_date": lot.expiry_date, "expired": bool(lot.expiry_date and lot.expiry_date < date.today()),
                      "location_id": loc.id, "location": loc.name, "quantity": b.quantity} for b, lot, loc in rows],
            "movements": [{"id": m.id, "kind": m.kind, "quantity": m.quantity, "balance_after": m.balance_after, "lot": lotn, "location": locn, "by": who,
                           "reason": m.reason, "at": m.at, "approved": bool(m.approved_by_id)} for m, lotn, locn, who in moves],
            "recommendation": I.recommend_reorder(ctx.db, it),
            "purchase_requests": [pr_out(ctx, p) for p in prs]}


class ReceiveIn(BaseModel):
    item_id: uuid.UUID
    location_id: uuid.UUID
    lot_number: str = Field(min_length=1, max_length=40)
    expiry_date: date | None = None
    quantity: int = Field(gt=0, le=100000)
    purchase_request_id: uuid.UUID | None = None


@router.post("/inventory/receive", status_code=201)
def receive(body: ReceiveIn, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    it, loc = _item(ctx, body.item_id), _loc(ctx, body.location_id)
    pr = None
    if body.purchase_request_id:
        pr = ctx.db.get(PurchaseRequest, body.purchase_request_id)
        if not pr or pr.organization_id != ctx.org_id or pr.item_id != it.id:
            raise not_found("Purchase request")
        if pr.status not in ("approved", "ordered"):
            raise bad_request("Only approved/ordered purchase requests can be received")
    m = _err(ctx, lambda: I.receive(ctx.db, it, location=loc, lot_number=body.lot_number, expiry=body.expiry_date, qty=body.quantity,
                                    actor_id=ctx.user.id, purchase_request=pr))
    ctx.audit("inventory.received", resource_type="inventory_item", resource_id=it.id, details={"qty": body.quantity, "lot": body.lot_number})
    ctx.db.commit()
    return {"balance_after": m.balance_after}


class TransferIn(BaseModel):
    lot_id: uuid.UUID
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    quantity: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=300)


@router.post("/inventory/transfer")
def transfer(body: TransferIn, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    lot = _lot(ctx, body.lot_id)
    _err(ctx, lambda: I.transfer(ctx.db, lot, src=_loc(ctx, body.from_location_id), dst=_loc(ctx, body.to_location_id), qty=body.quantity,
                                 actor_id=ctx.user.id, reason=body.reason))
    ctx.audit("inventory.transferred", resource_type="inventory_lot", resource_id=lot.id, details={"qty": body.quantity})
    ctx.db.commit()
    return {"message": "Transferred"}


class DispenseIn(BaseModel):
    lot_id: uuid.UUID
    location_id: uuid.UUID
    quantity: int = Field(gt=0, le=1000)
    patient_id: uuid.UUID | None = None
    order_id: uuid.UUID | None = None


@router.post("/inventory/dispense")
def dispense(body: DispenseIn, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    lot = _lot(ctx, body.lot_id)
    if lot.item.kind == "medication" and not ctx.can(P.PHARMACY_VERIFY):
        raise forbidden("Only pharmacists dispense medications")
    if body.patient_id:
        from app.services.patients import get_patient

        get_patient(ctx, body.patient_id)
    if lot.item.kind == "medication" and (body.patient_id or body.order_id):
        # Patient-specific medication dispensing requires the verified order for that patient (closed loop).
        from fastapi import HTTPException

        from app.services import medication as MED

        o = ctx.db.get(Order, body.order_id) if body.order_id else None
        if o is not None and o.organization_id != ctx.org_id:
            o = None
        try:
            MED.assert_dispensable(o, body.patient_id)
        except MED.MedicationError as e:
            raise HTTPException(409, {"code": e.code, "message": str(e)}) from None
        body.patient_id = o.patient_id
    m = _err(ctx, lambda: I.dispense(ctx.db, lot, location=_loc(ctx, body.location_id), qty=body.quantity, actor_id=ctx.user.id,
                                     patient_id=body.patient_id, order_id=body.order_id))
    ctx.db.commit()
    from app.services.medication import dose_label_barcode

    return {"balance_after": m.balance_after, "movement_id": m.id,
            "dose_label": dose_label_barcode(m.id) if lot.item.kind == "medication" and body.order_id else None}


class AdjustIn(BaseModel):
    lot_id: uuid.UUID
    location_id: uuid.UUID
    quantity: int = Field(gt=0)
    action: Literal["adjust_up", "adjust_down", "waste"]
    reason: str = Field(min_length=5, max_length=300)
    case_id: uuid.UUID | None = None


@router.post("/inventory/adjust")
def adjust(body: AdjustIn, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    lot, loc = _lot(ctx, body.lot_id), _loc(ctx, body.location_id)
    if body.action == "adjust_up":
        m = _err(ctx, lambda: I.adjust_up(ctx.db, lot, location=loc, qty=body.quantity, actor_id=ctx.user.id, reason=body.reason))
        ctx.audit("inventory.adjusted_up", resource_type="inventory_lot", resource_id=lot.id, details={"qty": body.quantity})
        ctx.db.commit()
        return {"status": "done", "balance_after": m.balance_after}
    from app.models import Case

    case = ctx.db.get(Case, body.case_id) if body.case_id else None
    req = _err(ctx, lambda: I.request_removal(ctx.db, lot, location=loc, qty=body.quantity, kind=body.action, reason=body.reason,
                                              actor_id=ctx.user.id, case=case if case and case.organization_id == ctx.org_id else None))
    ctx.db.commit()
    return {"status": "pending_approval", "approval_id": req.id, "message": "Waiting for a second person to approve"}


# ---------- Suppliers & purchase requests ----------

@router.get("/suppliers")
def suppliers(ctx: TenantContext = Depends(require(P.INVENTORY_READ))):
    return [{"id": s.id, "name": s.name, "lead_time_days": s.lead_time_days, "email": s.email, "phone": s.phone}
            for s in ctx.db.scalars(select(Supplier).where(Supplier.organization_id == ctx.org_id).order_by(Supplier.name))]


class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    lead_time_days: int = Field(default=3, ge=0, le=120)


@router.post("/suppliers", status_code=201)
def create_supplier(body: SupplierIn, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    s = Supplier(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(s)
    ctx.db.commit()
    return {"id": s.id}


def pr_out(ctx, p: PurchaseRequest) -> dict:
    sup = ctx.db.get(Supplier, p.supplier_id) if p.supplier_id else None
    return {"id": p.id, "number": p.number, "item_id": p.item_id, "item": p.item.name, "unit": p.item.unit, "quantity": p.quantity,
            "received_quantity": p.received_quantity, "status": p.status, "source": p.source, "reason": p.reason, "recommendation": p.recommendation,
            "supplier": sup.name if sup else None, "estimated_cost_cents": p.quantity * p.unit_cost_cents, "created_at": p.created_at,
            "requested_by_id": p.requested_by_id, "decided_at": p.decided_at, "decision_note": p.decision_note, "po_reference": p.po_reference,
            "deliver_to_location_id": p.deliver_to_location_id, "case_id": p.case_id,
            "can_decide": p.status == "submitted" and ctx.can(P.PROCUREMENT_APPROVE) and p.requested_by_id != ctx.user.id}


@router.get("/purchase-requests")
def list_prs(status: str | None = None, ctx: TenantContext = Depends(require(P.INVENTORY_READ))):
    q = select(PurchaseRequest).where(PurchaseRequest.organization_id == ctx.org_id)
    if status == "open":
        q = q.where(PurchaseRequest.status.in_(("submitted", "approved", "ordered")))
    elif status:
        q = q.where(PurchaseRequest.status == status)
    return [pr_out(ctx, p) for p in ctx.db.scalars(q.order_by(PurchaseRequest.created_at.desc()).limit(200))]


class PRIn(BaseModel):
    item_id: uuid.UUID
    quantity: int = Field(gt=0, le=100000)
    reason: str | None = Field(default=None, max_length=500)
    supplier_id: uuid.UUID | None = None
    deliver_to_location_id: uuid.UUID | None = None


@router.post("/purchase-requests", status_code=201)
def create_pr(body: PRIn, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    it = _item(ctx, body.item_id)
    loc = _loc(ctx, body.deliver_to_location_id) if body.deliver_to_location_id else None
    fac = loc.facility_id if loc else (ctx.facility_ids[0] if ctx.facility_ids else None)
    if fac is None:
        from app.models import Clinic

        fac = ctx.db.scalar(select(Clinic.id).where(Clinic.organization_id == ctx.org_id, Clinic.facility_type == "hospital"))
    p = PurchaseRequest(organization_id=ctx.org_id, facility_id=fac, item_id=it.id, quantity=body.quantity, reason=body.reason,
                        supplier_id=body.supplier_id or it.preferred_supplier_id, deliver_to_location_id=loc.id if loc else None,
                        unit_cost_cents=it.unit_cost_cents, requested_by_id=ctx.user.id, recommendation=I.recommend_reorder(ctx.db, it))
    ctx.db.add(p)
    ctx.audit("procurement.requested", resource_type="purchase_request", details={"item": it.sku, "qty": body.quantity})
    ctx.db.commit()
    return pr_out(ctx, p)


class DecideIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


@router.post("/purchase-requests/{pid}/decide")
def decide_pr(pid: uuid.UUID, body: DecideIn, ctx: TenantContext = Depends(require(P.PROCUREMENT_APPROVE))):
    p = ctx.db.get(PurchaseRequest, pid)
    if not p or p.organization_id != ctx.org_id:
        raise not_found("Purchase request")
    if p.status != "submitted":
        raise bad_request(f"Request is {p.status}")
    if p.requested_by_id == ctx.user.id:
        raise bad_request("You can't approve your own request")
    if not body.approve and not body.note:
        raise bad_request("Give a reason for rejecting")
    p.status, p.decided_by_id, p.decided_at, p.decision_note = ("approved" if body.approve else "rejected"), ctx.user.id, now(), body.note
    if p.case_id:
        from app.engine.cases import log_event
        from app.models import Case

        c = ctx.db.get(Case, p.case_id)
        if c:
            log_event(ctx.db, c, "purchase_request_decided", f"Purchase request #{p.number} {p.status}" + (f" — {body.note}" if body.note else ""),
                      actor_id=ctx.user.id, data={"purchase_request_id": str(p.id), "status": p.status})
    ctx.audit(f"procurement.{p.status}", resource_type="purchase_request", resource_id=p.id)
    ctx.db.commit()
    return pr_out(ctx, p)


@router.post("/purchase-requests/{pid}/order")
def order_pr(pid: uuid.UUID, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    """Send to the supplier. SIMULATED: no supplier integration — records a synthetic PO reference."""
    p = ctx.db.get(PurchaseRequest, pid)
    if not p or p.organization_id != ctx.org_id:
        raise not_found("Purchase request")
    if p.status != "approved":
        raise bad_request("Only approved requests can be ordered")
    p.status, p.ordered_at, p.po_reference = "ordered", now(), f"SIM-PO-{p.number}"
    ctx.audit("procurement.ordered", resource_type="purchase_request", resource_id=p.id, details={"simulated": True})
    ctx.db.commit()
    return pr_out(ctx, p)


# ---------- Pharmacist verification ----------

@router.get("/pharmacy/verifications")
def verification_queue(ctx: TenantContext = Depends(require(P.PHARMACY_READ))):
    """Inpatient medication orders awaiting a pharmacist decision (compatibility alias of /pharmacy/medication-queue)."""
    from app.api.routers.mar import medication_queue

    return [{**r, "order_id": r["id"]} for r in medication_queue(status="pending_verification", ctx=ctx)]


class VerifyIn(BaseModel):
    order_id: uuid.UUID
    status: Literal["verified", "rejected", "clarify"]
    note: str | None = Field(default=None, max_length=1000)
    manual_interaction_review: bool = False


@router.post("/pharmacy/verifications", status_code=201)
def verify(body: VerifyIn, ctx: TenantContext = Depends(require(P.PHARMACY_VERIFY))):
    """Compatibility alias of POST /orders/{id}/pharmacy-decision (same rules)."""
    from app.api.routers.mar import DecisionIn, pharmacy_decision

    out = pharmacy_decision(body.order_id, DecisionIn(decision=body.status, note=body.note,
                                                      manual_interaction_review=body.manual_interaction_review), ctx=ctx)
    return {"status": body.status, "order_status": out["status"]}


@router.get("/inventory/report")
def report(ctx: TenantContext = Depends(require(P.INVENTORY_READ))):
    val = ctx.db.execute(select(InventoryItem.kind, func.sum(StockBalance.quantity * InventoryItem.unit_cost_cents), func.sum(StockBalance.quantity))
                         .join(InventoryItem, InventoryItem.id == StockBalance.item_id).where(InventoryItem.organization_id == ctx.org_id)
                         .group_by(InventoryItem.kind)).all()
    exp = ctx.db.scalar(select(func.coalesce(func.sum(StockBalance.quantity * InventoryItem.unit_cost_cents), 0)).join(InventoryLot, InventoryLot.id == StockBalance.lot_id)
                        .join(InventoryItem, InventoryItem.id == StockBalance.item_id).where(
        InventoryItem.organization_id == ctx.org_id, InventoryLot.expiry_date <= date.today() + timedelta(days=30), StockBalance.quantity > 0))
    waste = ctx.db.scalar(select(func.coalesce(func.sum(StockMovement.quantity * InventoryItem.unit_cost_cents), 0)).join(InventoryItem, InventoryItem.id == StockMovement.item_id)
                          .where(StockMovement.organization_id == ctx.org_id, StockMovement.kind == "waste", StockMovement.at > now() - timedelta(days=30)))
    items = list_items(ctx=ctx)
    return {"valuation": [{"kind": k, "value_cents": int(v or 0), "units": int(u or 0)} for k, v, u in val],
            "expiring_30d_value_cents": int(exp or 0), "waste_30d_value_cents": int(waste or 0),
            "low_stock_items": sum(1 for i in items if i["stock_status"] != "ok"), "items": len(items),
            "pending_verifications": len(verification_queue(ctx=ctx)) if ctx.can(P.PHARMACY_READ) else None}
