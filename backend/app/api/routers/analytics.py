"""Analytics & population health — every number is computed from live tables at request time.

Quality measures are *modeled on* CMS eCQMs (e.g. CMS122 diabetes poor control, CMS165 controlling high BP) with
simplified logic for operational use; they are not certified measure calculations.
"""

import csv
import io
import uuid
from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Numeric, and_, case, cast, func, or_, select

from app.api.deps import TenantContext, require
from app.core.errors import bad_request
from app.core.permissions import P
from app.core.security import now
from app.models import (
    Appointment,
    AppointmentType,
    Claim,
    ClinicalNote,
    Encounter,
    LabResult,
    Patient,
    Payment,
    Problem,
    ProviderAvailability,
    ProviderProfile,
    ScribeSession,
    Task,
    VitalSigns,
)
from app.models.scheduling import INACTIVE_APPOINTMENT_STATUSES

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _range(days: int) -> tuple[datetime, datetime]:
    end = datetime.combine(date.today() + timedelta(days=1), time.min).astimezone()
    return end - timedelta(days=days + 1), end


def _scope(q, model, ctx: TenantContext, clinic_id: uuid.UUID | None, provider_id: uuid.UUID | None):
    q = q.where(model.organization_id == ctx.org_id)
    if clinic_id and hasattr(model, "clinic_id"):
        ctx.require_clinic(clinic_id)
        q = q.where(model.clinic_id == clinic_id)
    elif ctx.clinic_ids is not None and hasattr(model, "clinic_id"):
        q = q.where(model.clinic_id.in_(ctx.clinic_ids))
    if provider_id and hasattr(model, "provider_id"):
        q = q.where(model.provider_id == provider_id)
    return q


# ----------------------------------------------------------------------------------------------- operations

@router.get("/operations")
def operations(days: int = Query(30, ge=7, le=365), clinic_id: uuid.UUID | None = None, provider_id: uuid.UUID | None = None,
               ctx: TenantContext = Depends(require(P.ANALYTICS_READ))):
    start, end = _range(days)
    base = _scope(select(Appointment), Appointment, ctx, clinic_id, provider_id).where(Appointment.start_at >= start, Appointment.start_at < min(end, now()))
    sq = base.subquery()
    by_status = dict(ctx.db.execute(select(sq.c.status, func.count()).group_by(sq.c.status)).all())
    total = sum(by_status.values())
    kept = sum(v for k, v in by_status.items() if k in ("checked_out", "completed", "in_progress", "roomed", "checked_in"))
    per_day = ctx.db.execute(select(func.date_trunc("day", sq.c.start_at).label("d"), sq.c.status, func.count()).group_by("d", sq.c.status).order_by("d")).all()
    days_map: dict[str, dict] = {}
    for d, st, n in per_day:
        row = days_map.setdefault(d.date().isoformat(), {"date": d.date().isoformat(), "completed": 0, "no_show": 0, "cancelled": 0, "other": 0})
        key = "completed" if st in ("checked_out", "completed") else st if st in ("no_show", "cancelled") else "other"
        row[key] += n
    wait = ctx.db.scalar(select(func.avg(func.extract("epoch", sq.c.roomed_at - sq.c.checked_in_at) / 60)).where(sq.c.roomed_at.is_not(None), sq.c.checked_in_at.is_not(None)))
    enc_q = _scope(select(Encounter), Encounter, ctx, clinic_id, provider_id).where(Encounter.started_at >= start, Encounter.status == "completed").subquery()
    visit_len = ctx.db.scalar(select(func.avg(func.extract("epoch", enc_q.c.completed_at - enc_q.c.started_at) / 60)))
    by_type = ctx.db.execute(select(func.coalesce(AppointmentType.name, "Unspecified"), func.count()).select_from(sq).outerjoin(
        AppointmentType, AppointmentType.id == sq.c.appointment_type_id).where(sq.c.status.not_in(INACTIVE_APPOINTMENT_STATUSES)).group_by(AppointmentType.name)).all()
    channels = dict(ctx.db.execute(select(sq.c.booked_via, func.count()).group_by(sq.c.booked_via)).all())
    modes = dict(ctx.db.execute(select(sq.c.mode, func.count()).where(sq.c.status.not_in(INACTIVE_APPOINTMENT_STATUSES)).group_by(sq.c.mode)).all())
    # Utilization: booked minutes vs scheduled availability minutes over the window (per provider).
    util = []
    provs = ctx.db.scalars(select(ProviderProfile).where(ProviderProfile.organization_id == ctx.org_id, ProviderProfile.is_active.is_(True))).all()
    weekday_counts = [0] * 7
    d = start.date()
    while d < min(end, now()).date():
        weekday_counts[d.weekday()] += 1
        d += timedelta(days=1)
    for pr in provs:
        if provider_id and pr.id != provider_id:
            continue
        avail_q = select(ProviderAvailability).where(ProviderAvailability.provider_id == pr.id)
        if clinic_id:
            avail_q = avail_q.where(ProviderAvailability.clinic_id == clinic_id)
        avail_min = sum(((b.end_time.hour * 60 + b.end_time.minute) - (b.start_time.hour * 60 + b.start_time.minute)) * weekday_counts[b.weekday]
                        for b in ctx.db.scalars(avail_q).all())
        booked = ctx.db.scalar(select(func.coalesce(func.sum(func.extract("epoch", sq.c.end_at - sq.c.start_at) / 60), 0)).where(
            sq.c.provider_id == pr.id, sq.c.status.not_in(INACTIVE_APPOINTMENT_STATUSES))) or 0
        if avail_min:
            util.append({"provider": pr.user.display_name, "available_hours": round(avail_min / 60, 1), "booked_hours": round(float(booked) / 60, 1),
                         "utilization": round(min(float(booked) / avail_min, 1.5), 3)})
    return {
        "days": days, "total_appointments": total, "by_status": by_status,
        "no_show_rate": round(by_status.get("no_show", 0) / total, 3) if total else None,
        "cancellation_rate": round(by_status.get("cancelled", 0) / total, 3) if total else None,
        "kept_rate": round(kept / total, 3) if total else None,
        "avg_wait_minutes": round(float(wait), 1) if wait is not None else None,
        "avg_visit_minutes": round(float(visit_len), 1) if visit_len is not None else None,
        "per_day": list(days_map.values()), "by_type": [{"type": t, "count": n} for t, n in by_type],
        "booking_channels": channels, "modes": modes, "utilization": util,
    }


