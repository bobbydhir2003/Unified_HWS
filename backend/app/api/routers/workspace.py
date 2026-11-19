"""Cross-cutting workspace endpoints: global search, notifications, role dashboard."""

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update

from app.api.deps import TenantContext, get_ctx
from app.api.routers.patients import search_patients_query
from app.core.permissions import P
from app.core.security import now
from app.models import Appointment, Clinic, ClinicalNote, Encounter, Invitation, Notification, Patient
from app.schemas.common import Message

router = APIRouter(tags=["workspace"])


@router.get("/search")
def global_search(q: str = Query(min_length=1, max_length=100), ctx: TenantContext = Depends(get_ctx)):
    out: dict = {"patients": []}
    if ctx.can(P.PATIENTS_READ):
        rows = ctx.db.scalars(search_patients_query(ctx, q).limit(8)).all()
        out["patients"] = [{"id": p.id, "name": p.full_name, "mrn": p.mrn, "date_of_birth": p.date_of_birth,
                            "sex_at_birth": p.sex_at_birth, "status": p.status, "is_restricted": p.is_restricted} for p in rows]
    return out


@router.get("/notifications")
def list_notifications(unread_only: bool = False, ctx: TenantContext = Depends(get_ctx)):
    q = select(Notification).where(Notification.organization_id == ctx.org_id, Notification.user_id == ctx.user.id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    rows = ctx.db.scalars(q.order_by(Notification.created_at.desc()).limit(50)).all()
    unread = ctx.db.scalar(select(func.count()).where(Notification.organization_id == ctx.org_id,
                                                      Notification.user_id == ctx.user.id, Notification.read_at.is_(None)))
    return {"unread": unread, "items": [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
                                         "read_at": n.read_at, "created_at": n.created_at} for n in rows]}


@router.post("/notifications/read", response_model=Message)
def mark_read(ids: list[uuid.UUID] | None = None, ctx: TenantContext = Depends(get_ctx)):
    q = update(Notification).where(Notification.user_id == ctx.user.id, Notification.organization_id == ctx.org_id,
                                   Notification.read_at.is_(None))
    if ids:
        q = q.where(Notification.id.in_(ids))
    ctx.db.execute(q.values(read_at=now()))
    ctx.db.commit()
    return Message(message="ok")


@router.get("/dashboard")
def dashboard(clinic_id: uuid.UUID | None = None, ctx: TenantContext = Depends(get_ctx)):
    """Role-aware 'today' dashboard computed from live data."""
    clinic = ctx.db.get(Clinic, clinic_id) if clinic_id else None
    if clinic and clinic.organization_id != ctx.org_id:
        clinic = None
    tz = ZoneInfo(clinic.timezone if clinic else "America/New_York")
    today = now().astimezone(tz).date()
    start = datetime.combine(today, time(0), tz)
    end = start + timedelta(days=1)
    out: dict = {"date": today}

    if ctx.can(P.SCHEDULE_READ):
        q = select(Appointment).where(Appointment.organization_id == ctx.org_id, Appointment.start_at >= start,
                                      Appointment.start_at < end)
        if clinic:
            q = q.where(Appointment.clinic_id == clinic.id)
        elif ctx.clinic_ids is not None:
            q = q.where(Appointment.clinic_id.in_(ctx.clinic_ids))
        if ctx.provider and ctx.has_role("doctor") and not ctx.has_role("clinic_admin"):
            q = q.where(Appointment.provider_id == ctx.provider.id)
        appts = ctx.db.scalars(q.order_by(Appointment.start_at)).all()
        counts: dict[str, int] = {}
        for a in appts:
            counts[a.status] = counts.get(a.status, 0) + 1
        out["appointments"] = {
            "total": len([a for a in appts if a.status not in ("cancelled",)]),
            "by_status": counts,
            "waiting": [{"id": a.id, "patient": a.patient.full_name, "patient_id": a.patient_id, "status": a.status,
                         "checked_in_at": a.checked_in_at, "start_at": a.start_at, "room": a.room,
                         "provider": a.provider.user.display_name}
                        for a in appts if a.status in ("checked_in", "roomed")],
            "next": [{"id": a.id, "patient": a.patient.full_name, "patient_id": a.patient_id, "start_at": a.start_at,
                      "status": a.status, "type": a.appointment_type.name if a.appointment_type else None,
                      "reason": a.reason, "provider": a.provider.user.display_name, "mode": a.mode}
                     for a in appts if a.status in ("scheduled", "confirmed", "checked_in", "roomed", "in_progress")][:8],
        }
        week = ctx.db.execute(
            select(func.date_trunc("day", Appointment.start_at).label("d"), func.count())
            .where(Appointment.organization_id == ctx.org_id, Appointment.start_at >= start - timedelta(days=6),
                   Appointment.start_at < end, Appointment.status.not_in(("cancelled",)))
            .group_by("d").order_by("d")).all()
        out["appointments_7d"] = [{"date": d.date(), "count": c} for d, c in week]

    if ctx.can(P.CLINICAL_READ) and ctx.provider:
        open_enc = ctx.db.scalars(select(Encounter).where(Encounter.provider_id == ctx.provider.id,
                                                          Encounter.status == "in_progress")
                                  .order_by(Encounter.started_at.desc()).limit(10)).all()
        unsigned = ctx.db.scalar(select(func.count()).select_from(ClinicalNote).join(Encounter)
                                 .where(Encounter.provider_id == ctx.provider.id, ClinicalNote.status == "draft"))
        out["clinical"] = {
            "open_encounters": [{"id": e.id, "patient": e.patient.full_name, "patient_id": e.patient_id,
                                 "started_at": e.started_at, "chief_complaint": e.chief_complaint} for e in open_enc],
            "unsigned_notes": unsigned,
        }

    if ctx.can(P.PATIENTS_READ):
        out["patients"] = {
            "total": ctx.db.scalar(select(func.count()).where(Patient.organization_id == ctx.org_id, Patient.status == "active")),
            "new_30d": ctx.db.scalar(select(func.count()).where(Patient.organization_id == ctx.org_id,
                                                                Patient.created_at >= now() - timedelta(days=30))),
        }
    if ctx.can(P.USERS_MANAGE):
        out["admin"] = {"pending_invitations": ctx.db.scalar(select(func.count()).where(
            Invitation.organization_id == ctx.org_id, Invitation.accepted_at.is_(None), Invitation.revoked_at.is_(None),
            Invitation.expires_at > now()))}
    return out
