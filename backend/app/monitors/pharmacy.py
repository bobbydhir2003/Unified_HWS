"""Pharmacy Watchdog: expiring/expired stock, stock below reorder point (with a deterministic reorder recommendation and
a purchase request awaiting approval), and unusual consumption (a diversion/waste signal for pharmacist review)."""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select

from app.core.security import now
from app.engine.cases import Finding, add_task
from app.engine.monitors import Monitor, register
from app.engine.notifications import deliver_to_role
from app.models import (
    Clinic,
    InventoryItem,
    InventoryLot,
    Location,
    PurchaseRequest,
    StockBalance,
    StockMovement,
)
from app.services.inventory import avg_daily_use, recommend_reorder


class ExpiringStock(Monitor):
    key = "pharmacy.expiring"
    name = "Pharmacy Watchdog — expiring stock"
    description = "Lots with stock on hand that expire soon (or already expired) at any location — move, use first, or waste with approval."
    category = "pharmacy"
    default_config = {"window_days": 30, "urgent_days": 7, "assign_role": "pharmacist"}
    config_help = {"window_days": "Flag lots expiring within this many days", "urgent_days": "High severity within this many days",
                   "assign_role": "Role that owns expiry cases"}

    def evaluate(self, db, org_id, cfg):
        horizon = date.today() + timedelta(days=int(cfg["window_days"]))
        rows = db.execute(select(InventoryLot, StockBalance, Location).join(StockBalance, StockBalance.lot_id == InventoryLot.id)
                          .join(Location, Location.id == StockBalance.location_id)
                          .where(InventoryLot.organization_id == org_id, StockBalance.quantity > 0, InventoryLot.expiry_date.is_not(None),
                                 InventoryLot.expiry_date <= horizon)).all()
        out = []
        for lot, bal, loc in rows:
            days = (lot.expiry_date - date.today()).days
            expired = days < 0
            out.append(Finding(
                dedupe_key=f"rx.expiry:{lot.id}:{loc.id}", kind=self.key, category="pharmacy",
                severity="high" if expired or days <= int(cfg["urgent_days"]) else "medium" if days <= 14 else "low",
                title=(f"EXPIRED {lot.item.name} lot {lot.lot_number} — {bal.quantity} at {loc.name}" if expired else
                       f"{lot.item.name} lot {lot.lot_number} expires in {days} d — {bal.quantity} at {loc.name}"),
                summary="Remove from service and waste (needs a second pharmacist's approval)." if expired else
                        "Use first, transfer to a higher-use location, or waste with approval before expiry.",
                facility_id=loc.facility_id, department_id=loc.department_id, subject_type="inventory_lot", subject_id=str(lot.id),
                assign_role=cfg["assign_role"], link=f"/pharmacy?item={lot.item_id}", sla_minutes=240 if expired else max(days, 1) * 720,
                evidence={"item": lot.item.name, "lot": lot.lot_number, "expiry_date": lot.expiry_date.isoformat(), "days_left": days,
                          "quantity": bal.quantity, "location": loc.name, "controlled": lot.item.is_controlled},
                data={"lot_id": str(lot.id), "location_id": str(loc.id)}))
        return out

    def on_open(self, db, case, f, cfg):
        add_task(db, case, org_id=case.organization_id, title=f"Expiry action: {f.evidence['item']} lot {f.evidence['lot']} ({f.evidence['location']})",
                 role=cfg["assign_role"], dedupe_key=f"task:{case.dedupe_key}", priority="high" if case.severity == "high" else "normal",
                 kind="pharmacy.expiry", due_minutes=1440)

    def clear(self, db, case, cfg):
        lot = db.get(InventoryLot, uuid.UUID(case.data["lot_id"]))
        return "verified_active", f"No stock of lot {lot.lot_number if lot else ''} remains at that location (used, moved or wasted)."


