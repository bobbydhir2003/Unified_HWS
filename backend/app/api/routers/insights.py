"""Milestone C insights: forecasting baselines (C4), unified patient journey (C5), daily briefing & reports (C6).

Forecasts are simple statistical baselines — labeled UNVALIDATED and shown in shadow mode; they inform, never decide.
Briefing numbers come from live queries; any AI narrative must cite the numbered metrics/cases or it is discarded."""

import math
import re
import statistics
import uuid
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import joinedload

from app.api.deps import TenantContext, get_ctx, require
from app.core.errors import forbidden
from app.core.permissions import P
from app.core.security import now
from app.models import (
    AdtEvent,
    Appointment,
    Case,
    Claim,
    DischargePlan,
    DischargePlanItem,
    EdVisit,
    EligibilityCheck,
    Encounter,
    ImagingStudy,
    InpatientStay,
    LabResult,
    Order,
    Prediction,
)
from app.models.engine import CASE_OPEN
from app.services.patients import get_patient

router = APIRouter(tags=["insights"])
LABEL = "Baseline model — not validated. Shadow mode: for planning discussion only, not operational decisions."
NURSE_RATIO = {"med_surg": 5, "icu": 2}


# ======================= C4 Forecasting =======================

def _daily_census(db, org, days: int) -> dict[date, int]:
    """Occupied beds at 23:59 (server local) for each of the last `days` days — one query over all cutoffs, not one per day."""
    day_list = [date.today() - timedelta(days=d) for d in range(days, 0, -1)]
    cutoffs = [datetime.combine(d, time(23, 59)).astimezone() for d in day_list]
    rows = dict(db.execute(text("""
        select c.cutoff, count(ba.id)
        from unnest(cast(:cutoffs as timestamptz[])) as c(cutoff)
        left join bed_assignments ba on ba.start_at <= c.cutoff and (ba.end_at is null or ba.end_at > c.cutoff)
             and ba.stay_id in (select id from inpatient_stays where organization_id = :org)
        group by c.cutoff"""), {"cutoffs": cutoffs, "org": org}).all())
    return {d: int(rows.get(c, 0)) for d, c in zip(day_list, cutoffs, strict=True)}


def _daily_count(db, col, org_col, org, days: int) -> dict[date, int]:
    rows = dict(db.execute(select(func.date(col), func.count()).where(org_col == org, col > now() - timedelta(days=days)).group_by(func.date(col))).all())
    return {date.today() - timedelta(days=d): int(rows.get(date.today() - timedelta(days=d), 0)) for d in range(days, 0, -1)}


def seasonal(history: dict[date, int], target: date) -> tuple[float, float, float, str]:
    """Mean of the same weekday in history (seasonal average); falls back to the overall mean. ±1.5 sd band."""
    days = sorted(history)
    first = next((d for d in days if history[d]), None)  # ignore days before the data starts (no recording ≠ zero activity)
    history = {d: history[d] for d in days if first and d >= first}
    same = [v for d, v in history.items() if d.weekday() == target.weekday()]
    vals = same if len(same) >= 2 else list(history.values())
    method = "same-weekday mean" if len(same) >= 2 else "overall mean"
    if not vals:
        return 0.0, 0.0, 0.0, "no history"
    m = statistics.fmean(vals)
    sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    return round(m, 1), round(max(m - 1.5 * sd, 0), 1), round(m + 1.5 * sd, 1), method


