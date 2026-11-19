"""Operating rooms & staff rostering API (B11)."""

import uuid
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import TenantContext, get_ctx, require
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import (
    Department,
    Location,
    ProviderProfile,
    Shift,
    StaffSkill,
    SurgicalCase,
    SwapRequest,
    TimeOff,
    User,
)
from app.services import audit
from app.services import rostering as RS
from app.services.patients import get_patient
from app.services.realtime import publish

router = APIRouter(tags=["or-roster"])


def _conflict(ctx, e: IntegrityError, what: str):
    ctx.db.rollback()
    msg = str(e.orig)
    if "no_room_overlap" in msg:
        raise bad_request("That OR room is booked (including turnover) at that time") from None
    if "no_surgeon_overlap" in msg:
        raise bad_request("The surgeon is already in another case at that time") from None
    if "shifts_no_overlap" in msg:
        raise bad_request("That person already has an overlapping shift") from None
    raise bad_request(f"Conflicting {what}") from None


# ======================= Operating rooms =======================

def case_out(c: SurgicalCase, rooms: dict) -> dict:
    return {"id": c.id, "room": {"id": c.or_room_id, "name": rooms.get(c.or_room_id)}, "patient": {"id": c.patient_id, "name": c.patient.full_name, "mrn": c.patient.mrn},
            "surgeon": c.surgeon.user.display_name, "surgeon_provider_id": c.surgeon_provider_id, "procedure": c.procedure, "procedure_code": c.procedure_code,
            "priority": c.priority, "anesthesia": c.anesthesia, "start_at": c.start_at, "end_at": c.end_at, "blocked_until": c.blocked_until,
            "turnover_minutes": c.turnover_minutes, "status": c.status, "cancel_reason": c.cancel_reason, "notes": c.notes}


@router.get("/or/schedule")
def or_schedule(day: date | None = None, ctx: TenantContext = Depends(get_ctx)):
    if not (ctx.can(P.OR_MANAGE) or ctx.can(P.CLINICAL_READ)):
        raise forbidden()
    rooms = ctx.db.scalars(select(Location).where(Location.organization_id == ctx.org_id, Location.kind == "or_room", Location.is_active.is_(True))
                           .order_by(Location.sort_order)).all()
    if ctx.facility_ids is not None:
        rooms = [r for r in rooms if r.facility_id in ctx.facility_ids]
    from zoneinfo import ZoneInfo

    from app.models import Clinic

    fac = ctx.db.get(Clinic, rooms[0].facility_id) if rooms else None
    tz = ZoneInfo(fac.timezone if fac else "UTC")
    d = day or now().astimezone(tz).date()
    start, end = datetime.combine(d, datetime.min.time(), tz), datetime.combine(d + timedelta(days=1), datetime.min.time(), tz)
    cases = ctx.db.scalars(select(SurgicalCase).where(SurgicalCase.organization_id == ctx.org_id, SurgicalCase.or_room_id.in_([r.id for r in rooms]),
                                                      SurgicalCase.start_at < end, SurgicalCase.end_at > start).order_by(SurgicalCase.start_at)).all()
    names = {r.id: r.name for r in rooms}
    booked = {r.id: sum((min(c.end_at, end) - max(c.start_at, start)).total_seconds() / 3600 for c in cases if c.or_room_id == r.id and c.status != "cancelled")
              for r in rooms}
    return {"day": d, "timezone": str(tz), "rooms": [{"id": r.id, "name": r.name, "booked_hours": round(booked[r.id], 1), "utilization_pct": round(100 * booked[r.id] / 10, 0)} for r in rooms],
            "cases": [case_out(c, names) for c in cases], "utilization_basis": "booked hours ÷ 10-hour staffed day"}


class CaseIn(BaseModel):
    or_room_id: uuid.UUID
    patient_id: uuid.UUID
    surgeon_provider_id: uuid.UUID
    procedure: str = Field(min_length=3, max_length=200)
    procedure_code: str | None = Field(default=None, max_length=10)
    priority: Literal["elective", "urgent", "emergent"] = "elective"
    anesthesia: Literal["general", "regional", "mac", "local"] = "general"
    start_at: datetime
    duration_minutes: int = Field(ge=15, le=720)
    turnover_minutes: int = Field(default=30, ge=0, le=240)
    notes: str | None = Field(default=None, max_length=1000)


