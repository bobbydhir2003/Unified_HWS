"""Patient-facing API. Every endpoint resolves the caller's own patient record; there is no patient_id parameter."""

import uuid
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import TenantContext, get_ctx
from app.api.routers.scheduling import _check_conflicts, _within_availability, appointment_out, open_slots
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import (
    Appointment,
    AppointmentType,
    Clinic,
    ClinicalNote,
    Encounter,
    IntakeSubmission,
    Order,
    Patient,
    ProviderProfile,
    VitalSigns,
)
from app.services.notify import notify

router = APIRouter(prefix="/portal", tags=["portal"])


def portal_patient(ctx: TenantContext = Depends(get_ctx)) -> tuple[TenantContext, Patient]:
    if not ctx.can(P.PORTAL_SELF):
        raise forbidden("The patient portal is for patients")
    p = ctx.db.scalar(select(Patient).where(Patient.organization_id == ctx.org_id, Patient.portal_user_id == ctx.user.id))
    if not p:
        raise not_found("Patient record")
    return ctx, p


class BookIn(BaseModel):
    appointment_type_id: uuid.UUID
    provider_id: uuid.UUID
    clinic_id: uuid.UUID
    start_at: datetime
    reason: str = Field(min_length=3, max_length=300)


class IntakeIn(BaseModel):
    reason_details: str = Field(min_length=1, max_length=2000)
    symptoms: list[str] = Field(default_factory=list, max_length=30)
    symptom_duration: str | None = Field(default=None, max_length=100)
    pain_score: int | None = Field(default=None, ge=0, le=10)
    medications_confirmed: bool
    medication_changes: str | None = Field(default=None, max_length=2000)
    allergies_confirmed: bool
    allergy_changes: str | None = Field(default=None, max_length=2000)
    phq2_interest: Literal[0, 1, 2, 3]
    phq2_mood: Literal[0, 1, 2, 3]
    questions_for_clinician: str | None = Field(default=None, max_length=2000)


@router.get("/home")
def home(pp=Depends(portal_patient)):
    ctx, p = pp
    upcoming = ctx.db.scalars(select(Appointment).where(Appointment.patient_id == p.id, Appointment.start_at >= now() - timedelta(hours=2),
                                                        Appointment.status.not_in(("cancelled", "no_show", "checked_out", "completed")))
                              .order_by(Appointment.start_at).limit(5)).all()
    intake_done = set(ctx.db.scalars(select(IntakeSubmission.appointment_id).where(IntakeSubmission.appointment_id.in_([a.id for a in upcoming]))).all())
    new_results = ctx.db.scalar(select(Order.id).where(Order.patient_id == p.id, Order.released_to_patient_at >= now() - timedelta(days=14)).limit(1))
    return {
        "patient": {"id": p.id, "first_name": p.first_name, "last_name": p.last_name, "date_of_birth": p.date_of_birth, "mrn": p.mrn,
                    "email": p.email, "phone": p.phone},
        "upcoming": [{**appointment_out(a).model_dump(mode="json"), "intake_submitted": a.id in intake_done} for a in upcoming],
        "has_recent_results": bool(new_results),
    }


@router.get("/appointments")
def my_appointments(pp=Depends(portal_patient)):
    ctx, p = pp
    rows = ctx.db.scalars(select(Appointment).where(Appointment.patient_id == p.id).order_by(Appointment.start_at.desc()).limit(100)).all()
    done = set(ctx.db.scalars(select(IntakeSubmission.appointment_id).where(IntakeSubmission.patient_id == p.id)).all())
    return [{**appointment_out(a).model_dump(mode="json"), "intake_submitted": a.id in done} for a in rows]