# ----------------------------------------------------------------------------------------------- providers

@router.get("/providers")
def providers(days: int = Query(30, ge=7, le=365), clinic_id: uuid.UUID | None = None, ctx: TenantContext = Depends(require(P.ANALYTICS_READ))):
    start, _ = _range(days)
    rows = []
    for pr in ctx.db.scalars(select(ProviderProfile).where(ProviderProfile.organization_id == ctx.org_id)).all():
        eq = _scope(select(Encounter), Encounter, ctx, clinic_id, pr.id).where(Encounter.started_at >= start).subquery()
        completed = ctx.db.scalar(select(func.count()).select_from(eq).where(eq.c.status == "completed")) or 0
        open_ = ctx.db.scalar(select(func.count()).select_from(eq).where(eq.c.status == "in_progress")) or 0
        patients = ctx.db.scalar(select(func.count(func.distinct(eq.c.patient_id))).select_from(eq)) or 0
        unsigned = ctx.db.scalar(select(func.count()).select_from(ClinicalNote).join(Encounter, Encounter.id == ClinicalNote.encounter_id).where(
            Encounter.provider_id == pr.id, ClinicalNote.status == "draft")) or 0
        sign_lag = ctx.db.scalar(select(func.avg(func.extract("epoch", ClinicalNote.signed_at - Encounter.started_at) / 3600)).join(
            Encounter, Encounter.id == ClinicalNote.encounter_id).where(Encounter.provider_id == pr.id, ClinicalNote.signed_at.is_not(None), Encounter.started_at >= start))
        no_shows = ctx.db.scalar(select(func.count()).select_from(Appointment).where(Appointment.provider_id == pr.id, Appointment.status == "no_show",
                                                                                     Appointment.start_at >= start)) or 0
        scribe = ctx.db.scalar(select(func.count()).select_from(ScribeSession).join(Encounter, Encounter.id == ScribeSession.encounter_id).where(
            Encounter.provider_id == pr.id, ScribeSession.status == "applied", ScribeSession.created_at >= start)) or 0
        rows.append({"provider_id": pr.id, "provider": pr.user.display_name, "specialty": pr.specialty, "visits_completed": completed, "open_encounters": open_,
                     "unique_patients": patients, "unsigned_notes": unsigned, "avg_hours_to_sign": round(float(sign_lag), 1) if sign_lag is not None else None,
                     "no_shows": no_shows, "ai_scribe_notes": scribe})
    return {"days": days, "providers": sorted(rows, key=lambda r: -r["visits_completed"])}