@router.post("/or/cases", status_code=201)
def schedule_case(body: CaseIn, ctx: TenantContext = Depends(get_ctx)):
    if not (ctx.can(P.OR_MANAGE) or ctx.can(P.ORDERS_SIGN)):
        raise forbidden("Surgical scheduling is for OR managers and surgeons")
    room = ctx.db.get(Location, body.or_room_id)
    if not room or room.organization_id != ctx.org_id or room.kind != "or_room":
        raise not_found("OR room")
    ctx.require_facility(room.facility_id)
    get_patient(ctx, body.patient_id)
    sur = ctx.db.get(ProviderProfile, body.surgeon_provider_id)
    if not sur or sur.organization_id != ctx.org_id:
        raise bad_request("Unknown surgeon")
    end = body.start_at + timedelta(minutes=body.duration_minutes)
    c = SurgicalCase(organization_id=ctx.org_id, facility_id=room.facility_id, or_room_id=room.id, patient_id=body.patient_id, surgeon_provider_id=sur.id,
                     procedure=body.procedure, procedure_code=body.procedure_code, priority=body.priority, anesthesia=body.anesthesia, start_at=body.start_at,
                     end_at=end, turnover_minutes=body.turnover_minutes, blocked_until=end + timedelta(minutes=body.turnover_minutes), notes=body.notes,
                     created_by_id=ctx.user.id)
    ctx.db.add(c)
    try:
        ctx.db.flush()
    except IntegrityError as e:
        _conflict(ctx, e, "case")
    ctx.audit("or.case_scheduled", resource_type="surgical_case", resource_id=c.id, patient_id=c.patient_id)
    publish(ctx.db, ctx.org_id, "or", case_id=c.id)
    ctx.db.commit()
    return case_out(c, {room.id: room.name})


class CaseStatusIn(BaseModel):
    to: Literal["in_room", "completed", "cancelled"]
    reason: str | None = Field(default=None, max_length=300)


@router.post("/or/cases/{cid}/status")
def case_status(cid: uuid.UUID, body: CaseStatusIn, ctx: TenantContext = Depends(get_ctx)):
    if not (ctx.can(P.OR_MANAGE) or ctx.can(P.ORDERS_SIGN) or ctx.can(P.NURSING_WRITE)):
        raise forbidden()
    c = ctx.db.get(SurgicalCase, cid)
    if not c or c.organization_id != ctx.org_id:
        raise not_found("Case")
    allowed = {"scheduled": {"in_room", "cancelled"}, "in_room": {"completed"}}
    if body.to not in allowed.get(c.status, set()):
        raise bad_request(f"A {c.status} case can't move to {body.to}")
    if body.to == "cancelled" and not body.reason:
        raise bad_request("Give a reason for cancelling")
    c.status = body.to
    if body.to == "in_room":
        c.in_room_at = now()
    if body.to == "completed":
        c.completed_at = now()
    c.cancel_reason = body.reason if body.to == "cancelled" else c.cancel_reason
    ctx.audit(f"or.case_{body.to}", resource_type="surgical_case", resource_id=c.id, patient_id=c.patient_id)
    publish(ctx.db, ctx.org_id, "or", case_id=c.id)
    ctx.db.commit()
    return {"status": c.status}


# ======================= Rostering =======================

def shift_out(s: Shift, depts: dict) -> dict:
    return {"id": s.id, "user_id": s.user_id, "name": s.user.display_name, "role": s.role, "department_id": s.department_id, "department": depts.get(s.department_id),
            "start_at": s.start_at, "end_at": s.end_at, "status": s.status, "notes": s.notes}