@router.get("/booking/options")
def booking_options(pp=Depends(portal_patient)):
    ctx, p = pp
    types = ctx.db.scalars(select(AppointmentType).where(AppointmentType.organization_id == ctx.org_id, AppointmentType.is_active.is_(True),
                                                         AppointmentType.duration_minutes <= 40)).all()
    provs = ctx.db.scalars(select(ProviderProfile).where(ProviderProfile.organization_id == ctx.org_id, ProviderProfile.is_active.is_(True))).all()
    clinics = ctx.db.scalars(select(Clinic).where(Clinic.organization_id == ctx.org_id, Clinic.is_active.is_(True))).all()
    return {
        "types": [{"id": t.id, "name": t.name, "duration_minutes": t.duration_minutes, "is_telehealth": t.is_telehealth} for t in types],
        "providers": [{"id": x.id, "name": x.user.display_name, "specialty": x.specialty, "is_my_provider": x.id == p.primary_provider_id} for x in provs],
        "clinics": [{"id": c.id, "name": c.name, "timezone": c.timezone, "address": ", ".join(filter(None, [c.address_line1, c.city]))} for c in clinics],
    }


@router.get("/booking/slots")
def booking_slots(provider_id: uuid.UUID, clinic_id: uuid.UUID, type_id: uuid.UUID, day: date, pp=Depends(portal_patient)):
    ctx, _ = pp
    t = ctx.db.get(AppointmentType, type_id)
    if not t or t.organization_id != ctx.org_id:
        raise not_found("Visit type")
    if day > date.today() + timedelta(days=90):
        raise bad_request("Online booking is available up to 90 days ahead")
    # Portal patients don't hold schedule:read; call the shared slot finder with the same tenant context.
    res = open_slots(provider_id, clinic_id, day, t.duration_minutes, ctx)
    cutoff = now() + timedelta(hours=2)
    res["slots"] = [s for s in res["slots"] if datetime.fromisoformat(s) >= cutoff]
    return res


@router.post("/appointments", status_code=201)
def book(body: BookIn, pp=Depends(portal_patient)):
    ctx, p = pp
    if p.status != "active":
        raise bad_request("Please call the clinic to book.")
    t = ctx.db.get(AppointmentType, body.appointment_type_id)
    clinic = ctx.db.get(Clinic, body.clinic_id)
    prov = ctx.db.get(ProviderProfile, body.provider_id)
    if not (t and clinic and prov) or {t.organization_id, clinic.organization_id, prov.organization_id} != {ctx.org_id}:
        raise not_found("Booking option")
    if body.start_at < now() + timedelta(hours=2):
        raise bad_request("Online booking requires at least 2 hours' notice")
    end = body.start_at + timedelta(minutes=t.duration_minutes)
    if not _within_availability(ctx, prov.id, clinic, body.start_at, end):  # no override for patients
        raise HTTPException(409, {"code": "outside_availability", "message": "That time isn't available. Please pick an open slot."})
    _check_conflicts(ctx, prov.id, p.id, body.start_at, end)
    a = Appointment(organization_id=ctx.org_id, clinic_id=clinic.id, patient_id=p.id, provider_id=prov.id, appointment_type_id=t.id,
                    start_at=body.start_at, end_at=end, mode="telehealth" if t.is_telehealth else "in_person", reason=body.reason,
                    booked_via="portal", booked_by_id=ctx.user.id)
    ctx.db.add(a)
    ctx.db.flush()
    notify(ctx.db, ctx.org_id, prov.user_id, "portal_booking", f"New online booking: {p.full_name}",
           f"{t.name} on {body.start_at:%b %d %H:%M} UTC", "/schedule")
    ctx.audit("appointment.created", resource_type="appointment", resource_id=a.id, patient_id=p.id, details={"via": "portal"})
    ctx.db.commit()
    ctx.db.refresh(a)
    return appointment_out(a)


