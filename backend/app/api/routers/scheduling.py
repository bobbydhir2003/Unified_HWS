import uuid
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, select

from app.api.deps import TenantContext, require
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import (
    Appointment,
    AppointmentType,
    Clinic,
    Encounter,
    ProviderAvailability,
    ProviderProfile,
    User,
)
from app.models.scheduling import INACTIVE_APPOINTMENT_STATUSES
from app.schemas.common import ORM
from app.services.notify import notify
from app.services.patients import get_patient

router = APIRouter(tags=["scheduling"])


# ---------- Schemas ----------

class AppointmentTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    duration_minutes: int = Field(ge=5, le=480)
    color: str = "blue"
    is_telehealth: bool = False
    is_active: bool = True


class AppointmentTypeOut(AppointmentTypeIn, ORM):
    id: uuid.UUID


class AvailabilityBlock(BaseModel):
    clinic_id: uuid.UUID
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time


class ProviderOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    credentials: str | None
    specialty: str | None
    color: str
    accepts_new_patients: bool
    availability: list[AvailabilityBlock]


class AppointmentIn(BaseModel):
    patient_id: uuid.UUID
    provider_id: uuid.UUID
    clinic_id: uuid.UUID
    appointment_type_id: uuid.UUID | None = None
    start_at: datetime
    end_at: datetime | None = None
    mode: Literal["in_person", "telehealth"] = "in_person"
    reason: str | None = Field(default=None, max_length=300)
    notes: str | None = None
    override_availability: bool = False

    @model_validator(mode="after")
    def tz_aware(self):
        if self.start_at.tzinfo is None:
            raise ValueError("start_at must include a timezone offset")
        return self


class AppointmentUpdate(BaseModel):
    provider_id: uuid.UUID | None = None
    clinic_id: uuid.UUID | None = None
    appointment_type_id: uuid.UUID | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    mode: Literal["in_person", "telehealth"] | None = None
    reason: str | None = None
    notes: str | None = None
    override_availability: bool = False


class StatusAction(BaseModel):
    action: Literal["confirm", "check_in", "room", "check_out", "cancel", "no_show"]
    room: str | None = None
    reason: str | None = None


class PersonRef(BaseModel):
    id: uuid.UUID
    name: str


class AppointmentOut(BaseModel):
    id: uuid.UUID
    patient: dict
    provider: PersonRef
    clinic: PersonRef
    appointment_type: AppointmentTypeOut | None
    start_at: datetime
    end_at: datetime
    status: str
    mode: str
    reason: str | None
    notes: str | None
    room: str | None
    cancel_reason: str | None
    checked_in_at: datetime | None
    roomed_at: datetime | None
    checked_out_at: datetime | None
    encounter_id: uuid.UUID | None = None
    created_at: datetime


def appointment_out(a: Appointment, encounter_id: uuid.UUID | None = None) -> AppointmentOut:
    p = a.patient
    return AppointmentOut(
        id=a.id,
        patient={"id": p.id, "name": p.full_name, "mrn": p.mrn, "date_of_birth": p.date_of_birth,
                 "sex_at_birth": p.sex_at_birth, "phone": p.phone, "is_restricted": p.is_restricted},
        provider=PersonRef(id=a.provider.id, name=a.provider.user.display_name),
        clinic=PersonRef(id=a.clinic.id, name=a.clinic.name),
        appointment_type=AppointmentTypeOut.model_validate(a.appointment_type) if a.appointment_type else None,
        start_at=a.start_at, end_at=a.end_at, status=a.status, mode=a.mode, reason=a.reason, notes=a.notes,
        room=a.room, cancel_reason=a.cancel_reason, checked_in_at=a.checked_in_at, roomed_at=a.roomed_at,
        checked_out_at=a.checked_out_at, encounter_id=encounter_id, created_at=a.created_at,
    )


def _with_encounters(ctx: TenantContext, appts: list[Appointment]) -> list[AppointmentOut]:
    enc = dict(ctx.db.execute(select(Encounter.appointment_id, Encounter.id)
                              .where(Encounter.appointment_id.in_([a.id for a in appts]))).all())
    return [appointment_out(a, enc.get(a.id)) for a in appts]


# ---------- Appointment types ----------

