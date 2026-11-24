"""Nursing documentation: flowsheet (observations + intake/output totals), structured assessments, care plans.

Row and template definitions below are configurable demonstrations reviewed for this synthetic environment — not a
formal nursing taxonomy and not licensed scoring instruments. Vital signs are read from the existing Vitals records
(one source of truth), so they appear in the flowsheet without being entered twice.
"""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import TenantContext, require
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import NursingAssessment, NursingCarePlan, NursingObservation, User, VitalSigns
from app.services.medication import active_stay
from app.services.patients import get_patient

router = APIRouter(tags=["nursing documentation"])

# key: (group, label, kind, unit, min, max, options)
ROWS: dict[str, tuple] = {
    "pain_score": ("Observations", "Pain score (0–10)", "number", None, 0, 10, None),
    "consciousness": ("Observations", "Level of consciousness", "choice", None, None, None, ["Alert", "Responds to voice", "Responds to pain", "Unresponsive"]),
    "skin": ("Observations", "Skin / pressure areas", "text", None, None, None, None),
    "mobility": ("Observations", "Mobility", "choice", None, None, None, ["Independent", "Assist ×1", "Assist ×2", "Bed rest"]),
    "intake_oral": ("Intake", "Oral", "number", "mL", 0, 5000, None),
    "intake_iv": ("Intake", "IV fluids", "number", "mL", 0, 5000, None),
    "intake_enteral": ("Intake", "Enteral feed", "number", "mL", 0, 5000, None),
    "output_urine": ("Output", "Urine", "number", "mL", 0, 5000, None),
    "output_drain": ("Output", "Drain", "number", "mL", 0, 5000, None),
    "output_emesis": ("Output", "Emesis", "number", "mL", 0, 5000, None),
    "repositioned": ("Care activities", "Repositioned", "choice", None, None, None, ["Left side", "Right side", "Back", "Chair"]),
    "hygiene": ("Care activities", "Hygiene care", "choice", None, None, None, ["Full wash", "Assisted wash", "Oral care", "Declined"]),
}
VITAL_ROWS = [("temperature_c", "Temperature", "°C"), ("heart_rate", "Heart rate", "/min"), ("respiratory_rate", "Respiratory rate", "/min"),
              ("bp", "Blood pressure", "mmHg"), ("spo2", "SpO₂", "%")]

TEMPLATES: dict[str, dict] = {
    "admission": {"label": "Admission nursing assessment", "fields": [
        {"key": "presenting_concern", "label": "Presenting concern (patient's words)", "type": "text", "required": True},
        {"key": "orientation", "label": "Orientation", "type": "choice", "options": ["Oriented", "Partially oriented", "Disoriented"], "required": True},
        {"key": "mobility", "label": "Mobility", "type": "choice", "options": ["Independent", "Needs assistance", "Bed bound"], "required": True},
        {"key": "falls_history", "label": "Fall in the last 12 months", "type": "choice", "options": ["No", "Yes"], "required": True},
        {"key": "skin", "label": "Skin integrity", "type": "text", "required": True},
        {"key": "nutrition", "label": "Nutrition / swallowing concerns", "type": "text"},
        {"key": "devices", "label": "Lines, drains, devices", "type": "text"},
        {"key": "plan", "label": "Nursing priorities", "type": "text", "required": True},
    ]},
    "shift": {"label": "Shift assessment", "fields": [
        {"key": "neuro", "label": "Neurological", "type": "text", "required": True},
        {"key": "cardio_resp", "label": "Cardiovascular / respiratory", "type": "text", "required": True},
        {"key": "gi_gu", "label": "Gastrointestinal / genitourinary", "type": "text"},
        {"key": "skin", "label": "Skin", "type": "text"},
        {"key": "psychosocial", "label": "Psychosocial", "type": "text"},
        {"key": "concerns", "label": "Concerns escalated", "type": "text"},
    ]},
    "fall_risk": {"label": "Fall-risk screening (organization-defined)", "fields": [
        {"key": "history", "label": "History of falls", "type": "choice", "options": ["No", "Yes"], "required": True},
        {"key": "gait", "label": "Gait", "type": "choice", "options": ["Steady", "Unsteady", "Unable to walk"], "required": True},
        {"key": "aid", "label": "Walking aid", "type": "choice", "options": ["None", "Cane / frame", "Furniture"], "required": True},
        {"key": "cognition", "label": "Aware of own limitations", "type": "choice", "options": ["Yes", "No"], "required": True},
        {"key": "precautions", "label": "Precautions in place", "type": "text", "required": True},
    ]},
}


def _name(ctx, uid):
    u = ctx.db.get(User, uid) if uid else None
    return u.display_name if u else None