@router.get("/forecasts")
def forecasts(days: int = 7, ctx: TenantContext = Depends(require(P.ANALYTICS_READ))):
    db, org = ctx.db, ctx.org_id
    hist = {"census": _daily_census(db, org, 28), "discharges": _daily_count(db, InpatientStay.discharged_at, InpatientStay.organization_id, org, 28),
            "ed_arrivals": _daily_count(db, EdVisit.arrival_at, EdVisit.organization_id, org, 28),
            "admissions": _daily_count(db, InpatientStay.admitted_at, InpatientStay.organization_id, org, 28)}
    # Backfill actuals for matured predictions (backtest).
    for p in db.scalars(select(Prediction).where(Prediction.organization_id == org, Prediction.actual.is_(None), Prediction.target_date < date.today())):
        series = hist.get(p.target) or {}
        if p.target_date in series:
            p.actual = series[p.target_date]
    out = {}
    stored = set(db.execute(select(Prediction.target, Prediction.target_date).where(
        Prediction.organization_id == org, Prediction.generated_on == date.today(), Prediction.model == "seasonal_mean_v1")).all())
    for target, series in hist.items():
        pts = []
        for i in range(1, min(days, 14) + 1):
            t = date.today() + timedelta(days=i)
            v, lo, hi, method = seasonal(series, t)
            pts.append({"date": t, "value": v, "lower": lo, "upper": hi})
            if (target, t) not in stored:
                db.add(Prediction(organization_id=org, target=target, target_date=t, model="seasonal_mean_v1", value=v, lower=lo, upper=hi,
                                  generated_on=date.today(), inputs={"method": method, "history_days": len(series)}))
        out[target] = {"history": [{"date": d, "value": v} for d, v in series.items()], "forecast": pts, "method": "seasonal_mean_v1"}
    # Staffing demand from forecast census (ratio-based) and no-shows from historical rates.
    cen = out["census"]["forecast"]
    out["nurses_needed"] = {"forecast": [{"date": p["date"], "value": math.ceil(p["value"] / NURSE_RATIO["med_surg"]), "basis": f"census ÷ {NURSE_RATIO['med_surg']} (med-surg ratio)"} for p in cen],
                            "method": "ratio"}
    total = db.scalar(select(func.count()).select_from(Appointment).where(Appointment.organization_id == org, Appointment.start_at < now(),
                                                                          Appointment.start_at > now() - timedelta(days=90))) or 0
    ns = db.scalar(select(func.count()).select_from(Appointment).where(Appointment.organization_id == org, Appointment.status == "no_show",
                                                                       Appointment.start_at > now() - timedelta(days=90))) or 0
    rate = ns / total if total else 0.0
    tomorrow = db.scalar(select(func.count()).select_from(Appointment).where(Appointment.organization_id == org, Appointment.status.in_(("scheduled", "confirmed")),
                                                                             func.date(Appointment.start_at) == date.today() + timedelta(days=1))) or 0
    out["no_shows"] = {"rate_90d": round(rate, 3), "tomorrow_appointments": tomorrow, "expected_no_shows_tomorrow": round(tomorrow * rate, 1), "method": "90-day historical rate"}
    matured = db.scalars(select(Prediction).where(Prediction.organization_id == org, Prediction.actual.is_not(None))).all()
    evaluation = {}
    for t in {p.target for p in matured}:
        ps = [p for p in matured if p.target == t]
        mae = statistics.fmean(abs(p.value - p.actual) for p in ps)
        within = sum(1 for p in ps if p.lower is not None and p.lower <= p.actual <= p.upper) / len(ps)
        evaluation[t] = {"n": len(ps), "mae": round(mae, 2), "band_coverage": round(within, 2)}
    db.commit()
    return {"label": LABEL, "shadow_mode": True, "series": out, "evaluation": evaluation or None,
            "evaluation_note": "Backtest populates as forecast dates pass. Synthetic history cannot validate accuracy."}


# ======================= C5 Patient journey =======================