# ----------------------------------------------------------------------------------------------- financial

@router.get("/financial")
def financial(days: int = Query(90, ge=30, le=365), ctx: TenantContext = Depends(require(P.BILLING_READ))):
    start, _ = _range(days)
    org = ctx.org_id
    charges = ctx.db.scalar(select(func.coalesce(func.sum(Claim.total_charge_cents), 0)).where(Claim.organization_id == org, Claim.created_at >= start, Claim.status != "void"))
    pay = dict(ctx.db.execute(select(Payment.source, func.sum(Payment.amount_cents)).where(Payment.organization_id == org, Payment.created_at >= start).group_by(Payment.source)).all())
    by_payer = ctx.db.execute(select(Claim.payer_name, func.count(), func.sum(Claim.total_charge_cents), func.sum(Claim.paid_cents),
                                     func.sum(case((Claim.status.in_(("denied", "closed")), 1), else_=0))).where(
        Claim.organization_id == org, Claim.created_at >= start, Claim.status != "void").group_by(Claim.payer_name).order_by(func.sum(Claim.total_charge_cents).desc())).all()
    monthly = ctx.db.execute(select(func.date_trunc("month", Payment.created_at).label("m"), Payment.source, func.sum(Payment.amount_cents)).where(
        Payment.organization_id == org, Payment.created_at >= start).group_by("m", Payment.source).order_by("m")).all()
    paid_claims = ctx.db.execute(select(func.avg(func.extract("epoch", Claim.adjudicated_at - Claim.submitted_at) / 86400)).where(
        Claim.organization_id == org, Claim.status == "paid", Claim.created_at >= start)).scalar()
    adjudicated = ctx.db.scalar(select(func.count()).select_from(Claim).where(Claim.organization_id == org, Claim.adjudicated_at >= start)) or 0
    denied = ctx.db.scalar(select(func.count()).select_from(Claim).where(Claim.organization_id == org, Claim.adjudicated_at >= start,
                                                                         or_(Claim.denial_code.is_not(None), Claim.status == "denied"))) or 0
    collected = sum(int(v) for v in pay.values())
    return {
        "days": days, "charges_cents": int(charges), "collections": {k: int(v) for k, v in pay.items()}, "collected_cents": collected,
        "collection_rate": round(collected / charges, 3) if charges else None, "denial_rate": round(denied / adjudicated, 3) if adjudicated else None,
        "avg_days_to_payment": round(float(paid_claims), 1) if paid_claims is not None else None,
        "by_payer": [{"payer": p, "claims": n, "charges_cents": int(c or 0), "paid_cents": int(pd or 0), "denials": int(dn or 0)} for p, n, c, pd, dn in by_payer],
        "monthly": [{"month": m.date().isoformat(), "source": s, "cents": int(v)} for m, s, v in monthly], "simulated_payer_data": True,
    }


# ----------------------------------------------------------------------------------------------- population health

REGISTRIES = {
    "diabetes": ("Diabetes", ["E10", "E11"]), "hypertension": ("Hypertension", ["I10"]), "hyperlipidemia": ("Hyperlipidemia", ["E78"]),
    "asthma_copd": ("Asthma / COPD", ["J45", "J44"]), "depression_anxiety": ("Depression / anxiety", ["F32", "F33", "F41"]),
    "hypothyroidism": ("Hypothyroidism", ["E03"]),
}


def _registry_ids(ctx: TenantContext, prefixes: list[str]):
    return select(Problem.patient_id).where(Problem.organization_id == ctx.org_id, Problem.status == "active",
                                            or_(*[Problem.code.like(f"{p}%") for p in prefixes])).distinct()