@router.get("/appointment-types", response_model=list[AppointmentTypeOut])
def list_types(ctx: TenantContext = Depends(require(P.SCHEDULE_READ))):
    return ctx.db.scalars(select(AppointmentType).where(AppointmentType.organization_id == ctx.org_id)
                          .order_by(AppointmentType.name)).all()


@router.post("/appointment-types", response_model=AppointmentTypeOut, status_code=201)
def create_type(body: AppointmentTypeIn, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    t = AppointmentType(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(t)
    ctx.audit("schedule.type_created", resource_type="appointment_type", resource_id=None)
    ctx.db.commit()
    return t


@router.put("/appointment-types/{type_id}", response_model=AppointmentTypeOut)
def update_type(type_id: uuid.UUID, body: AppointmentTypeIn, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    t = ctx.db.get(AppointmentType, type_id)
    if not t or t.organization_id != ctx.org_id:
        raise not_found("Appointment type")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    ctx.db.commit()
    return t


# ---------- Providers & availability ----------

def _provider(ctx: TenantContext, provider_id: uuid.UUID) -> ProviderProfile:
    pr = ctx.db.get(ProviderProfile, provider_id)
    if not pr or pr.organization_id != ctx.org_id:
        raise not_found("Provider")
    return pr


@router.get("/providers", response_model=list[ProviderOut])
def list_providers(ctx: TenantContext = Depends(require(P.SCHEDULE_READ))):
    provs = ctx.db.scalars(select(ProviderProfile).join(User, User.id == ProviderProfile.user_id)
                           .where(ProviderProfile.organization_id == ctx.org_id, ProviderProfile.is_active.is_(True))
                           .order_by(User.last_name)).all()
    avail = ctx.db.scalars(select(ProviderAvailability).where(ProviderAvailability.organization_id == ctx.org_id)
                           .order_by(ProviderAvailability.weekday, ProviderAvailability.start_time)).all()
    by_p: dict[uuid.UUID, list[AvailabilityBlock]] = {}
    for a in avail:
        by_p.setdefault(a.provider_id, []).append(AvailabilityBlock(
            clinic_id=a.clinic_id, weekday=a.weekday, start_time=a.start_time, end_time=a.end_time))
    return [ProviderOut(id=p.id, user_id=p.user_id, name=p.user.display_name, credentials=p.credentials,
                        specialty=p.specialty, color=p.color, accepts_new_patients=p.accepts_new_patients,
                        availability=by_p.get(p.id, [])) for p in provs]


@router.put("/providers/{provider_id}/availability", response_model=list[AvailabilityBlock])
def set_availability(provider_id: uuid.UUID, blocks: list[AvailabilityBlock],
                     ctx: TenantContext = Depends(require(P.SCHEDULE_READ))):
    pr = _provider(ctx, provider_id)
    if not (ctx.can(P.CLINIC_MANAGE) or pr.user_id == ctx.user.id):
        ctx.require(P.CLINIC_MANAGE)
    for b in blocks:
        if b.end_time <= b.start_time:
            raise bad_request("Each block must end after it starts")
        c = ctx.db.get(Clinic, b.clinic_id)
        if not c or c.organization_id != ctx.org_id:
            raise bad_request("Unknown clinic")
    ctx.db.query(ProviderAvailability).filter(ProviderAvailability.provider_id == pr.id).delete()
    for b in blocks:
        ctx.db.add(ProviderAvailability(organization_id=ctx.org_id, provider_id=pr.id, **b.model_dump()))
    ctx.audit("schedule.availability_updated", resource_type="provider", resource_id=pr.id)
    ctx.db.commit()
    return blocks


def _within_availability(ctx: TenantContext, provider_id: uuid.UUID, clinic: Clinic, start: datetime, end: datetime) -> bool:
    tz = ZoneInfo(clinic.timezone)
    ls, le = start.astimezone(tz), end.astimezone(tz)
    if ls.date() != le.date() and le.time() != time(0):
        return False
    blocks = ctx.db.scalars(select(ProviderAvailability).where(
        ProviderAvailability.provider_id == provider_id, ProviderAvailability.clinic_id == clinic.id,
        ProviderAvailability.weekday == ls.weekday())).all()
    return any(b.start_time <= ls.time() and le.time() <= b.end_time for b in blocks)


@router.get("/providers/{provider_id}/slots")
def open_slots(provider_id: uuid.UUID, clinic_id: uuid.UUID, day: date, duration: int = Query(20, ge=5, le=240),
               ctx: TenantContext = Depends(require(P.SCHEDULE_READ))):
    pr = _provider(ctx, provider_id)
    clinic = ctx.db.get(Clinic, clinic_id)
    if not clinic or clinic.organization_id != ctx.org_id:
        raise not_found("Clinic")
    tz = ZoneInfo(clinic.timezone)
    blocks = ctx.db.scalars(select(ProviderAvailability).where(
        ProviderAvailability.provider_id == pr.id, ProviderAvailability.clinic_id == clinic.id,
        ProviderAvailability.weekday == day.weekday())).all()
    day_start = datetime.combine(day, time(0), tz)
    busy = ctx.db.execute(select(Appointment.start_at, Appointment.end_at).where(
        Appointment.provider_id == pr.id, Appointment.status.not_in(INACTIVE_APPOINTMENT_STATUSES),
        Appointment.start_at < day_start + timedelta(days=1), Appointment.end_at > day_start)).all()
    slots, step, cutoff = [], timedelta(minutes=15), now()
    for b in blocks:
        t = datetime.combine(day, b.start_time, tz)
        block_end = datetime.combine(day, b.end_time, tz)
        while t + timedelta(minutes=duration) <= block_end:
            e = t + timedelta(minutes=duration)
            if t > cutoff and not any(s < e and t < en for s, en in busy):
                slots.append(t.isoformat())
            t += step
    return {"provider_id": pr.id, "clinic_id": clinic.id, "date": day, "timezone": clinic.timezone, "slots": slots}


# ---------- Appointments ----------

def _resolve(ctx: TenantContext, clinic_id, provider_id, type_id) -> tuple[Clinic, ProviderProfile, AppointmentType | None]:
    clinic = ctx.db.get(Clinic, clinic_id)
    if not clinic or clinic.organization_id != ctx.org_id:
        raise not_found("Clinic")
    ctx.require_clinic(clinic.id)
    pr = _provider(ctx, provider_id)
    at = None
    if type_id:
        at = ctx.db.get(AppointmentType, type_id)
        if not at or at.organization_id != ctx.org_id:
            raise not_found("Appointment type")
    return clinic, pr, at


def _check_conflicts(ctx: TenantContext, provider_id, patient_id, start, end, exclude_id=None) -> None:
    base = [Appointment.status.not_in(INACTIVE_APPOINTMENT_STATUSES), Appointment.start_at < end, Appointment.end_at > start]
    if exclude_id:
        base.append(Appointment.id != exclude_id)
    clash = ctx.db.scalar(select(Appointment).where(Appointment.provider_id == provider_id, *base))
    if clash:
        tz = ZoneInfo(clash.clinic.timezone)
        s_, e_ = clash.start_at.astimezone(tz), clash.end_at.astimezone(tz)
        raise HTTPException(409, {"code": "provider_conflict",
                                  "message": f"{clash.provider.user.display_name} is already booked "
                                             f"{s_:%-I:%M}–{e_:%-I:%M %p} ({clash.clinic.timezone}). Choose another time.",
                                  "conflict_id": str(clash.id)})
    pclash = ctx.db.scalar(select(Appointment).where(Appointment.patient_id == patient_id, *base))
    if pclash:
        raise HTTPException(409, {"code": "patient_conflict",
                                  "message": "This patient already has an overlapping appointment.",
                                  "conflict_id": str(pclash.id)})


@router.get("/appointments", response_model=list[AppointmentOut])
def list_appointments(
    start: datetime, end: datetime, provider_id: list[uuid.UUID] | None = Query(None),
    clinic_id: uuid.UUID | None = None, patient_id: uuid.UUID | None = None, include_cancelled: bool = False,
    ctx: TenantContext = Depends(require(P.SCHEDULE_READ)),
):
    if end - start > timedelta(days=62):
        raise bad_request("Date range too large (max 62 days)")
    q = select(Appointment).where(Appointment.organization_id == ctx.org_id, Appointment.start_at < end,
                                  Appointment.end_at > start)
    if provider_id:
        q = q.where(Appointment.provider_id.in_(provider_id))
    if clinic_id:
        ctx.require_clinic(clinic_id)
        q = q.where(Appointment.clinic_id == clinic_id)
    elif ctx.clinic_ids is not None:
        q = q.where(Appointment.clinic_id.in_(ctx.clinic_ids))
    if patient_id:
        q = q.where(Appointment.patient_id == patient_id)
    if not include_cancelled:
        q = q.where(Appointment.status.not_in(INACTIVE_APPOINTMENT_STATUSES))
    return _with_encounters(ctx, ctx.db.scalars(q.order_by(Appointment.start_at)).all())


@router.post("/appointments", response_model=AppointmentOut, status_code=201)
def create_appointment(body: AppointmentIn, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    patient = get_patient(ctx, body.patient_id)
    if patient.status != "active":
        raise bad_request(f"Patient is {patient.status}; appointments can only be booked for active patients")
    clinic, pr, at = _resolve(ctx, body.clinic_id, body.provider_id, body.appointment_type_id)
    end = body.end_at or body.start_at + timedelta(minutes=at.duration_minutes if at else 20)
    if end <= body.start_at:
        raise bad_request("Appointment must end after it starts")
    if body.start_at < now() - timedelta(hours=12):
        raise bad_request("Cannot book appointments in the past")
    if not body.override_availability and not _within_availability(ctx, pr.id, clinic, body.start_at, end):
        raise HTTPException(409, {"code": "outside_availability",
                                  "message": "This time is outside the provider's scheduled hours at this clinic."})
    _check_conflicts(ctx, pr.id, patient.id, body.start_at, end)
    mode = "telehealth" if (at and at.is_telehealth) else body.mode
    a = Appointment(organization_id=ctx.org_id, clinic_id=clinic.id, patient_id=patient.id, provider_id=pr.id,
                    appointment_type_id=at.id if at else None, start_at=body.start_at, end_at=end, mode=mode,
                    reason=body.reason, notes=body.notes, booked_by_id=ctx.user.id)
    ctx.db.add(a)
    ctx.db.flush()  # exclusion constraint is the final guard against races
    ctx.audit("appointment.created", resource_type="appointment", resource_id=a.id, patient_id=patient.id,
              details={"override_availability": body.override_availability})
    ctx.db.commit()
    ctx.db.refresh(a)
    return appointment_out(a)


def _get_appt(ctx: TenantContext, appt_id: uuid.UUID) -> Appointment:
    a = ctx.db.get(Appointment, appt_id)
    if not a or a.organization_id != ctx.org_id:
        raise not_found("Appointment")
    ctx.require_clinic(a.clinic_id)
    return a


@router.get("/appointments/{appt_id}", response_model=AppointmentOut)
def get_appointment(appt_id: uuid.UUID, ctx: TenantContext = Depends(require(P.SCHEDULE_READ))):
    return _with_encounters(ctx, [_get_appt(ctx, appt_id)])[0]


@router.patch("/appointments/{appt_id}", response_model=AppointmentOut)
def update_appointment(appt_id: uuid.UUID, body: AppointmentUpdate, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    a = _get_appt(ctx, appt_id)
    if a.status not in ("scheduled", "confirmed"):
        raise bad_request(f"Appointments that are {a.status.replace('_', ' ')} can't be rescheduled")
    data = body.model_dump(exclude_unset=True, exclude={"override_availability"})
    clinic, pr, at = _resolve(ctx, data.get("clinic_id", a.clinic_id), data.get("provider_id", a.provider_id),
                              data.get("appointment_type_id", a.appointment_type_id))
    start = data.get("start_at", a.start_at)
    if "end_at" in data and data["end_at"]:
        end = data["end_at"]
    elif "start_at" in data or "appointment_type_id" in data:
        end = start + (timedelta(minutes=at.duration_minutes) if at else (a.end_at - a.start_at))
    else:
        end = a.end_at
    if end <= start:
        raise bad_request("Appointment must end after it starts")
    timing_changed = start != a.start_at or end != a.end_at or pr.id != a.provider_id or clinic.id != a.clinic_id
    if timing_changed:
        if not body.override_availability and not _within_availability(ctx, pr.id, clinic, start, end):
            raise HTTPException(409, {"code": "outside_availability",
                                      "message": "This time is outside the provider's scheduled hours at this clinic."})
        _check_conflicts(ctx, pr.id, a.patient_id, start, end, exclude_id=a.id)
    a.clinic_id, a.provider_id, a.appointment_type_id, a.start_at, a.end_at = clinic.id, pr.id, at.id if at else None, start, end
    for k in ("mode", "reason", "notes"):
        if k in data:
            setattr(a, k, data[k])
    if timing_changed:
        a.status, a.reminder_sent_at = "scheduled", None
    ctx.audit("appointment.rescheduled" if timing_changed else "appointment.updated", resource_type="appointment",
              resource_id=a.id, patient_id=a.patient_id, details={"fields": sorted(data)})
    ctx.db.commit()
    ctx.db.refresh(a)
    return _with_encounters(ctx, [a])[0]


TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "confirm": (("scheduled",), "confirmed"),
    "check_in": (("scheduled", "confirmed"), "checked_in"),
    "room": (("checked_in", "roomed"), "roomed"),
    "check_out": (("checked_in", "roomed", "in_progress", "completed"), "checked_out"),
    "cancel": (("scheduled", "confirmed", "checked_in"), "cancelled"),
    "no_show": (("scheduled", "confirmed"), "no_show"),
}


@router.post("/appointments/{appt_id}/status", response_model=AppointmentOut)
def change_status(appt_id: uuid.UUID, body: StatusAction, ctx: TenantContext = Depends(require(P.SCHEDULE_WRITE))):
    a = _get_appt(ctx, appt_id)
    allowed_from, target = TRANSITIONS[body.action]
    if a.status not in allowed_from:
        raise bad_request(f"Can't {body.action.replace('_', ' ')} an appointment that is {a.status.replace('_', ' ')}")
    ts = now()
    if body.action == "check_in":
        if a.start_at.date() > (ts + timedelta(days=1)).date():
            raise bad_request("Check-in is only available on the day of the appointment")
        a.checked_in_at = ts
        notify(ctx.db, ctx.org_id, a.provider.user_id, "patient_arrived", f"{a.patient.full_name} checked in",
               f"{a.start_at:%H:%M} UTC appointment at {a.clinic.name}", "/front-desk")
    elif body.action == "room":
        a.room, a.roomed_at = body.room, ts
        notify(ctx.db, ctx.org_id, a.provider.user_id, "patient_roomed", f"{a.patient.full_name} is ready",
               f"Roomed in {body.room or 'exam room'}", f"/patients/{a.patient_id}")
    elif body.action == "check_out":
        a.checked_out_at = ts
    elif body.action == "cancel":
        if not body.reason:
            raise bad_request("A cancellation reason is required")
        a.cancel_reason = body.reason
    a.status = target
    ctx.audit(f"appointment.{body.action}", resource_type="appointment", resource_id=a.id, patient_id=a.patient_id)
    ctx.db.commit()
    ctx.db.refresh(a)
    return _with_encounters(ctx, [a])[0]


@router.get("/front-desk/queue")
def front_desk_queue(clinic_id: uuid.UUID, day: date | None = None, ctx: TenantContext = Depends(require(P.SCHEDULE_READ))):
    clinic = ctx.db.get(Clinic, clinic_id)
    if not clinic or clinic.organization_id != ctx.org_id:
        raise not_found("Clinic")
    ctx.require_clinic(clinic.id)
    tz = ZoneInfo(clinic.timezone)
    day = day or now().astimezone(tz).date()
    start = datetime.combine(day, time(0), tz)
    appts = ctx.db.scalars(select(Appointment).where(and_(
        Appointment.clinic_id == clinic.id, Appointment.start_at >= start, Appointment.start_at < start + timedelta(days=1)))
        .order_by(Appointment.start_at)).all()
    items = _with_encounters(ctx, appts)
    counts: dict[str, int] = {}
    for a in items:
        counts[a.status] = counts.get(a.status, 0) + 1
    return {"clinic_id": clinic.id, "date": day, "timezone": clinic.timezone, "counts": counts, "appointments": items}


__all__ = ["router", "appointment_out"]
