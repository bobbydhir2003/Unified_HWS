"""Hospital structure: facilities (stored in `clinics`), departments, and the location tree (unit → room → bed)."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import TenantContext, get_ctx, require
from app.core.errors import bad_request, conflict, not_found
from app.core.permissions import P
from app.models import Clinic, Department, Location
from app.models.facility import DEPARTMENT_KINDS, FACILITY_TYPES, LOCATION_KINDS

router = APIRouter(tags=["facilities"])

FacilityType = Literal[FACILITY_TYPES]  # type: ignore[valid-type]
DepartmentKind = Literal[DEPARTMENT_KINDS]  # type: ignore[valid-type]
LocationKind = Literal[LOCATION_KINDS]  # type: ignore[valid-type]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FacilityOut(ORM):
    id: uuid.UUID
    name: str
    code: str
    facility_type: str
    timezone: str
    is_active: bool
    settings: dict
    department_count: int = 0
    bed_count: int = 0


class FacilityPatch(BaseModel):
    facility_type: FacilityType | None = None
    settings: dict | None = None


class DepartmentOut(ORM):
    id: uuid.UUID
    facility_id: uuid.UUID
    name: str
    code: str
    kind: str
    is_active: bool
    settings: dict


class DepartmentIn(BaseModel):
    facility_id: uuid.UUID
    name: str = Field(min_length=2, max_length=120)
    code: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    kind: DepartmentKind = "outpatient"
    is_active: bool = True


class DepartmentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    kind: DepartmentKind | None = None
    is_active: bool | None = None
    settings: dict | None = None


class LocationOut(ORM):
    id: uuid.UUID
    facility_id: uuid.UUID
    department_id: uuid.UUID | None
    parent_id: uuid.UUID | None
    kind: str
    name: str
    code: str
    sort_order: int
    is_active: bool
    attributes: dict
    bed_status: str | None


class LocationIn(BaseModel):
    facility_id: uuid.UUID
    department_id: uuid.UUID | None = None
    parent_id: uuid.UUID | None = None
    kind: LocationKind
    name: str = Field(min_length=1, max_length=80)
    code: str = Field(min_length=1, max_length=40)
    sort_order: int = 0
    attributes: dict = {}


class LocationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    department_id: uuid.UUID | None = None
    is_active: bool | None = None
    attributes: dict | None = None
    sort_order: int | None = None


class GenerateBeds(BaseModel):
    rooms: int = Field(ge=1, le=60)
    beds_per_room: int = Field(ge=1, le=6)
    room_prefix: str = Field(default="", max_length=10)
    start_number: int = Field(default=1, ge=0, le=9999)


VALID_PARENT = {"room": {"unit"}, "bed": {"room", "unit", "bay"}, "bay": {"unit"}, "or_room": {"unit", "area"},
                "storage": {"unit", "area"}, "unit": set(), "area": set()}


def _facility(ctx: TenantContext, facility_id: uuid.UUID) -> Clinic:
    f = ctx.db.get(Clinic, facility_id)
    if not f or f.organization_id != ctx.org_id:
        raise not_found("Facility")
    ctx.require_facility(f.id)
    return f


def _department(ctx: TenantContext, dept_id: uuid.UUID) -> Department:
    d = ctx.db.get(Department, dept_id)
    if not d or d.organization_id != ctx.org_id:
        raise not_found("Department")
    ctx.require_facility(d.facility_id)
    return d


def _location(ctx: TenantContext, loc_id: uuid.UUID) -> Location:
    loc = ctx.db.get(Location, loc_id)
    if not loc or loc.organization_id != ctx.org_id:
        raise not_found("Location")
    ctx.require_facility(loc.facility_id)
    return loc


# ---------- Facilities ----------

@router.get("/facilities", response_model=list[FacilityOut])
def list_facilities(ctx: TenantContext = Depends(get_ctx)):
    q = select(Clinic).where(Clinic.organization_id == ctx.org_id, Clinic.is_active.is_(True)).order_by(Clinic.name)
    if ctx.facility_ids is not None:
        q = q.where(Clinic.id.in_(ctx.facility_ids))
    facilities = ctx.db.scalars(q).all()
    ids = [f.id for f in facilities]
    depts = dict(ctx.db.execute(select(Department.facility_id, func.count()).where(Department.facility_id.in_(ids), Department.is_active.is_(True))
                                .group_by(Department.facility_id)).all())
    beds = dict(ctx.db.execute(select(Location.facility_id, func.count()).where(Location.facility_id.in_(ids), Location.kind == "bed",
                                                                                 Location.is_active.is_(True)).group_by(Location.facility_id)).all())
    out = []
    for f in facilities:
        o = FacilityOut.model_validate(f)
        o.department_count, o.bed_count = depts.get(f.id, 0), beds.get(f.id, 0)
        out.append(o)
    return out


@router.patch("/facilities/{facility_id}", response_model=FacilityOut)
def update_facility(facility_id: uuid.UUID, body: FacilityPatch, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    f = _facility(ctx, facility_id)
    if body.facility_type:
        f.facility_type = body.facility_type
    if body.settings is not None:
        f.settings = {**(f.settings or {}), **body.settings}
    ctx.audit("facility.updated", resource_type="facility", resource_id=f.id, details=body.model_dump(exclude_none=True))
    ctx.db.commit()
    return FacilityOut.model_validate(f)


# ---------- Departments ----------

@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(facility_id: uuid.UUID | None = None, kind: str | None = None, ctx: TenantContext = Depends(get_ctx)):
    q = select(Department).where(Department.organization_id == ctx.org_id).order_by(Department.name)
    if facility_id:
        _facility(ctx, facility_id)
        q = q.where(Department.facility_id == facility_id)
    elif ctx.facility_ids is not None:
        q = q.where(Department.facility_id.in_(ctx.facility_ids))
    if kind:
        q = q.where(Department.kind == kind)
    return ctx.db.scalars(q).all()


@router.post("/departments", response_model=DepartmentOut, status_code=201)
def create_department(body: DepartmentIn, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    _facility(ctx, body.facility_id)
    d = Department(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(d)
    try:
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise conflict("A department with that code already exists in this facility") from None
    ctx.audit("department.created", resource_type="department", resource_id=d.id)
    ctx.db.commit()
    return d


@router.patch("/departments/{dept_id}", response_model=DepartmentOut)
def update_department(dept_id: uuid.UUID, body: DepartmentPatch, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    d = _department(ctx, dept_id)
    data = body.model_dump(exclude_none=True)
    if "settings" in data:
        data["settings"] = {**(d.settings or {}), **data["settings"]}
    for k, v in data.items():
        setattr(d, k, v)
    ctx.audit("department.updated", resource_type="department", resource_id=d.id, details={k: v for k, v in data.items() if k != "settings"})
    ctx.db.commit()
    return d


# ---------- Locations ----------

@router.get("/locations", response_model=list[LocationOut])
def list_locations(facility_id: uuid.UUID, kind: str | None = None, parent_id: uuid.UUID | None = None,
                   ctx: TenantContext = Depends(get_ctx)):
    _facility(ctx, facility_id)
    q = select(Location).where(Location.facility_id == facility_id, Location.organization_id == ctx.org_id)
    if kind:
        q = q.where(Location.kind == kind)
    if parent_id:
        q = q.where(Location.parent_id == parent_id)
    return ctx.db.scalars(q.order_by(Location.kind, Location.sort_order, Location.code)).all()


def _check_parent(ctx: TenantContext, kind: str, parent_id: uuid.UUID | None, facility_id: uuid.UUID) -> Location | None:
    if parent_id is None:
        if kind in ("room", "bed", "bay"):
            raise bad_request(f"A {kind} must belong to a parent location")
        return None
    parent = _location(ctx, parent_id)
    if parent.facility_id != facility_id:
        raise bad_request("Parent location belongs to a different facility")
    if parent.kind not in VALID_PARENT.get(kind, set()):
        raise bad_request(f"A {kind} cannot be placed inside a {parent.kind}")
    return parent


@router.post("/locations", response_model=LocationOut, status_code=201)
def create_location(body: LocationIn, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    _facility(ctx, body.facility_id)
    parent = _check_parent(ctx, body.kind, body.parent_id, body.facility_id)
    if body.department_id:
        if _department(ctx, body.department_id).facility_id != body.facility_id:
            raise bad_request("Department belongs to a different facility")
    data = body.model_dump()
    if parent and not data["department_id"]:
        data["department_id"] = parent.department_id
    loc = Location(organization_id=ctx.org_id, **data, bed_status="available" if body.kind == "bed" else None)
    ctx.db.add(loc)
    try:
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise conflict("A location with that code already exists in this facility") from None
    ctx.audit("location.created", resource_type="location", resource_id=loc.id, details={"kind": loc.kind, "code": loc.code})
    ctx.db.commit()
    return loc


@router.patch("/locations/{loc_id}", response_model=LocationOut)
def update_location(loc_id: uuid.UUID, body: LocationPatch, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    loc = _location(ctx, loc_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("department_id") and _department(ctx, data["department_id"]).facility_id != loc.facility_id:
        raise bad_request("Department belongs to a different facility")
    for k, v in data.items():
        setattr(loc, k, v)
    ctx.audit("location.updated", resource_type="location", resource_id=loc.id, details={k: str(v) for k, v in data.items()})
    ctx.db.commit()
    return loc


@router.post("/locations/{unit_id}/generate", response_model=list[LocationOut], status_code=201)
def generate_rooms(unit_id: uuid.UUID, body: GenerateBeds, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    """Create `rooms` rooms with `beds_per_room` beds each under a unit (codes: UNIT-ROOM-A/B…)."""
    unit = _location(ctx, unit_id)
    if unit.kind != "unit":
        raise bad_request("Rooms can only be generated inside a unit")
    created: list[Location] = []
    for i in range(body.rooms):
        num = f"{body.room_prefix}{body.start_number + i}"
        room = Location(organization_id=ctx.org_id, facility_id=unit.facility_id, department_id=unit.department_id, parent_id=unit.id,
                        kind="room", name=f"Room {num}", code=f"{unit.code}-{num}", sort_order=i)
        ctx.db.add(room)
        ctx.db.flush()
        created.append(room)
        for b in range(body.beds_per_room):
            letter = chr(ord("A") + b)
            bed = Location(organization_id=ctx.org_id, facility_id=unit.facility_id, department_id=unit.department_id, parent_id=room.id,
                           kind="bed", name=f"{num}{letter}", code=f"{unit.code}-{num}{letter}", sort_order=b, bed_status="available")
            ctx.db.add(bed)
            created.append(bed)
    try:
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise conflict("Some generated codes already exist; choose a different start number or prefix") from None
    ctx.audit("location.generated", resource_type="location", resource_id=unit.id, details={"rooms": body.rooms, "beds_per_room": body.beds_per_room})
    ctx.db.commit()
    return created