@router.get("/population")
def population(ctx: TenantContext = Depends(require(P.ANALYTICS_READ))):
    active = select(Patient.id).where(Patient.organization_id == ctx.org_id, Patient.status == "active")
    total = ctx.db.scalar(select(func.count()).select_from(active.subquery()))
    regs = [{"key": k, "label": label, "patients": ctx.db.scalar(select(func.count()).select_from(_registry_ids(ctx, pre).where(Problem.patient_id.in_(active)).subquery()))}
            for k, (label, pre) in REGISTRIES.items()]
    age = func.date_part("year", func.age(Patient.date_of_birth))
    bands = ctx.db.execute(select(case((age < 18, "0-17"), (age < 40, "18-39"), (age < 65, "40-64"), else_="65+").label("b"), Patient.sex_at_birth, func.count())
                           .where(Patient.organization_id == ctx.org_id, Patient.status == "active").group_by("b", Patient.sex_at_birth)).all()
    last_visit = select(Encounter.patient_id).where(Encounter.organization_id == ctx.org_id, Encounter.status == "completed",
                                                    Encounter.started_at >= now() - timedelta(days=365)).distinct()
    no_visit = ctx.db.scalar(select(func.count()).select_from(active.where(Patient.id.not_in(last_visit)).subquery()))
    multi = ctx.db.scalar(select(func.count()).select_from(select(Problem.patient_id).where(Problem.organization_id == ctx.org_id, Problem.status == "active",
                                                                                              Problem.is_chronic.is_(True)).group_by(Problem.patient_id).having(func.count() >= 2).subquery()))
    return {"active_patients": total, "registries": regs, "age_sex": [{"band": b, "sex": s, "count": n} for b, s, n in bands],
            "no_visit_12m": no_visit, "multiple_chronic_conditions": multi}


GAPS = {
    "a1c_overdue": "Diabetes — no HbA1c in 6 months",
    "a1c_poor_control": "Diabetes — most recent HbA1c > 9%",
    "bp_uncontrolled": "Hypertension — most recent BP ≥ 140/90",
    "lipid_overdue": "Hyperlipidemia — no lipid panel in 12 months",
    "no_visit_12m": "No completed visit in 12 months",
}


def _latest_lab(ctx: TenantContext, name: str):
    rn = func.row_number().over(partition_by=LabResult.patient_id, order_by=LabResult.resulted_at.desc()).label("rn")
    sub = select(LabResult.patient_id, LabResult.value, LabResult.resulted_at, rn).where(LabResult.organization_id == ctx.org_id, LabResult.name == name).subquery()
    return select(sub.c.patient_id, sub.c.value, sub.c.resulted_at).where(sub.c.rn == 1).subquery()


def _latest_bp(ctx: TenantContext):
    rn = func.row_number().over(partition_by=VitalSigns.patient_id, order_by=VitalSigns.measured_at.desc()).label("rn")
    sub = select(VitalSigns.patient_id, VitalSigns.systolic, VitalSigns.diastolic, VitalSigns.measured_at, rn).where(
        VitalSigns.organization_id == ctx.org_id, VitalSigns.systolic.is_not(None)).subquery()
    return select(sub.c.patient_id, sub.c.systolic, sub.c.diastolic, sub.c.measured_at).where(sub.c.rn == 1).subquery()