@router.post("/appointments/{appt_id}/cancel")
def cancel(appt_id: uuid.UUID, pp=Depends(portal_patient)):
    ctx, p = pp
    a = ctx.db.get(Appointment, appt_id)
    if not a or a.patient_id != p.id:
        raise not_found("Appointment")
    if a.status not in ("scheduled", "confirmed"):
        raise bad_request("This appointment can't be cancelled online")
    if a.start_at < now() + timedelta(hours=24):
        raise bad_request("Appointments within 24 hours must be cancelled by phone")
    a.status, a.cancel_reason = "cancelled", "Cancelled by patient (portal)"
    notify(ctx.db, ctx.org_id, a.provider.user_id, "portal_cancel", f"Cancelled online: {p.full_name}", f"{a.start_at:%b %d %H:%M} UTC", "/schedule")
    ctx.audit("appointment.cancel", resource_type="appointment", resource_id=a.id, patient_id=p.id, details={"via": "portal"})
    ctx.db.commit()
    return appointment_out(a)


@router.get("/appointments/{appt_id}/intake")
def get_intake(appt_id: uuid.UUID, pp=Depends(portal_patient)):
    ctx, p = pp
    a = ctx.db.get(Appointment, appt_id)
    if not a or a.patient_id != p.id:
        raise not_found("Appointment")
    s = ctx.db.scalar(select(IntakeSubmission).where(IntakeSubmission.appointment_id == a.id))
    return {"submitted_at": s.submitted_at, "answers": s.answers} if s else None


@router.post("/appointments/{appt_id}/intake", status_code=201)
def submit_intake(appt_id: uuid.UUID, body: IntakeIn, pp=Depends(portal_patient)):
    ctx, p = pp
    a = ctx.db.get(Appointment, appt_id)
    if not a or a.patient_id != p.id:
        raise not_found("Appointment")
    if a.status not in ("scheduled", "confirmed", "checked_in"):
        raise bad_request("Intake is only available before your visit")
    s = ctx.db.scalar(select(IntakeSubmission).where(IntakeSubmission.appointment_id == a.id))
    if s:
        s.answers, s.submitted_at, s.reviewed_at, s.reviewed_by_id = body.model_dump(), now(), None, None
    else:
        ctx.db.add(IntakeSubmission(organization_id=ctx.org_id, appointment_id=a.id, patient_id=p.id, answers=body.model_dump(),
                                    submitted_by_id=ctx.user.id))
    ctx.audit("intake.submitted", resource_type="appointment", resource_id=a.id, patient_id=p.id)
    ctx.db.commit()
    return {"message": "Thanks — your answers were sent to your care team."}


@router.get("/visits")
def visit_summaries(pp=Depends(portal_patient)):
    """After-visit summaries from completed encounters with signed notes (assessment, plan, follow-up, diagnoses, vitals)."""
    ctx, p = pp
    encs = ctx.db.scalars(select(Encounter).where(Encounter.patient_id == p.id, Encounter.status == "completed")
                          .order_by(Encounter.started_at.desc()).limit(50)).all()
    out = []
    for e in encs:
        note = ctx.db.scalar(select(ClinicalNote).where(ClinicalNote.encounter_id == e.id, ClinicalNote.status == "signed"))
        if not note:
            continue
        v = ctx.db.scalar(select(VitalSigns).where(VitalSigns.encounter_id == e.id).order_by(VitalSigns.measured_at.desc()))
        meds = ctx.db.scalars(select(Order).where(Order.encounter_id == e.id, Order.order_type == "medication", Order.status == "completed")).all()
        out.append({
            "encounter_id": e.id, "date": e.started_at, "provider": e.provider.user.display_name, "reason": e.chief_complaint,
            "diagnoses": [{"code": d.code, "description": d.description} for d in e.diagnoses],
            "assessment": note.content.get("assessment"), "plan": note.content.get("plan"), "follow_up": e.follow_up,
            "addenda": [a.body for a in note.addenda],
            "vitals": {"bp": f"{v.systolic}/{v.diastolic}" if v and v.systolic else None, "heart_rate": v.heart_rate if v else None,
                       "weight_lb": round(float(v.weight_kg) * 2.20462) if v and v.weight_kg else None},
            "prescriptions": [{"title": m.title, "sig": m.details.get("sig")} for m in meds],
        })
    ctx.audit("portal.visits_viewed", resource_type="patient", resource_id=p.id, patient_id=p.id)
    ctx.db.commit()
    return out
