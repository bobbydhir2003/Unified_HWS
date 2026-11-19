"""Equipment registry + maintenance (B9) and location par levels."""

import uuid
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import TenantContext, require
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.models import Equipment, InventoryItem, Location, MaintenanceLog, StockPar, User

router = APIRouter(tags=["equipment"])


def eq_out(e: Equipment, locs: dict) -> dict:
    today = date.today()
    return {"id": e.id, "name": e.name, "asset_tag": e.asset_tag, "category": e.category, "manufacturer": e.manufacturer, "model": e.model,
            "serial_number": e.serial_number, "status": e.status, "location": locs.get(e.location_id), "location_id": e.location_id,
            "maintenance_interval_days": e.maintenance_interval_days, "last_maintenance_on": e.last_maintenance_on, "next_maintenance_due": e.next_maintenance_due,
            "overdue": bool(e.next_maintenance_due and e.next_maintenance_due < today and e.status != "retired"),
            "due_soon": bool(e.next_maintenance_due and today <= e.next_maintenance_due <= today + timedelta(days=14))}


def _locs(ctx) -> dict:
    return {x.id: x.name for x in ctx.db.scalars(select(Location).where(Location.organization_id == ctx.org_id))}


@router.get("/equipment")
def list_equipment(status: str | None = None, ctx: TenantContext = Depends(require(P.INVENTORY_READ))):
    q = select(Equipment).where(Equipment.organization_id == ctx.org_id)
    if ctx.facility_ids is not None:
        q = q.where(Equipment.facility_id.in_(ctx.facility_ids))
    if status:
        q = q.where(Equipment.status == status)
    locs = _locs(ctx)
    return [eq_out(e, locs) for e in ctx.db.scalars(q.order_by(Equipment.next_maintenance_due.nulls_last(), Equipment.name))]


class EquipmentIn(BaseModel):
    facility_id: uuid.UUID
    location_id: uuid.UUID | None = None
    name: str = Field(min_length=2, max_length=120)
    asset_tag: str = Field(min_length=2, max_length=40)
    category: str = Field(default="clinical", max_length=40)
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    maintenance_interval_days: int = Field(default=180, ge=1, le=3650)
    last_maintenance_on: date | None = None


@router.post("/equipment", status_code=201)
def create_equipment(body: EquipmentIn, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    ctx.require_facility(body.facility_id)
    e = Equipment(organization_id=ctx.org_id, **body.model_dump())
    e.next_maintenance_due = (body.last_maintenance_on or date.today()) + timedelta(days=body.maintenance_interval_days)
    ctx.db.add(e)
    try:
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise bad_request("Asset tag already in use") from None
    ctx.audit("equipment.created", resource_type="equipment", resource_id=e.id)
    ctx.db.commit()
    return eq_out(e, _locs(ctx))


class StatusIn(BaseModel):
    status: Literal["in_service", "out_of_service", "maintenance", "retired"]
    note: str | None = Field(default=None, max_length=300)


@router.post("/equipment/{eid}/status")
def set_status(eid: uuid.UUID, body: StatusIn, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    e = ctx.db.get(Equipment, eid)
    if not e or e.organization_id != ctx.org_id:
        raise not_found("Equipment")
    if body.status in ("out_of_service", "retired") and not body.note:
        raise bad_request("Give a reason")
    e.status = body.status
    if body.note:
        e.notes = body.note
    ctx.audit("equipment.status", resource_type="equipment", resource_id=e.id, details={"status": body.status})
    ctx.db.commit()
    return eq_out(e, _locs(ctx))


class MaintIn(BaseModel):
    kind: Literal["preventive", "repair", "inspection", "calibration"] = "preventive"
    result: Literal["passed", "failed", "repaired"] = "passed"
    notes: str | None = Field(default=None, max_length=2000)
    performed_on: date | None = None


@router.post("/equipment/{eid}/maintenance", status_code=201)
def log_maintenance(eid: uuid.UUID, body: MaintIn, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    e = ctx.db.get(Equipment, eid)
    if not e or e.organization_id != ctx.org_id:
        raise not_found("Equipment")
    on = body.performed_on or date.today()
    if on > date.today():
        raise bad_request("Maintenance date can't be in the future")
    ctx.db.add(MaintenanceLog(organization_id=ctx.org_id, equipment_id=e.id, kind=body.kind, result=body.result, notes=body.notes,
                              performed_by_id=ctx.user.id, performed_on=on))
    if body.result == "failed":
        e.status = "out_of_service"
    else:
        e.last_maintenance_on, e.next_maintenance_due = on, on + timedelta(days=e.maintenance_interval_days)
        if e.status in ("maintenance", "out_of_service") and body.result in ("passed", "repaired"):
            e.status = "in_service"
    ctx.audit("equipment.maintenance", resource_type="equipment", resource_id=e.id, details={"kind": body.kind, "result": body.result})
    ctx.db.commit()
    return eq_out(e, _locs(ctx))


@router.get("/equipment/{eid}/maintenance")
def maintenance_history(eid: uuid.UUID, ctx: TenantContext = Depends(require(P.INVENTORY_READ))):
    e = ctx.db.get(Equipment, eid)
    if not e or e.organization_id != ctx.org_id:
        raise not_found("Equipment")
    rows = ctx.db.execute(select(MaintenanceLog, User.first_name + " " + User.last_name).outerjoin(User, User.id == MaintenanceLog.performed_by_id)
                          .where(MaintenanceLog.equipment_id == e.id).order_by(MaintenanceLog.performed_on.desc())).all()
    return [{"kind": m.kind, "result": m.result, "notes": m.notes, "performed_on": m.performed_on, "by": who} for m, who in rows]


# ---------- Par levels ----------

class ParIn(BaseModel):
    location_id: uuid.UUID
    item_id: uuid.UUID
    par_level: int = Field(ge=0, le=100000)


@router.put("/inventory/pars")
def set_par(body: ParIn, ctx: TenantContext = Depends(require(P.INVENTORY_WRITE))):
    loc, it = ctx.db.get(Location, body.location_id), ctx.db.get(InventoryItem, body.item_id)
    if not loc or loc.organization_id != ctx.org_id or not it or it.organization_id != ctx.org_id:
        raise not_found("Location or item")
    row = ctx.db.scalar(select(StockPar).where(StockPar.location_id == loc.id, StockPar.item_id == it.id))
    if not row:
        row = StockPar(organization_id=ctx.org_id, location_id=loc.id, item_id=it.id, par_level=body.par_level)
        ctx.db.add(row)
    row.par_level = body.par_level
    ctx.db.commit()
    return {"location_id": loc.id, "item_id": it.id, "par_level": row.par_level}


@router.get("/inventory/pars")
def list_pars(item_id: uuid.UUID | None = None, ctx: TenantContext = Depends(require(P.INVENTORY_READ))):
    from app.monitors.equipment import par_shortfalls

    return par_shortfalls(ctx.db, ctx.org_id, item_id=item_id, include_ok=True)