def gap_rows(ctx: TenantContext, measure: str) -> list[dict]:
    if measure not in GAPS:
        raise bad_request("Unknown measure")
    P_ = Patient
    base = select(P_).where(P_.organization_id == ctx.org_id, P_.status == "active", P_.is_restricted.is_(False))
    detail: dict[uuid.UUID, str] = {}
    if measure in ("a1c_overdue", "a1c_poor_control"):
        a1c = _latest_lab(ctx, "Hemoglobin A1c")
        q = select(P_, a1c.c.value, a1c.c.resulted_at).outerjoin(a1c, a1c.c.patient_id == P_.id).where(
            P_.organization_id == ctx.org_id, P_.status == "active", P_.is_restricted.is_(False), P_.id.in_(_registry_ids(ctx, ["E10", "E11"])))
        if measure == "a1c_overdue":
            q = q.where(or_(a1c.c.resulted_at.is_(None), a1c.c.resulted_at < now() - timedelta(days=182)))
        else:
            q = q.where(cast(func.nullif(func.regexp_replace(a1c.c.value, r"[^0-9.]", "", "g"), ""), Numeric) > 9)
        rows = ctx.db.execute(q).all()
        pts = [r[0] for r in rows]
        for p, v, at in rows:
            detail[p.id] = f"Last A1c {v}% on {at:%Y-%m-%d}" if v else "No A1c on file"
    elif measure == "bp_uncontrolled":
        bp = _latest_bp(ctx)
        rows = ctx.db.execute(select(P_, bp.c.systolic, bp.c.diastolic, bp.c.measured_at).join(bp, bp.c.patient_id == P_.id).where(
            P_.organization_id == ctx.org_id, P_.status == "active", P_.is_restricted.is_(False), P_.id.in_(_registry_ids(ctx, ["I10"])),
            or_(bp.c.systolic >= 140, bp.c.diastolic >= 90))).all()
        pts = [r[0] for r in rows]
        for p, s, d, at in rows:
            detail[p.id] = f"Last BP {s}/{d} on {at:%Y-%m-%d}"
    elif measure == "lipid_overdue":
        ldl = _latest_lab(ctx, "LDL cholesterol")
        rows = ctx.db.execute(select(P_, ldl.c.resulted_at).outerjoin(ldl, ldl.c.patient_id == P_.id).where(
            P_.organization_id == ctx.org_id, P_.status == "active", P_.is_restricted.is_(False), P_.id.in_(_registry_ids(ctx, ["E78"])),
            or_(ldl.c.resulted_at.is_(None), ldl.c.resulted_at < now() - timedelta(days=365)))).all()
        pts = [r[0] for r in rows]
        for p, at in rows:
            detail[p.id] = f"Last lipid panel {at:%Y-%m-%d}" if at else "No lipid panel on file"
    else:
        seen = select(Encounter.patient_id).where(Encounter.organization_id == ctx.org_id, Encounter.status == "completed",
                                                  Encounter.started_at >= now() - timedelta(days=365))
        pts = ctx.db.scalars(base.where(P_.id.not_in(seen))).all()
        for p in pts:
            detail[p.id] = "No completed visit in the last 12 months"
    provs = {pr.id: pr.user.display_name for pr in ctx.db.scalars(select(ProviderProfile).where(ProviderProfile.organization_id == ctx.org_id)).all()}
    open_tasks = set(ctx.db.scalars(select(Task.patient_id).where(Task.organization_id == ctx.org_id, Task.status == "open",
                                                                  Task.title.like(f"Care gap: {GAPS[measure]}%"))).all())
    return [{"patient_id": p.id, "name": p.full_name, "mrn": p.mrn, "date_of_birth": p.date_of_birth, "phone": p.phone,
             "pcp": provs.get(p.primary_provider_id), "detail": detail.get(p.id), "outreach_open": p.id in open_tasks} for p in pts]


@router.get("/care-gaps")
def care_gaps(measure: str | None = None, ctx: TenantContext = Depends(require(P.ANALYTICS_READ))):
    if measure:
        return {"measure": measure, "label": GAPS.get(measure), "patients": gap_rows(ctx, measure)}
    return {"measures": [{"key": k, "label": v, "count": len(gap_rows(ctx, k))} for k, v in GAPS.items()]}


class OutreachIn(BaseModel):
    measure: str
    patient_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    role: Literal["nurse", "receptionist"] = "nurse"


@router.post("/care-gaps/outreach")
def create_outreach(body: OutreachIn, ctx: TenantContext = Depends(require(P.ANALYTICS_READ))):
    if body.measure not in GAPS:
        raise bad_request("Unknown measure")
    valid = {r["patient_id"]: r for r in gap_rows(ctx, body.measure)}
    created = 0
    for pid in body.patient_ids:
        r = valid.get(pid)
        if not r or r["outreach_open"]:
            continue
        ctx.db.add(Task(organization_id=ctx.org_id, title=f"Care gap: {GAPS[body.measure]} — {r['name']}"[:200], description=r["detail"],
                        patient_id=pid, assigned_role=body.role, priority="normal", link=f"/patients/{pid}", source="manual"))
        created += 1
    ctx.audit("analytics.care_gap_outreach", resource_type="care_gap", resource_id=body.measure, details={"tasks": created})
    ctx.db.commit()
    return {"created": created, "skipped": len(body.patient_ids) - created}