@router.get("/patients/{patient_id}/journey")
def journey(patient_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    """Cross-department timeline. Each source is included only if the caller holds that permission."""
    p = get_patient(ctx, patient_id)
    db, ev = ctx.db, []

    def add(at, kind, title, detail=None, link=None, dept=None):
        if at:
            ev.append({"at": at, "kind": kind, "title": title, "detail": detail, "link": link, "department": dept})

    if ctx.can(P.SCHEDULE_READ):
        for a in db.scalars(select(Appointment).options(joinedload(Appointment.clinic)).where(Appointment.patient_id == p.id).order_by(Appointment.start_at.desc()).limit(50)):
            add(a.start_at, "appointment", f"Appointment · {a.status.replace('_', ' ')}", a.reason, f"/patients/{p.id}/appointments", a.clinic.name)
    if ctx.can(P.CLINICAL_READ):
        for e in db.scalars(select(Encounter).where(Encounter.patient_id == p.id).order_by(Encounter.started_at.desc()).limit(50)):
            add(e.started_at, "encounter", f"{e.encounter_type.replace('_', ' ').title()} visit", e.chief_complaint, f"/encounters/{e.id}")
        for o in db.scalars(select(Order).where(Order.patient_id == p.id, Order.status != "draft").order_by(Order.created_at.desc()).limit(50)):
            add(o.signed_at or o.created_at, "order", f"{o.order_type.title()} order · {o.title}", o.status, f"/patients/{p.id}/orders")
        for r in db.execute(select(func.max(LabResult.verified_at), Order.title, Order.id).join(Order, Order.id == LabResult.order_id)
                            .where(LabResult.patient_id == p.id, LabResult.status == "final").group_by(Order.title, Order.id)).all():
            add(r[0], "result", f"Result verified · {r[1]}", None, f"/patients/{p.id}/results", "Laboratory")
        for s in db.scalars(select(ImagingStudy).options(joinedload(ImagingStudy.order)).where(ImagingStudy.patient_id == p.id, ImagingStudy.status == "final")):
            add(s.signed_at, "imaging", f"Imaging report signed · {s.order.title}", (s.impression or "")[:160], None, "Radiology")
    if ctx.can(P.ADT_READ):
        for v in db.scalars(select(EdVisit).where(EdVisit.patient_id == p.id)):
            add(v.arrival_at, "ed", f"ED arrival{f' · ESI {v.esi_level}' if v.esi_level else ''}", v.chief_complaint, "/ed", "Emergency")
            if v.departed_at:
                add(v.departed_at, "ed", f"ED departure · {v.disposition}", None, "/ed", "Emergency")
        for a in db.scalars(select(AdtEvent).where(AdtEvent.patient_id == p.id)):
            add(a.at, "adt", a.kind.replace("_", " ").capitalize(), a.note, f"/inpatients/{a.stay_id}", "Inpatient")
    if ctx.can(P.INSURANCE_WRITE) or ctx.can(P.BILLING_READ):
        for c in db.scalars(select(EligibilityCheck).where(EligibilityCheck.patient_id == p.id)):
            add(c.checked_at, "insurance", f"Eligibility {c.result} ({c.source})", f"for {c.date_of_service}", f"/insurance?patient={p.id}", "Insurance")
    if ctx.can(P.BILLING_READ):
        for c in db.scalars(select(Claim).where(Claim.patient_id == p.id)):
            add(c.created_at, "billing", f"Claim {c.claim_number} · {c.status}", c.payer_name, "/billing", "Billing")
    if ctx.can(P.CASES_READ):
        for c in db.scalars(select(Case).where(Case.patient_id == p.id)):
            add(c.created_at, "case", f"Case C{c.number} · {c.title}", c.status, f"/worklist?case={c.id}", c.category)
    ev.sort(key=lambda x: x["at"], reverse=True)
    ctx.audit("patient.journey_viewed", resource_type="patient", resource_id=p.id, patient_id=p.id)
    ctx.db.commit()
    return {"patient": {"id": p.id, "name": p.full_name, "mrn": p.mrn}, "events": ev[:300]}


# ======================= C6 Briefing & reports =======================

def _metrics(ctx) -> list[dict]:
    from app.api.routers.command import hospital_section

    h = hospital_section(ctx, ctx.facility_ids)
    ms = [{"metric": t["label"], "value": t["value"], "detail": t["sub"], "source": t["source"], "link": t["link"]} for t in h.get("tiles", [])]
    return [{**m, "ref": f"M{i + 1}"} for i, m in enumerate(ms)]


def discharge_bottlenecks(db, org) -> list[dict]:
    rows = db.execute(select(DischargePlanItem.label, DischargePlanItem.owner_role, func.count()).join(DischargePlan, DischargePlan.id == DischargePlanItem.plan_id)
                      .where(DischargePlan.organization_id == org, DischargePlan.status == "active", DischargePlanItem.required.is_(True),
                             DischargePlanItem.status.in_(("pending", "in_progress"))).group_by(DischargePlanItem.label, DischargePlanItem.owner_role)
                      .order_by(func.count().desc())).all()
    return [{"item": label, "owner": owner, "open_plans": n} for label, owner, n in rows]


@router.get("/reports/briefing")
def briefing(ctx: TenantContext = Depends(require(P.CASES_READ))):
    if not (ctx.can(P.COMMAND_CENTER) or ctx.can(P.AUTOMATION_MANAGE)):
        raise forbidden()
    metrics = _metrics(ctx)
    crit = ctx.db.scalars(select(Case).where(Case.organization_id == ctx.org_id, Case.status.in_(CASE_OPEN), Case.severity.in_(("critical", "high")))
                          .order_by(Case.due_at.asc().nulls_last()).limit(8)).all()
    cases = [{"ref": f"C{c.number}", "title": c.title, "severity": c.severity, "category": c.category} for c in crit]
    bottlenecks = discharge_bottlenecks(ctx.db, ctx.org_id)
    lines = []
    for m in metrics:
        detail = f" ({m['detail']})" if m.get("detail") else ""
        lines.append(f"{m['metric']}: {m['value']}{detail} [{m['ref']}]")
    if cases:
        lines.append("Highest-priority cases: " + "; ".join(f"{c['title']} [{c['ref']}]" for c in cases[:5]))
    if bottlenecks:
        lines.append("Top discharge blocker: " + f"{bottlenecks[0]['item']} ({bottlenecks[0]['open_plans']} plans, owner {bottlenecks[0]['owner']})")
    narrative, source = "\n".join(lines), "deterministic"
    from app.ai.openai_provider import available

    if available("hospital_operations"):
        from pydantic import BaseModel

        from app.ai.config import effective
        from app.ai.openai_provider import OpenAICore
        from app.ai.policy import contains_phi
        from app.ai.provider import AIError

        class _Out(BaseModel):
            briefing: str

        facts = "\n".join(lines)
        valid = {m["ref"] for m in metrics} | {c["ref"] for c in cases}
        try:
            out, _ = OpenAICore().structured(system=("Write a short daily operations briefing for hospital leaders using ONLY the facts provided. Every sentence must cite "
                                                     "its reference in brackets ([M3], [C1042]). Do not compute new numbers or add recommendations not supported by the facts."),
                                             content=[{"type": "input_text", "text": f"<sources>{facts}</sources>"}], schema=_Out,
                                             contains_phi=contains_phi(ctx.db, ctx.org_id), model=effective().model_for("hospital_operations"),
                                             max_output_tokens=1200, name="briefing")
            kept = [s for s in re.split(r"(?<=[.!?])\s+", out.briefing) if (refs := set(re.findall(r"\[((?:M|C)\d+)\]", s))) and refs <= valid]
            if kept:
                narrative, source = " ".join(kept), "ai_cited"
        except AIError:
            pass
    ctx.audit("reports.briefing", details={"source": source})
    ctx.db.commit()
    return {"generated_at": now(), "narrative": narrative, "narrative_source": source, "metrics": metrics, "cases": cases, "discharge_bottlenecks": bottlenecks}


@router.get("/reports/discharge-bottlenecks")
def discharge_report(ctx: TenantContext = Depends(require(P.ADT_READ))):
    return {"generated_at": now(), "items": discharge_bottlenecks(ctx.db, ctx.org_id), "source": "discharge_plan_items (active plans, required, open)"}
