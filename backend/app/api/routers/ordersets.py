"""Terminology search and versioned order sets.

Order sets: editable drafts → authorized publishing (clinic:manage) → new versions retire older published ones.
Applying a set never signs anything: it creates DRAFT orders for the items the clinician kept selected (with any edits),
each validated like a hand-entered order; the clinician then reviews and signs each order individually.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import TenantContext, get_ctx, require
from app.api.routers.orders import OrderIn, create_order
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import OrderSet, OrderSetItem, User
from app.services import terminology as T

router = APIRouter(tags=["order sets & terminology"])


# ---------------------------------------------------------------------------------------------- terminology

@router.get("/terminology/systems")
def terminology_systems(ctx: TenantContext = Depends(get_ctx)):
    return T.systems(ctx.db)


@router.get("/terminology/{system}/search")
def terminology_search(system: Literal["ICD-10-CM"], q: str = Query(min_length=1, max_length=100), include_retired: bool = False,
                       limit: int = Query(20, ge=1, le=50), ctx: TenantContext = Depends(get_ctx)):
    return T.search(ctx.db, system, q, limit=limit, include_retired=include_retired)


@router.get("/terminology/{system}/codes/{code}")
def terminology_lookup(system: Literal["ICD-10-CM"], code: str, ctx: TenantContext = Depends(get_ctx)):
    c = T.lookup(ctx.db, system, code)
    if not c:
        raise not_found("Code")
    return c


# ---------------------------------------------------------------------------------------------- order sets

class ItemIn(BaseModel):
    order_type: Literal["medication", "lab", "imaging", "referral", "procedure", "nursing"]
    details: dict
    priority: Literal["routine", "urgent", "stat"] = "routine"
    default_selected: bool = True
    note: str | None = Field(default=None, max_length=300)


class OrderSetIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=2000)
    items: list[ItemIn] = Field(min_length=1, max_length=40)


def _name(ctx, uid):
    u = ctx.db.get(User, uid) if uid else None
    return u.display_name if u else None


def set_out(ctx: TenantContext, s: OrderSet) -> dict:
    return {"id": s.id, "key": s.key, "version": s.version, "name": s.name, "category": s.category, "description": s.description,
            "status": s.status, "is_demonstration": s.is_demonstration, "published_at": s.published_at,
            "published_by": _name(ctx, s.published_by_id), "created_by": _name(ctx, s.created_by_id), "created_at": s.created_at,
            "items": [{"id": i.id, "order_type": i.order_type, "details": i.details, "priority": i.priority, "default_selected": i.default_selected,
                       "note": i.note, "title": _title(i)} for i in s.items]}


def _title(i: OrderSetItem) -> str:
    d = i.details or {}
    return str(d.get("name") or d.get("instruction") or d.get("title") or d.get("code") or d.get("specialty") or i.order_type)


def _validate(items: list[ItemIn]) -> None:
    from app.api.routers.orders import _normalize

    for it in items:
        _normalize(it.order_type, it.details)  # same validation as a hand-entered order (422 on bad content)


def _get(ctx, sid) -> OrderSet:
    s = ctx.db.get(OrderSet, sid)
    if not s or s.organization_id != ctx.org_id:
        raise not_found("Order set")
    return s


def _can_read(ctx: TenantContext) -> None:
    from app.core.errors import forbidden

    if not (ctx.can(P.CLINICAL_READ) or ctx.can(P.CLINIC_MANAGE)):  # definitions only — no patient data
        raise forbidden("You don't have access to order sets")


@router.get("/order-sets")
def list_sets(status: Literal["published", "all"] = "published", ctx: TenantContext = Depends(get_ctx)):
    _can_read(ctx)
    q = select(OrderSet).where(OrderSet.organization_id == ctx.org_id)
    if status == "published" or not ctx.can(P.CLINIC_MANAGE):
        q = q.where(OrderSet.status == "published")
    return [set_out(ctx, s) for s in ctx.db.scalars(q.order_by(OrderSet.name, OrderSet.version.desc()))]


@router.get("/order-sets/{sid}")
def get_set(sid: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    _can_read(ctx)
    s = _get(ctx, sid)
    if s.status != "published" and not ctx.can(P.CLINIC_MANAGE):
        raise not_found("Order set")
    return set_out(ctx, s)


@router.post("/order-sets", status_code=201)
def create_set(body: OrderSetIn, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    _validate(body.items)
    key = "".join(ch if ch.isalnum() else "-" for ch in body.name.lower()).strip("-")[:50] + "-" + uuid.uuid4().hex[:6]
    s = OrderSet(organization_id=ctx.org_id, key=key, version=1, name=body.name, category=body.category, description=body.description,
                 status="draft", is_demonstration=True, created_by_id=ctx.user.id)
    s.items = [OrderSetItem(organization_id=ctx.org_id, position=n, **it.model_dump()) for n, it in enumerate(body.items)]
    ctx.db.add(s)
    ctx.audit("orderset.created", resource_type="order_set", resource_id=s.id, details={"name": s.name})
    ctx.db.commit()
    return set_out(ctx, s)


@router.put("/order-sets/{sid}")
def update_set(sid: uuid.UUID, body: OrderSetIn, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    s = _get(ctx, sid)
    if s.status != "draft":
        raise bad_request("Only drafts can be edited. Create a new version of a published order set.")
    _validate(body.items)
    s.name, s.category, s.description = body.name, body.category, body.description
    s.items = [OrderSetItem(organization_id=ctx.org_id, position=n, **it.model_dump()) for n, it in enumerate(body.items)]
    ctx.audit("orderset.updated", resource_type="order_set", resource_id=s.id)
    ctx.db.commit()
    return set_out(ctx, s)


@router.post("/order-sets/{sid}/new-version", status_code=201)
def new_version(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    s = _get(ctx, sid)
    if ctx.db.scalar(select(OrderSet.id).where(OrderSet.organization_id == ctx.org_id, OrderSet.key == s.key, OrderSet.status == "draft")):
        raise bad_request("A draft version already exists")
    top = ctx.db.scalar(select(func.max(OrderSet.version)).where(OrderSet.organization_id == ctx.org_id, OrderSet.key == s.key))
    n = OrderSet(organization_id=ctx.org_id, key=s.key, version=top + 1, name=s.name, category=s.category, description=s.description,
                 status="draft", is_demonstration=s.is_demonstration, created_by_id=ctx.user.id)
    n.items = [OrderSetItem(organization_id=ctx.org_id, position=i.position, order_type=i.order_type, details=dict(i.details), priority=i.priority,
                            default_selected=i.default_selected, note=i.note) for i in s.items]
    ctx.db.add(n)
    ctx.audit("orderset.versioned", resource_type="order_set", resource_id=n.id, details={"from": str(s.id), "version": n.version})
    ctx.db.commit()
    return set_out(ctx, n)


@router.post("/order-sets/{sid}/publish")
def publish(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    s = _get(ctx, sid)
    if s.status != "draft":
        raise bad_request("Only drafts can be published")
    for old in ctx.db.scalars(select(OrderSet).where(OrderSet.organization_id == ctx.org_id, OrderSet.key == s.key, OrderSet.status == "published")):
        old.status = "retired"
    s.status, s.published_by_id, s.published_at = "published", ctx.user.id, now()
    ctx.audit("orderset.published", resource_type="order_set", resource_id=s.id, details={"version": s.version})
    ctx.db.commit()
    return set_out(ctx, s)


class ApplyItem(BaseModel):
    item_id: uuid.UUID
    details: dict | None = None           # clinician's edits for this order (validated)
    priority: Literal["routine", "urgent", "stat"] | None = None


class ApplyIn(BaseModel):
    patient_id: uuid.UUID
    encounter_id: uuid.UUID | None = None
    items: list[ApplyItem] = Field(min_length=1, max_length=40)
    indication_codes: list[str] = Field(default_factory=list, max_length=8)


@router.post("/order-sets/{sid}/apply", status_code=201)
def apply(sid: uuid.UUID, body: ApplyIn, ctx: TenantContext = Depends(require(P.ORDERS_WRITE))):
    s = _get(ctx, sid)
    if s.status != "published":
        raise bad_request("Only published order sets can be used")
    by_id = {i.id: i for i in s.items}
    unknown = [str(x.item_id) for x in body.items if x.item_id not in by_id]
    if unknown:
        raise bad_request("Item does not belong to this order set")
    from app.api.routers.orders import _normalize

    for x in body.items:  # validate everything first: either all draft orders are created or none
        it = by_id[x.item_id]
        _normalize(it.order_type, {**it.details, **(x.details or {})})
    created = []
    for x in body.items:
        it = by_id[x.item_id]
        details = {**it.details, **(x.details or {})}
        try:
            o = create_order(OrderIn(patient_id=body.patient_id, encounter_id=body.encounter_id, order_type=it.order_type, priority=x.priority or it.priority,
                                     details=details, indication_codes=body.indication_codes,
                                     notes=f"From order set: {s.name} v{s.version}"), ctx=ctx)
        except HTTPException:
            ctx.db.rollback()
            raise
        created.append(o)
    ctx.audit("orderset.applied", resource_type="order_set", resource_id=s.id, patient_id=body.patient_id,
              details={"version": s.version, "orders": [str(o.id) for o in created]})
    ctx.db.commit()
    return {"orders": created, "message": f"{len(created)} draft order(s) created. Review and sign each one."}