@router.get("/roster")
def roster(start: date | None = None, days: int = 3, department_id: uuid.UUID | None = None, ctx: TenantContext = Depends(require(P.ROSTER_SELF))):
    s0 = datetime.combine(start or now().date(), datetime.min.time()).astimezone()
    s1 = s0 + timedelta(days=min(days, 14))
    q = select(Shift).where(Shift.organization_id == ctx.org_id, Shift.status == "scheduled", Shift.start_at < s1, Shift.end_at > s0)
    if department_id:
        q = q.where(Shift.department_id == department_id)
    elif not ctx.can(P.ROSTER_MANAGE):
        q = q.where(Shift.user_id == ctx.user.id)
    depts = {d.id: d.name for d in ctx.db.scalars(select(Department).where(Department.organization_id == ctx.org_id))}
    gaps = RS.gaps(ctx.db, ctx.org_id, hours_ahead=min(days, 3) * 24) if ctx.can(P.ROSTER_MANAGE) else []
    swaps = ctx.db.scalars(select(SwapRequest).where(SwapRequest.organization_id == ctx.org_id, SwapRequest.status.in_(("open", "accepted")))).all()
    return {"shifts": [shift_out(x, depts) for x in ctx.db.scalars(q.order_by(Shift.start_at))], "gaps": gaps,
            "swaps": [{"id": w.id, "shift_id": w.shift_id, "status": w.status, "reason": w.reason, "requested_by_id": w.requested_by_id,
                       "target_user_id": w.target_user_id, "created_at": w.created_at} for w in swaps],
            "rules": {"min_rest_hours": RS.MIN_REST_HOURS, "max_week_hours": RS.MAX_WEEK_HOURS}}


class ShiftIn(BaseModel):
    user_id: uuid.UUID
    department_id: uuid.UUID
    role: str = Field(min_length=2, max_length=30)
    start_at: datetime
    end_at: datetime
    notes: str | None = Field(default=None, max_length=300)
    override_rules: bool = False
    override_reason: str | None = Field(default=None, max_length=300)


@router.post("/roster/shifts", status_code=201)
def create_shift(body: ShiftIn, ctx: TenantContext = Depends(require(P.ROSTER_MANAGE))):
    dept = ctx.db.get(Department, body.department_id)
    if not dept or dept.organization_id != ctx.org_id:
        raise not_found("Department")
    ctx.require_facility(dept.facility_id)
    ok, reasons, _ = RS.check_candidate(ctx.db, body.user_id, body.start_at, body.end_at)
    if not ok:
        if "overlapping" in reasons[0] or not body.override_rules:
            raise bad_request(f"Can't schedule: {reasons[0]}" + ("" if "overlapping" in reasons[0] else " (a manager may override with a reason)"))
        if not body.override_reason:
            raise bad_request("Give a reason to override the scheduling rule")
    s = Shift(organization_id=ctx.org_id, facility_id=dept.facility_id, department_id=dept.id, user_id=body.user_id, role=body.role, start_at=body.start_at,
              end_at=body.end_at, notes=body.notes or body.override_reason, created_by_id=ctx.user.id)
    ctx.db.add(s)
    try:
        ctx.db.flush()
    except IntegrityError as e:
        _conflict(ctx, e, "shift")
    ctx.audit("roster.shift_created", resource_type="shift", resource_id=s.id, details={"override": body.override_rules and not ok, "rule": reasons[0] if not ok else None})
    publish(ctx.db, ctx.org_id, "roster", department_id=dept.id)
    ctx.db.commit()
    return shift_out(s, {dept.id: dept.name})


@router.post("/roster/shifts/{sid}/cancel")
def cancel_shift(sid: uuid.UUID, ctx: TenantContext = Depends(require(P.ROSTER_MANAGE))):
    s = ctx.db.get(Shift, sid)
    if not s or s.organization_id != ctx.org_id:
        raise not_found("Shift")
    s.status = "cancelled"
    ctx.audit("roster.shift_cancelled", resource_type="shift", resource_id=s.id)
    publish(ctx.db, ctx.org_id, "roster", department_id=s.department_id)
    ctx.db.commit()
    return {"status": "cancelled"}


@router.get("/roster/suggest")
def suggest(department_id: uuid.UUID, role: str, start: datetime, end: datetime, skill: str | None = None,
            ctx: TenantContext = Depends(require(P.ROSTER_MANAGE))):
    dept = ctx.db.get(Department, department_id)
    if not dept or dept.organization_id != ctx.org_id:
        raise not_found("Department")
    return {"candidates": RS.suggest(ctx.db, ctx.org_id, dept, role, start, end, skill), "method": "Hard rules filter (role, overlap, time off, "
            f"≥{RS.MIN_REST_HOURS} h rest, ≤{RS.MAX_WEEK_HOURS} h/7 days, credentials) then rank by fewest hours this week"}