@router.get("/nursing/definitions")
def definitions(ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    return {"rows": [{"key": k, "group": g, "label": lb, "kind": kind, "unit": u, "min": mn, "max": mx, "options": opts}
                     for k, (g, lb, kind, u, mn, mx, opts) in ROWS.items()],
            "vitals": [{"key": k, "label": lb, "unit": u} for k, lb, u in VITAL_ROWS],
            "templates": [{"key": k, **v} for k, v in TEMPLATES.items()]}


# ---------------------------------------------------------------------------------------------- flowsheet

@router.get("/patients/{patient_id}/flowsheet")
def flowsheet(patient_id: uuid.UUID, hours: int = Query(24, ge=1, le=168), ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    p = get_patient(ctx, patient_id)
    since = now() - timedelta(hours=hours)
    obs = ctx.db.scalars(select(NursingObservation).where(NursingObservation.patient_id == p.id, NursingObservation.observed_at >= since)
                         .order_by(NursingObservation.observed_at)).all()
    superseded = {o.supersedes_id for o in obs if o.supersedes_id}
    current = [o for o in obs if o.id not in superseded]
    vit = ctx.db.scalars(select(VitalSigns).where(VitalSigns.patient_id == p.id, VitalSigns.measured_at >= since).order_by(VitalSigns.measured_at)).all()
    tot = {"intake": Decimal(0), "output": Decimal(0)}
    for o in current:
        g = ROWS.get(o.row_key, ("",))[0]
        if g in ("Intake", "Output") and o.value_num is not None:
            tot[g.lower()] += o.value_num
    return {
        "since": since,
        "observations": [{"id": o.id, "row_key": o.row_key, "value": float(o.value_num) if o.value_num is not None else o.value_text, "unit": o.unit,
                          "observed_at": o.observed_at, "recorded_by": _name(ctx, o.recorded_by_id), "corrected": o.supersedes_id is not None,
                          "correction_reason": o.correction_reason} for o in current],
        "vitals": [{"at": v.measured_at, "temperature_c": float(v.temperature_c) if v.temperature_c else None, "heart_rate": v.heart_rate,
                    "respiratory_rate": v.respiratory_rate, "bp": f"{v.systolic}/{v.diastolic}" if v.systolic else None, "spo2": v.spo2} for v in vit],
        "io": {"intake_ml": float(tot["intake"]), "output_ml": float(tot["output"]), "balance_ml": float(tot["intake"] - tot["output"]), "hours": hours},
    }


def _coerce(key: str, value) -> tuple[Decimal | None, str | None, str | None]:
    if key not in ROWS:
        raise bad_request(f"Unknown flowsheet row {key}")
    _, label, kind, unit, mn, mx, opts = ROWS[key]
    if kind == "number":
        try:
            v = Decimal(str(value))
        except Exception:
            raise bad_request(f"{label}: enter a number") from None
        if (mn is not None and v < mn) or (mx is not None and v > mx):
            raise bad_request(f"{label}: must be between {mn} and {mx}{' ' + unit if unit else ''}")
        return v, None, unit
    text = str(value).strip()
    if not text:
        raise bad_request(f"{label}: value required")
    if kind == "choice" and text not in opts:
        raise bad_request(f"{label}: choose one of {', '.join(opts)}")
    return None, text[:300], None


class ObservationsIn(BaseModel):
    observed_at: datetime | None = None
    values: dict[str, str | float | int] = Field(min_length=1, max_length=20)


@router.post("/patients/{patient_id}/flowsheet", status_code=201)
def record(patient_id: uuid.UUID, body: ObservationsIn, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    p = get_patient(ctx, patient_id, P.CLINICAL_WRITE)
    at = body.observed_at or now()
    if at > now() + timedelta(minutes=5):
        raise bad_request("Observations can't be documented in the future")
    stay = active_stay(ctx.db, ctx.org_id, p.id)
    rows = []
    for k, v in body.values.items():
        num, text, unit = _coerce(k, v)
        rows.append(NursingObservation(organization_id=ctx.org_id, patient_id=p.id, stay_id=stay.id if stay else None, row_key=k, value_num=num,
                                       value_text=text, unit=unit, observed_at=at, recorded_by_id=ctx.user.id))
    ctx.db.add_all(rows)
    ctx.audit("nursing.observations_recorded", resource_type="patient", resource_id=p.id, patient_id=p.id, details={"rows": list(body.values)})
    ctx.db.commit()
    return {"recorded": len(rows)}


class CorrectIn(BaseModel):
    value: str | float | int
    reason: str = Field(min_length=3, max_length=300)


@router.post("/flowsheet/{obs_id}/correct", status_code=201)
def correct(obs_id: uuid.UUID, body: CorrectIn, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    o = ctx.db.get(NursingObservation, obs_id)
    if not o or o.organization_id != ctx.org_id:
        raise not_found("Observation")
    get_patient(ctx, o.patient_id, P.CLINICAL_WRITE)
    if ctx.db.scalar(select(NursingObservation.id).where(NursingObservation.supersedes_id == o.id)):
        raise bad_request("This value was already corrected; correct the latest value")
    num, text, unit = _coerce(o.row_key, body.value)
    n = NursingObservation(organization_id=ctx.org_id, patient_id=o.patient_id, stay_id=o.stay_id, row_key=o.row_key, value_num=num, value_text=text,
                           unit=unit, observed_at=o.observed_at, recorded_by_id=ctx.user.id, supersedes_id=o.id, correction_reason=body.reason)
    ctx.db.add(n)
    ctx.audit("nursing.observation_corrected", resource_type="nursing_observation", resource_id=o.id, patient_id=o.patient_id, details={"reason": body.reason})
    ctx.db.commit()
    return {"id": n.id}


# ---------------------------------------------------------------------------------------------- assessments

def _assessment_out(ctx, a: NursingAssessment) -> dict:
    t = TEMPLATES.get(a.template_key, {})
    return {"id": a.id, "template_key": a.template_key, "template": t.get("label", a.template_key), "fields": t.get("fields", []), "data": a.data,
            "status": a.status, "author": _name(ctx, a.author_id), "author_id": a.author_id, "signed_by": _name(ctx, a.signed_by_id), "signed_at": a.signed_at,
            "amends_id": a.amends_id, "amendment_reason": a.amendment_reason, "created_at": a.created_at, "updated_at": a.updated_at}


def _assessment(ctx, aid) -> NursingAssessment:
    a = ctx.db.get(NursingAssessment, aid)
    if not a or a.organization_id != ctx.org_id:
        raise not_found("Assessment")
    get_patient(ctx, a.patient_id, P.CLINICAL_WRITE)
    return a


@router.get("/patients/{patient_id}/nursing-assessments")
def list_assessments(patient_id: uuid.UUID, ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    p = get_patient(ctx, patient_id)
    rows = ctx.db.scalars(select(NursingAssessment).where(NursingAssessment.patient_id == p.id).order_by(NursingAssessment.created_at.desc())).all()
    return [_assessment_out(ctx, a) for a in rows]


class AssessmentIn(BaseModel):
    template_key: str
    data: dict = Field(default_factory=dict)


@router.post("/patients/{patient_id}/nursing-assessments", status_code=201)
def create_assessment(patient_id: uuid.UUID, body: AssessmentIn, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    p = get_patient(ctx, patient_id, P.CLINICAL_WRITE)
    if body.template_key not in TEMPLATES:
        raise bad_request("Unknown assessment template")
    stay = active_stay(ctx.db, ctx.org_id, p.id)
    a = NursingAssessment(organization_id=ctx.org_id, patient_id=p.id, stay_id=stay.id if stay else None, template_key=body.template_key,
                          data=_clean(body.template_key, body.data), status="draft", author_id=ctx.user.id)
    ctx.db.add(a)
    ctx.audit("nursing.assessment_drafted", resource_type="nursing_assessment", resource_id=a.id, patient_id=p.id)
    ctx.db.commit()
    return _assessment_out(ctx, a)


def _clean(template_key: str, data: dict, *, require_all: bool = False) -> dict:
    out = {}
    for f in TEMPLATES[template_key]["fields"]:
        v = data.get(f["key"])
        if isinstance(v, str):
            v = v.strip()[:2000]
        if v in (None, ""):
            if require_all and f.get("required"):
                raise bad_request(f"{f['label']} is required before signing")
            continue
        if f["type"] == "choice" and v not in f["options"]:
            raise bad_request(f"{f['label']}: choose one of {', '.join(f['options'])}")
        out[f["key"]] = v
    return out


class DraftIn(BaseModel):
    data: dict


@router.put("/nursing-assessments/{aid}")
def save_draft(aid: uuid.UUID, body: DraftIn, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    a = _assessment(ctx, aid)
    if a.status != "draft":
        raise bad_request("Signed assessments can't be edited; create an amendment")
    if a.author_id != ctx.user.id:
        raise forbidden("Only the author can edit a draft assessment")
    a.data = _clean(a.template_key, body.data)
    ctx.db.commit()
    return _assessment_out(ctx, a)


@router.post("/nursing-assessments/{aid}/sign")
def sign_assessment(aid: uuid.UUID, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    a = _assessment(ctx, aid)
    if a.status != "draft":
        raise bad_request("Already signed")
    if a.author_id != ctx.user.id:
        raise forbidden("Only the author signs their assessment")
    a.data = _clean(a.template_key, a.data, require_all=True)
    a.status, a.signed_by_id, a.signed_at = "signed", ctx.user.id, now()
    if a.amends_id:
        orig = ctx.db.get(NursingAssessment, a.amends_id)
        if orig and orig.status == "signed":
            orig.status = "amended"
    ctx.audit("nursing.assessment_signed", resource_type="nursing_assessment", resource_id=a.id, patient_id=a.patient_id,
              details={"amends": str(a.amends_id) if a.amends_id else None})
    ctx.db.commit()
    return _assessment_out(ctx, a)


class AmendIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


@router.post("/nursing-assessments/{aid}/amend", status_code=201)
def amend(aid: uuid.UUID, body: AmendIn, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    a = _assessment(ctx, aid)
    if a.status != "signed":
        raise bad_request("Only the current signed version can be amended")
    n = NursingAssessment(organization_id=ctx.org_id, patient_id=a.patient_id, stay_id=a.stay_id, template_key=a.template_key, data=dict(a.data),
                          status="draft", author_id=ctx.user.id, amends_id=a.id, amendment_reason=body.reason)
    ctx.db.add(n)
    ctx.audit("nursing.assessment_amendment_started", resource_type="nursing_assessment", resource_id=a.id, patient_id=a.patient_id)
    ctx.db.commit()
    return _assessment_out(ctx, n)


# ---------------------------------------------------------------------------------------------- care plans

def _plan_out(ctx, c: NursingCarePlan) -> dict:
    return {"id": c.id, "problem": c.problem, "goal": c.goal, "interventions": c.interventions, "responsible_role": c.responsible_role,
            "status": c.status, "review_due_at": c.review_due_at, "progress": c.progress, "created_by": _name(ctx, c.created_by_id), "created_at": c.created_at,
            "overdue_review": bool(c.status == "active" and c.review_due_at and c.review_due_at < now())}


@router.get("/patients/{patient_id}/care-plans")
def list_plans(patient_id: uuid.UUID, ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    p = get_patient(ctx, patient_id)
    return [_plan_out(ctx, c) for c in ctx.db.scalars(select(NursingCarePlan).where(NursingCarePlan.patient_id == p.id)
                                                      .order_by(NursingCarePlan.status, NursingCarePlan.created_at.desc()))]


class PlanIn(BaseModel):
    problem: str = Field(min_length=3, max_length=300)
    goal: str = Field(min_length=3, max_length=500)
    interventions: list[str] = Field(min_length=1, max_length=12)
    responsible_role: str | None = Field(default="nurse", max_length=40)
    review_in_hours: int = Field(default=24, ge=1, le=168)


@router.post("/patients/{patient_id}/care-plans", status_code=201)
def create_plan(patient_id: uuid.UUID, body: PlanIn, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    p = get_patient(ctx, patient_id, P.CLINICAL_WRITE)
    stay = active_stay(ctx.db, ctx.org_id, p.id)
    c = NursingCarePlan(organization_id=ctx.org_id, patient_id=p.id, stay_id=stay.id if stay else None, problem=body.problem.strip(), goal=body.goal.strip(),
                        interventions=[i.strip()[:300] for i in body.interventions if i.strip()], responsible_role=body.responsible_role,
                        review_due_at=now() + timedelta(hours=body.review_in_hours), created_by_id=ctx.user.id)
    ctx.db.add(c)
    ctx.audit("nursing.care_plan_created", resource_type="nursing_care_plan", resource_id=c.id, patient_id=p.id)
    ctx.db.commit()
    return _plan_out(ctx, c)


class ProgressIn(BaseModel):
    note: str = Field(min_length=3, max_length=1000)
    status: Literal["active", "met", "not_met", "discontinued"] = "active"
    review_in_hours: int | None = Field(default=24, ge=1, le=168)


@router.post("/care-plans/{plan_id}/progress")
def plan_progress(plan_id: uuid.UUID, body: ProgressIn, ctx: TenantContext = Depends(require(P.NURSING_WRITE))):
    c = ctx.db.get(NursingCarePlan, plan_id)
    if not c or c.organization_id != ctx.org_id:
        raise not_found("Care plan")
    get_patient(ctx, c.patient_id, P.CLINICAL_WRITE)
    if c.status != "active":
        raise bad_request("This care plan is closed")
    c.progress = [*c.progress, {"at": now().isoformat(), "by": ctx.user.display_name, "note": body.note.strip(), "status": body.status}]
    c.status = body.status
    c.review_due_at = now() + timedelta(hours=body.review_in_hours) if body.status == "active" and body.review_in_hours else c.review_due_at
    ctx.audit("nursing.care_plan_progress", resource_type="nursing_care_plan", resource_id=c.id, patient_id=c.patient_id, details={"status": body.status})
    ctx.db.commit()
    return _plan_out(ctx, c)
