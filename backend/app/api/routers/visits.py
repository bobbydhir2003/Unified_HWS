"""My Visits: one clinician's appointments and encounters, by view. Reuses the existing appointment and encounter records
(no separate visit store).

Scope: a clinician (provider profile) sees their own visits; anyone else with clinical access — e.g. a Platform Admin
viewing the Doctor workspace — sees the visits of their allowed clinics, labelled as such and never as "theirs". Opening a
visit doesn't grant anything: signing requires signing permission and a clinician profile (enforced by the note endpoints).
Restricted charts are excluded."""

from datetime import datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import TenantContext, require
from app.core.permissions import P
from app.core.security import now
from app.models import Appointment, Clinic, ClinicalNote, Encounter, Patient, ProviderProfile, User

router = APIRouter(tags=["visits"])
View = Literal["today", "upcoming", "in_progress", "completed", "documentation"]


def _tz(ctx: TenantContext) -> ZoneInfo:
    q = select(Clinic.timezone).where(Clinic.organization_id == ctx.org_id)
    if ctx.clinic_ids is not None:
        q = q.where(Clinic.id.in_(ctx.clinic_ids))
    return ZoneInfo(ctx.db.scalar(q.limit(1)) or "America/New_York")


def _names(ctx, provider_ids) -> dict:
    ids = {i for i in provider_ids if i}
    if not ids:
        return {}
    rows = ctx.db.execute(select(ProviderProfile.id, User.first_name, User.last_name, User.title).join(User, User.id == ProviderProfile.user_id)
                          .where(ProviderProfile.id.in_(ids))).all()
    return {pid: " ".join(x for x in (f, last) if x) + (f", {t}" if t else "") for pid, f, last, t in rows}


def _scoped(ctx, q, provider_col, clinic_col):
    if ctx.provider:
        q = q.where(provider_col == ctx.provider.id)
    if ctx.clinic_ids is not None:
        q = q.where(clinic_col.in_(ctx.clinic_ids))
    return q


def _appointments(ctx, start, end, limit=100):
    q = (select(Appointment, Patient).join(Patient, Patient.id == Appointment.patient_id)
         .where(Appointment.organization_id == ctx.org_id, Appointment.start_at >= start, Appointment.start_at < end,
                Appointment.status != "cancelled", Patient.is_restricted.is_(False)))
    rows = ctx.db.execute(_scoped(ctx, q, Appointment.provider_id, Appointment.clinic_id).order_by(Appointment.start_at).limit(limit)).all()
    enc = dict(ctx.db.execute(select(Encounter.appointment_id, Encounter.id).where(Encounter.appointment_id.in_([a.id for a, _ in rows]))).all()) if rows else {}
    names = _names(ctx, [a.provider_id for a, _ in rows])
    return [{"kind": "appointment", "id": str(a.id), "at": a.start_at, "patient": {"id": str(p.id), "name": p.full_name, "mrn": p.mrn},
             "reason": a.reason or (a.appointment_type.name if a.appointment_type else None), "status": a.status, "clinician": names.get(a.provider_id),
             "encounter_id": str(enc[a.id]) if a.id in enc else None,
             "link": f"/encounters/{enc[a.id]}" if a.id in enc else f"/patients/{p.id}"} for a, p in rows]


def _encounters(ctx, statuses, since=None, needs_doc=False, limit=100):
    q = (select(Encounter, Patient).join(Patient, Patient.id == Encounter.patient_id)
         .where(Encounter.organization_id == ctx.org_id, Encounter.status.in_(statuses), Patient.is_restricted.is_(False)))
    if since:
        q = q.where(Encounter.started_at >= since)
    rows = ctx.db.execute(_scoped(ctx, q, Encounter.provider_id, Encounter.clinic_id).order_by(Encounter.started_at.desc()).limit(limit * 2)).all()
    notes = dict(ctx.db.execute(select(ClinicalNote.encounter_id, ClinicalNote.status).where(ClinicalNote.encounter_id.in_([e.id for e, _ in rows]))).all()) if rows else {}
    if needs_doc:
        rows = [(e, p) for e, p in rows if notes.get(e.id) != "signed"]
    names = _names(ctx, [e.provider_id for e, _ in rows])
    return [{"kind": "encounter", "id": str(e.id), "at": e.started_at, "patient": {"id": str(p.id), "name": p.full_name, "mrn": p.mrn},
             "reason": e.chief_complaint, "status": e.status, "note_status": notes.get(e.id) or "none", "clinician": names.get(e.provider_id),
             "encounter_id": str(e.id), "link": f"/encounters/{e.id}"} for e, p in rows[:limit]]


@router.get("/my-visits")
def my_visits(view: View = "today", ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    tz = _tz(ctx)
    start = datetime.combine(now().astimezone(tz).date(), time(0), tz)
    end = start + timedelta(days=1)
    if view == "today":
        items = _appointments(ctx, start, end)
    elif view == "upcoming":
        items = _appointments(ctx, end, end + timedelta(days=14))
    elif view == "in_progress":
        items = _encounters(ctx, ("in_progress",))
    elif view == "completed":
        items = _encounters(ctx, ("completed",), since=now() - timedelta(days=30))
    else:
        items = _encounters(ctx, ("in_progress", "completed"), since=now() - timedelta(days=30), needs_doc=True)

    def count_enc(statuses, **kw):
        return len(_encounters(ctx, statuses, **kw))

    counts = {"today": len(_appointments(ctx, start, end)),
              "upcoming": len(_appointments(ctx, end, end + timedelta(days=14))),
              "in_progress": count_enc(("in_progress",)),
              "completed": count_enc(("completed",), since=now() - timedelta(days=30)),
              "documentation": count_enc(("in_progress", "completed"), since=now() - timedelta(days=30), needs_doc=True)}
    return {"view": view, "timezone": str(tz), "scope": "mine" if ctx.provider else "clinics",
            "scope_note": None if ctx.provider else "You don't have a clinician profile, so these are your clinics' visits. You can open them; "
                                                     "signing requires a clinician profile.",
            "counts": counts, "items": items}


_ = func