@router.get("/quality")
def quality(ctx: TenantContext = Depends(require(P.ANALYTICS_READ))):
    diabetics = ctx.db.scalar(select(func.count()).select_from(_registry_ids(ctx, ["E10", "E11"]).subquery())) or 0
    poor_ids = {r["patient_id"] for r in gap_rows(ctx, "a1c_poor_control")}
    missing_ids = {r["patient_id"] for r in gap_rows(ctx, "a1c_overdue")}
    a1c_missing = len(missing_ids)
    htn = ctx.db.scalar(select(func.count()).select_from(_registry_ids(ctx, ["I10"]).subquery())) or 0
    bp = _latest_bp(ctx)
    htn_with_bp = ctx.db.scalar(select(func.count()).select_from(bp).where(bp.c.patient_id.in_(_registry_ids(ctx, ["I10"])))) or 0
    controlled = ctx.db.scalar(select(func.count()).select_from(bp).where(bp.c.patient_id.in_(_registry_ids(ctx, ["I10"])),
                                                                         and_(bp.c.systolic < 140, bp.c.diastolic < 90))) or 0
    lipid = ctx.db.scalar(select(func.count()).select_from(_registry_ids(ctx, ["E78"]).subquery())) or 0
    lipid_overdue = len(gap_rows(ctx, "lipid_overdue"))

    def m(key, name, ref, num, den, inverse=False):
        return {"key": key, "name": name, "modeled_on": ref, "numerator": num, "denominator": den,
                "rate": round(num / den, 3) if den else None, "lower_is_better": inverse}
    return {"measures": [
        m("dm_poor_control", "Diabetes: HbA1c poor control (>9% or untested)", "CMS122", len(poor_ids | missing_ids), diabetics, inverse=True),
        m("dm_a1c_tested", "Diabetes: HbA1c tested in last 6 months", "process", diabetics - a1c_missing, diabetics),
        m("htn_controlled", "Controlling high blood pressure (<140/90)", "CMS165", controlled, htn),
        m("htn_bp_recorded", "Hypertension: BP on file", "process", htn_with_bp, htn),
        m("lipid_screened", "Hyperlipidemia: lipid panel in last 12 months", "process", lipid - lipid_overdue, lipid),
    ], "disclaimer": "Simplified logic modeled on CMS measures for operational use; not certified eCQM results."}


# ----------------------------------------------------------------------------------------------- CSV export

@router.get("/export/{report}.csv")
def export(report: Literal["care_gaps", "quality", "providers", "appointments"], measure: str | None = None, days: int = Query(30, ge=7, le=365),
           ctx: TenantContext = Depends(require(P.ANALYTICS_READ))):
    buf = io.StringIO()
    w = csv.writer(buf)
    if report == "care_gaps":
        if not measure:
            raise bad_request("measure is required")
        w.writerow(["measure", "patient", "mrn", "date_of_birth", "phone", "pcp", "detail", "outreach_open"])
        for r in gap_rows(ctx, measure):
            w.writerow([measure, r["name"], r["mrn"], r["date_of_birth"], r["phone"], r["pcp"], r["detail"], r["outreach_open"]])
    elif report == "quality":
        w.writerow(["measure", "modeled_on", "numerator", "denominator", "rate", "lower_is_better"])
        for mm in quality(ctx)["measures"]:
            w.writerow([mm["name"], mm["modeled_on"], mm["numerator"], mm["denominator"], mm["rate"], mm["lower_is_better"]])
    elif report == "providers":
        w.writerow(["provider", "specialty", "visits_completed", "unique_patients", "open_encounters", "unsigned_notes", "avg_hours_to_sign", "no_shows", "ai_scribe_notes"])
        for r in providers(days, None, ctx)["providers"]:
            w.writerow([r["provider"], r["specialty"], r["visits_completed"], r["unique_patients"], r["open_encounters"], r["unsigned_notes"],
                        r["avg_hours_to_sign"], r["no_shows"], r["ai_scribe_notes"]])
    else:
        start, end = _range(days)
        w.writerow(["date", "time_utc", "provider", "clinic", "type", "status", "mode", "booked_via"])
        rows = ctx.db.execute(_scope(select(Appointment), Appointment, ctx, None, None).where(Appointment.start_at >= start, Appointment.start_at < end)
                              .order_by(Appointment.start_at)).scalars().all()
        for a in rows:  # operational export: no patient identifiers
            w.writerow([a.start_at.date(), a.start_at.strftime("%H:%M"), a.provider.user.display_name, a.clinic.name,
                        a.appointment_type.name if a.appointment_type else "", a.status, a.mode, a.booked_via])
    ctx.audit("analytics.exported", resource_type="report", resource_id=report, details={"measure": measure, "days": days})
    ctx.db.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="undeclared-{report}-{date.today()}.csv"'})