class LowStock(Monitor):
    key = "inventory.low_stock"
    name = "Pharmacy Watchdog — low stock"
    description = ("Item on hand at or below its reorder point. Opens a purchase request with a recommended quantity "
                   "(28-day average use × lead time + 14 days) for approval.")
    category = "inventory"
    default_config = {"assign_role": "pharmacist", "approver_role": "hospital_admin", "auto_purchase_request": True}
    config_help = {"assign_role": "Role that owns low-stock cases", "approver_role": "Role notified to approve purchase requests",
                   "auto_purchase_request": "Create a purchase request (awaiting approval) when a case opens"}

    def evaluate(self, db, org_id, cfg):
        items = db.scalars(select(InventoryItem).where(InventoryItem.organization_id == org_id, InventoryItem.is_active.is_(True),
                                                       InventoryItem.reorder_point > 0)).all()
        out = []
        for it in items:
            rec = recommend_reorder(db, it)
            if rec["on_hand"] > it.reorder_point:
                continue
            open_pr = db.scalar(select(PurchaseRequest.id).where(PurchaseRequest.item_id == it.id,
                                                                 PurchaseRequest.status.in_(("submitted", "approved", "ordered"))))
            sev = "high" if rec["on_hand"] == 0 or (rec["days_of_supply"] is not None and rec["days_of_supply"] < 2) else "medium"
            hosp = db.scalar(select(Clinic.id).where(Clinic.organization_id == org_id, Clinic.facility_type == "hospital"))
            out.append(Finding(
                dedupe_key=f"inv.low:{it.id}", kind=self.key, category="inventory" if it.kind != "medication" else "pharmacy", severity=sev,
                title=f"Low stock: {it.name} — {rec['on_hand']} {it.unit} on hand (reorder at {it.reorder_point})",
                summary=f"Recommended order: {rec['recommended_qty']} {it.unit}. " + (f"About {rec['days_of_supply']} days of supply left." if rec["days_of_supply"] else ""),
                facility_id=hosp, subject_type="inventory_item", subject_id=str(it.id), assign_role=cfg["assign_role"], link=f"/pharmacy?item={it.id}",
                sla_minutes=240 if sev == "high" else 1440, evidence={**rec, "item": it.name, "reorder_point": it.reorder_point,
                                                                     "purchase_request_open": bool(open_pr)},
                data={"item_id": str(it.id)}))
        return out

    def on_open(self, db, case, f, cfg):
        it = db.get(InventoryItem, uuid.UUID(f.data["item_id"]))
        if cfg.get("auto_purchase_request") and not f.evidence["purchase_request_open"] and case.facility_id:
            main = db.scalar(select(Location.id).where(Location.facility_id == case.facility_id,
                                                       Location.code == ("RX-MAIN" if it.kind == "medication" else "SUPPLY")))
            pr = PurchaseRequest(organization_id=case.organization_id, facility_id=case.facility_id, item_id=it.id, supplier_id=it.preferred_supplier_id,
                                 deliver_to_location_id=main, quantity=f.evidence["recommended_qty"], unit_cost_cents=it.unit_cost_cents,
                                 status="submitted", source="watchdog", reason=f"Pharmacy Watchdog: {case.title}", recommendation=f.evidence, case_id=case.id)
            db.add(pr)
            db.flush()
            from app.engine.cases import log_event

            log_event(db, case, "purchase_request", f"Purchase request #{pr.number} for {pr.quantity} {it.unit} awaiting approval",
                      actor_kind="agent", data={"purchase_request_id": str(pr.id)})
            deliver_to_role(db, case.organization_id, cfg["approver_role"], subject=f"Approve purchase request #{pr.number}: {it.name}",
                            body=f"{pr.quantity} {it.unit} recommended by the Pharmacy Watchdog.", link="/pharmacy?tab=purchasing",
                            dedupe=f"pr:{pr.id}:approve", case=case, category="inventory")

    def clear(self, db, case, cfg):
        it = db.get(InventoryItem, uuid.UUID(case.data["item_id"]))
        return "verified_active", f"Stock restored above the reorder point for {it.name if it else 'item'}."


class UnusualUsage(Monitor):
    key = "pharmacy.unusual_usage"
    name = "Pharmacy Watchdog — unusual consumption"
    description = "Dispensing/waste in the last 24 h far above the 28-day daily average (possible error, waste or diversion) — for pharmacist review."
    category = "pharmacy"
    default_config = {"multiplier": 3.0, "min_units": 10, "assign_role": "pharmacist"}
    config_help = {"multiplier": "Flag when 24 h use exceeds this × the daily average", "min_units": "Ignore items with fewer units used",
                   "assign_role": "Role that reviews the signal"}

    def evaluate(self, db, org_id, cfg):
        rows = db.execute(select(StockMovement.item_id, func.sum(StockMovement.quantity)).where(
            StockMovement.organization_id == org_id, StockMovement.kind.in_(("dispense", "waste")), StockMovement.at > now() - timedelta(hours=24))
            .group_by(StockMovement.item_id)).all()
        out = []
        for item_id, used in rows:
            avg = avg_daily_use(db, item_id)
            if used < int(cfg["min_units"]) or used <= float(cfg["multiplier"]) * max(avg, 0.5):
                continue
            it = db.get(InventoryItem, item_id)
            out.append(Finding(dedupe_key=f"rx.usage:{item_id}:{date.today().isoformat()}", kind=self.key, category="pharmacy",
                               severity="high" if it.is_controlled else "medium",
                               title=f"Unusual use of {it.name}: {used} {it.unit} in 24 h (avg {avg:.1f}/day)" + (" — controlled substance" if it.is_controlled else ""),
                               subject_type="inventory_item", subject_id=str(item_id), assign_role=cfg["assign_role"], link=f"/pharmacy?item={item_id}",
                               sla_minutes=480, evidence={"used_24h": int(used), "avg_daily_28d": round(avg, 2), "controlled": it.is_controlled}))
        return out

    def clear(self, db, case, cfg):
        return "condition_cleared", "Consumption back within the expected range (or a new day started)."


register(ExpiringStock())
register(LowStock())
register(UnusualUsage())
