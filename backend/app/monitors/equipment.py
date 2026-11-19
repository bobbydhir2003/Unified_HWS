"""Equipment maintenance due/overdue and location stock below par (restock-by-transfer suggestion)."""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select

from app.engine.cases import Finding
from app.engine.monitors import Monitor, register
from app.models import Equipment, InventoryItem, Location, StockBalance, StockPar


class MaintenanceDue(Monitor):
    key = "equipment.maintenance_due"
    name = "Equipment maintenance due"
    description = "Preventive maintenance is due within the window or overdue for equipment in service."
    category = "equipment"
    default_config = {"window_days": 14, "assign_role": "hospital_admin"}
    config_help = {"window_days": "Warn this many days before the due date", "assign_role": "Owner role (biomedical engineering)"}

    def evaluate(self, db, org_id, cfg):
        out = []
        for e in db.scalars(select(Equipment).where(Equipment.organization_id == org_id, Equipment.status.in_(("in_service", "maintenance")),
                                                    Equipment.next_maintenance_due <= date.today() + timedelta(days=int(cfg["window_days"])))):
            days = (e.next_maintenance_due - date.today()).days
            out.append(Finding(dedupe_key=f"eq.maint:{e.id}:{e.next_maintenance_due.isoformat()}", kind=self.key, category="equipment",
                               severity="high" if days < 0 else "medium" if days <= 3 else "low",
                               title=f"{e.name} ({e.asset_tag}) maintenance {'overdue by ' + str(-days) + ' d' if days < 0 else f'due in {days} d'}",
                               facility_id=e.facility_id, subject_type="equipment", subject_id=str(e.id), assign_role=cfg["assign_role"], link="/equipment",
                               sla_minutes=max(days, 1) * 1440, evidence={"due": e.next_maintenance_due.isoformat(), "interval_days": e.maintenance_interval_days,
                                                                         "last": e.last_maintenance_on.isoformat() if e.last_maintenance_on else None}))
        return out

    def clear(self, db, case, cfg):
        e = db.get(Equipment, uuid.UUID(case.subject_id))
        return "verified_active", f"Maintenance logged; next due {e.next_maintenance_due}." if e and e.next_maintenance_due else ("no_longer_applicable", "Equipment retired")


def par_shortfalls(db, org_id, item_id=None, include_ok=False) -> list[dict]:
    q = select(StockPar, Location, InventoryItem).join(Location, Location.id == StockPar.location_id).join(InventoryItem, InventoryItem.id == StockPar.item_id) \
        .where(StockPar.organization_id == org_id)
    if item_id:
        q = q.where(StockPar.item_id == item_id)
    out = []
    for par, loc, it in db.execute(q).all():
        on = int(db.scalar(select(func.coalesce(func.sum(StockBalance.quantity), 0)).where(StockBalance.location_id == loc.id, StockBalance.item_id == it.id)) or 0)
        if include_ok or on < par.par_level:
            out.append({"location_id": loc.id, "location": loc.name, "facility_id": loc.facility_id, "item_id": it.id, "item": it.name, "unit": it.unit,
                        "par_level": par.par_level, "on_hand": on, "short": max(par.par_level - on, 0)})
    return out


class BelowPar(Monitor):
    key = "inventory.below_par"
    name = "Unit stock below par"
    description = "A unit/department location holds less than its par level — restock by transfer from the main store."
    category = "inventory"
    default_config = {"threshold_pct": 50, "assign_role": "pharmacist"}
    config_help = {"threshold_pct": "Open a case when on-hand falls below this % of par", "assign_role": "Owner role"}

    def evaluate(self, db, org_id, cfg):
        out = []
        for r in par_shortfalls(db, org_id):
            if r["on_hand"] * 100 >= r["par_level"] * int(cfg["threshold_pct"]):
                continue
            out.append(Finding(dedupe_key=f"inv.par:{r['location_id']}:{r['item_id']}", kind=self.key, category="inventory",
                               severity="high" if r["on_hand"] == 0 else "medium",
                               title=f"{r['location']}: {r['item']} {r['on_hand']}/{r['par_level']} {r['unit']} — restock {r['short']}",
                               facility_id=r["facility_id"], subject_type="inventory_item", subject_id=str(r["item_id"]), assign_role=cfg["assign_role"],
                               link=f"/pharmacy?item={r['item_id']}", sla_minutes=480, evidence=r | {"location_id": str(r["location_id"]), "item_id": str(r["item_id"]),
                                                                                                   "facility_id": str(r["facility_id"])}))
        return out

    def clear(self, db, case, cfg):
        return "verified_active", "Restocked to par."


register(MaintenanceDue())
register(BelowPar())