class SwapIn(BaseModel):
    shift_id: uuid.UUID
    target_user_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, max_length=300)


@router.post("/roster/swaps", status_code=201)
def request_swap(body: SwapIn, ctx: TenantContext = Depends(require(P.ROSTER_SELF))):
    s = ctx.db.get(Shift, body.shift_id)
    if not s or s.organization_id != ctx.org_id or s.status != "scheduled":
        raise not_found("Shift")
    if s.user_id != ctx.user.id:
        raise forbidden("You can only offer your own shifts")
    w = SwapRequest(organization_id=ctx.org_id, shift_id=s.id, requested_by_id=ctx.user.id, target_user_id=body.target_user_id, reason=body.reason)
    ctx.db.add(w)
    ctx.db.commit()
    return {"id": w.id, "status": w.status}


@router.post("/roster/swaps/{wid}/accept")
def accept_swap(wid: uuid.UUID, ctx: TenantContext = Depends(require(P.ROSTER_SELF))):
    w = ctx.db.get(SwapRequest, wid)
    if not w or w.organization_id != ctx.org_id or w.status != "open":
        raise not_found("Swap request")
    if w.requested_by_id == ctx.user.id or (w.target_user_id and w.target_user_id != ctx.user.id):
        raise forbidden("This swap isn't offered to you")
    s = ctx.db.get(Shift, w.shift_id)
    ok, reasons, _ = RS.check_candidate(ctx.db, ctx.user.id, s.start_at, s.end_at)
    if not ok:
        raise bad_request(f"You can't take this shift: {reasons[0]}")
    w.target_user_id, w.status = ctx.user.id, "accepted"
    ctx.db.commit()
    return {"status": w.status}


class DecideIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=300)


@router.post("/roster/swaps/{wid}/decide")
def decide_swap(wid: uuid.UUID, body: DecideIn, ctx: TenantContext = Depends(require(P.ROSTER_MANAGE))):
    w = ctx.db.get(SwapRequest, wid)
    if not w or w.organization_id != ctx.org_id or w.status != "accepted":
        raise bad_request("Only accepted swaps can be approved")
    s = ctx.db.get(Shift, w.shift_id)
    if body.approve:
        ok, reasons, _ = RS.check_candidate(ctx.db, w.target_user_id, s.start_at, s.end_at, exclude_shift_id=s.id)
        if not ok:
            raise bad_request(f"Can't approve: {reasons[0]}")
        s.user_id = w.target_user_id
        try:
            ctx.db.flush()
        except IntegrityError as e:
            _conflict(ctx, e, "shift")
    w.status, w.decided_by_id, w.decided_at = ("approved" if body.approve else "rejected"), ctx.user.id, now()
    audit.record(ctx.db, f"roster.swap_{w.status}", org_id=ctx.org_id, actor_id=ctx.user.id, resource_type="shift", resource_id=s.id)
    ctx.db.commit()
    return {"status": w.status}


class SkillIn(BaseModel):
    user_id: uuid.UUID
    skill: str = Field(min_length=2, max_length=40)
    expires_on: date | None = None


@router.post("/roster/skills", status_code=201)
def add_skill(body: SkillIn, ctx: TenantContext = Depends(require(P.ROSTER_MANAGE))):
    if not ctx.db.scalar(select(User.id).where(User.id == body.user_id)):
        raise bad_request("Unknown user")
    ex = ctx.db.scalar(select(StaffSkill).where(StaffSkill.user_id == body.user_id, StaffSkill.skill == body.skill))
    if ex:
        ex.expires_on = body.expires_on
    else:
        ctx.db.add(StaffSkill(organization_id=ctx.org_id, **body.model_dump()))
    ctx.db.commit()
    return {"message": "Saved"}


class TimeOffIn(BaseModel):
    start_at: datetime
    end_at: datetime
    reason: str | None = Field(default=None, max_length=200)


@router.post("/roster/time-off", status_code=201)
def time_off(body: TimeOffIn, ctx: TenantContext = Depends(require(P.ROSTER_SELF))):
    if body.end_at <= body.start_at:
        raise bad_request("End must be after start")
    ctx.db.add(TimeOff(organization_id=ctx.org_id, user_id=ctx.user.id, **body.model_dump()))
    ctx.db.commit()
    return {"message": "Time off recorded"}
