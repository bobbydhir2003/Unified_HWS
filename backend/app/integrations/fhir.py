"""FHIR R4 read-only API (foundation for interoperability).

Implements read + patient-scoped search for Patient, Encounter, Condition, AllergyIntolerance, MedicationStatement and
Observation (vital signs + laboratory). Uses the same authentication, tenancy and patient-access rules as the rest of
the API. Not yet: write operations, SMART on FHIR launch/scopes, US Core profile conformance testing, bulk export.
"""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.deps import TenantContext, get_ctx
from app.core.permissions import P
from app.core.security import now
from app.models import Allergy, Encounter, LabResult, Patient, PatientMedication, Problem, VitalSigns
from app.services.patients import get_patient

router = APIRouter(prefix="/fhir/R4", tags=["fhir"])
FHIR_JSON = "application/fhir+json"
LOINC = "http://loinc.org"
ICD10 = "http://hl7.org/fhir/sid/icd-10-cm"


def _resp(body: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, media_type=FHIR_JSON)


def _outcome(status: int, code: str, text: str) -> JSONResponse:
    return _resp({"resourceType": "OperationOutcome", "issue": [{"severity": "error", "code": code, "diagnostics": text}]}, status)


def _iso(v) -> str | None:
    if v is None:
        return None
    return v.isoformat() if isinstance(v, (date, datetime)) else str(v)


def _ref(kind: str, id_) -> dict:
    return {"reference": f"{kind}/{id_}"}


def patient_res(p: Patient) -> dict:
    gender = {"female": "female", "male": "male", "intersex": "other"}.get(p.sex_at_birth, "unknown")
    r = {
        "resourceType": "Patient", "id": str(p.id), "meta": {"lastUpdated": _iso(p.updated_at)},
        "identifier": [{"use": "usual", "type": {"text": "MRN"}, "system": "urn:undeclared:mrn", "value": p.mrn}],
        "active": p.status == "active", "name": [{"use": "official", "family": p.last_name, "given": [x for x in [p.first_name, p.middle_name] if x]}],
        "gender": gender, "birthDate": _iso(p.date_of_birth),
        "telecom": [t for t in [{"system": "phone", "value": p.phone, "use": "mobile"} if p.phone else None,
                                {"system": "email", "value": p.email} if p.email else None] if t],
        "address": [{"line": [x for x in [p.address_line1, p.address_line2] if x], "city": p.city, "state": p.state, "postalCode": p.postal_code}] if p.address_line1 else [],
        "communication": [{"language": {"text": p.preferred_language}, "preferred": True}],
    }
    if p.status == "deceased":
        r["deceasedBoolean"] = True
    return r


def encounter_res(e: Encounter) -> dict:
    status = {"in_progress": "in-progress", "completed": "finished", "cancelled": "cancelled"}[e.status]
    cls = {"code": "VR", "display": "virtual"} if e.encounter_type == "telehealth" else {"code": "AMB", "display": "ambulatory"}
    return {
        "resourceType": "Encounter", "id": str(e.id), "status": status,
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", **cls}, "type": [{"text": e.encounter_type.replace("_", " ")}],
        "subject": _ref("Patient", e.patient_id), "participant": [{"individual": {"display": e.provider.user.display_name}}],
        "period": {"start": _iso(e.started_at), **({"end": _iso(e.completed_at)} if e.completed_at else {})},
        "reasonCode": [{"text": e.chief_complaint}] if e.chief_complaint else [],
        "diagnosis": [{"condition": {"display": f"{d.code} {d.description}"}, "rank": d.rank} for d in e.diagnoses],
    }


def condition_res(c: Problem) -> dict:
    clinical = {"active": "active", "resolved": "resolved", "inactive": "inactive"}.get(c.status, "active")
    return {
        "resourceType": "Condition", "id": str(c.id), "subject": _ref("Patient", c.patient_id),
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": clinical}]},
        "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                                           "code": "entered-in-error" if c.status == "entered_in_error" else "confirmed"}]},
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-category", "code": "problem-list-item"}]}],
        "code": {"coding": [{"system": ICD10, "code": c.code, "display": c.description}] if c.code else [], "text": c.description},
        **({"onsetDateTime": _iso(c.onset_date)} if c.onset_date else {}), **({"abatementDateTime": _iso(c.resolved_date)} if c.resolved_date else {}),
        "recordedDate": _iso(c.created_at),
    }


def allergy_res(a: Allergy) -> dict:
    crit = "high" if a.severity in ("severe", "life_threatening") else "low"
    return {
        "resourceType": "AllergyIntolerance", "id": str(a.id), "patient": _ref("Patient", a.patient_id),
        "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                                       "code": "active" if a.status == "active" else "inactive"}]},
        "category": [{"medication": "medication", "food": "food", "environmental": "environment"}.get(a.category, "biologic")],
        "criticality": crit, "code": {"text": a.substance}, "recordedDate": _iso(a.created_at),
        "reaction": [{"manifestation": [{"text": a.reaction}], "severity": {"mild": "mild", "moderate": "moderate"}.get(a.severity, "severe")}] if a.reaction else [],
    }


def medication_res(m: PatientMedication) -> dict:
    status = {"active": "active", "completed": "completed", "discontinued": "stopped", "entered_in_error": "entered-in-error"}[m.status]
    return {
        "resourceType": "MedicationStatement", "id": str(m.id), "status": status, "subject": _ref("Patient", m.patient_id),
        "medicationCodeableConcept": {"text": f"{m.name} {m.dose or ''}".strip()},
        "dosage": [{"text": ", ".join(x for x in [m.dose, m.route, m.frequency] if x)}] if (m.dose or m.frequency) else [],
        **({"effectivePeriod": {"start": _iso(m.start_date), **({"end": _iso(m.end_date)} if m.end_date else {})}} if m.start_date else {}),
        "dateAsserted": _iso(m.created_at),
    }


VITAL_CODES = [("systolic", "8480-6", "Systolic blood pressure", "mm[Hg]"), ("diastolic", "8462-4", "Diastolic blood pressure", "mm[Hg]"),
               ("heart_rate", "8867-4", "Heart rate", "/min"), ("respiratory_rate", "9279-1", "Respiratory rate", "/min"),
               ("temperature_c", "8310-5", "Body temperature", "Cel"), ("spo2", "59408-5", "Oxygen saturation", "%"),
               ("height_cm", "8302-2", "Body height", "cm"), ("weight_kg", "29463-7", "Body weight", "kg")]


def vitals_res(v: VitalSigns) -> dict:
    comps = [{"code": {"coding": [{"system": LOINC, "code": c, "display": d}]}, "valueQuantity": {"value": float(getattr(v, f)), "unit": u}}
             for f, c, d, u in VITAL_CODES if getattr(v, f) is not None]
    return {
        "resourceType": "Observation", "id": f"vs-{v.id}", "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs"}]}],
        "code": {"coding": [{"system": LOINC, "code": "85353-1", "display": "Vital signs panel"}]}, "subject": _ref("Patient", v.patient_id),
        **({"encounter": _ref("Encounter", v.encounter_id)} if v.encounter_id else {}), "effectiveDateTime": _iso(v.measured_at), "component": comps,
    }


def lab_res(r: LabResult) -> dict:
    interp = {"high": "H", "low": "L", "critical_high": "HH", "critical_low": "LL", "abnormal": "A", "normal": "N"}.get(r.flag, "N")
    res = {
        "resourceType": "Observation", "id": f"lab-{r.id}", "status": "final" if r.status == "final" else "preliminary",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
        "code": {"text": r.name}, "subject": _ref("Patient", r.patient_id), "effectiveDateTime": _iso(r.resulted_at),
        "interpretation": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": interp}]}],
    }
    try:
        res["valueQuantity"] = {"value": float(r.value), "unit": r.unit or ""}
    except ValueError:
        res["valueString"] = r.value
    if r.reference_range and "-" in r.reference_range:
        lo, hi = r.reference_range.split("-", 1)
        res["referenceRange"] = [{"low": {"value": float(lo)}, "high": {"value": float(hi)}}] if lo.strip() and hi.strip() else [{"text": r.reference_range}]
    return res


def _bundle(request: Request, resources: list[dict]) -> JSONResponse:
    base = str(request.base_url).rstrip("/") + "/api/v1/fhir/R4"
    return _resp({"resourceType": "Bundle", "type": "searchset", "total": len(resources), "timestamp": _iso(now()),
                  "link": [{"relation": "self", "url": str(request.url)}],
                  "entry": [{"fullUrl": f"{base}/{r['resourceType']}/{r['id']}", "resource": r, "search": {"mode": "match"}} for r in resources]})


def _pid(ref: str | None) -> uuid.UUID | None:
    if not ref:
        return None
    try:
        return uuid.UUID(ref.split("/")[-1])
    except ValueError:
        return None


@router.get("/metadata")
def capability(request: Request):
    types = ["Patient", "Encounter", "Condition", "AllergyIntolerance", "MedicationStatement", "Observation"]
    return _resp({
        "resourceType": "CapabilityStatement", "status": "active", "date": _iso(now()), "kind": "instance", "fhirVersion": "4.0.1",
        "format": ["json"], "software": {"name": "Undeclared", "version": "0.1.0"},
        "implementation": {"description": "Undeclared FHIR R4 read API (development; not certified)", "url": str(request.base_url) + "api/fhir/R4"},
        "rest": [{"mode": "server", "security": {"description": "Bearer token + X-Organization-Id; SMART on FHIR not yet supported."},
                  "resource": [{"type": t, "interaction": [{"code": "read"}, {"code": "search-type"}],
                                "searchParam": [] if t == "Patient" else [{"name": "patient", "type": "reference"}]} for t in types]}],
    })


@router.get("/Patient/{pid}")
def read_patient(pid: str, ctx: TenantContext = Depends(get_ctx)):
    p_id = _pid(pid)
    if not p_id:
        return _outcome(404, "not-found", "Patient not found")
    p = get_patient(ctx, p_id)
    ctx.audit("fhir.read", resource_type="Patient", resource_id=p.id, patient_id=p.id)
    ctx.db.commit()
    return _resp(patient_res(p))


@router.get("/Patient")
def search_patients(request: Request, identifier: str | None = None, family: str | None = None, birthdate: date | None = None,
                    _count: int = Query(20, le=100), ctx: TenantContext = Depends(get_ctx)):
    if ctx.is_patient_only:  # patients can only see themselves
        rows = ctx.db.scalars(select(Patient).where(Patient.organization_id == ctx.org_id, Patient.portal_user_id == ctx.user.id)).all()
    else:
        ctx.require(P.PATIENTS_READ)
        if not (identifier or family or birthdate):
            return _outcome(400, "required", "Provide at least one of: identifier, family, birthdate")
        q = select(Patient).where(Patient.organization_id == ctx.org_id, Patient.is_restricted.is_(False))
        if identifier:
            q = q.where(Patient.mrn == identifier.split("|")[-1].upper())
        if family:
            q = q.where(Patient.last_name.ilike(f"{family}%"))
        if birthdate:
            q = q.where(Patient.date_of_birth == birthdate)
        rows = ctx.db.scalars(q.limit(_count)).all()
    ctx.audit("fhir.search", resource_type="Patient", details={"results": len(rows)})
    ctx.db.commit()
    return _bundle(request, [patient_res(p) for p in rows])


def _clinical_search(request: Request, ctx: TenantContext, patient: str | None, rtype: str):
    pid = _pid(patient)
    if not pid:
        return _outcome(400, "required", "The 'patient' search parameter is required")
    p = get_patient(ctx, pid, P.CLINICAL_READ)
    db = ctx.db
    if rtype == "Encounter":
        res = [encounter_res(e) for e in db.scalars(select(Encounter).where(Encounter.patient_id == p.id).order_by(Encounter.started_at.desc())).all()]
    elif rtype == "Condition":
        res = [condition_res(c) for c in db.scalars(select(Problem).where(Problem.patient_id == p.id)).all()]
    elif rtype == "AllergyIntolerance":
        res = [allergy_res(a) for a in db.scalars(select(Allergy).where(Allergy.patient_id == p.id, Allergy.status != "entered_in_error")).all()]
    elif rtype == "MedicationStatement":
        res = [medication_res(m) for m in db.scalars(select(PatientMedication).where(PatientMedication.patient_id == p.id)).all()]
    else:
        cat = request.query_params.get("category")
        res = []
        if cat in (None, "vital-signs"):
            res += [vitals_res(v) for v in db.scalars(select(VitalSigns).where(VitalSigns.patient_id == p.id).order_by(VitalSigns.measured_at.desc())).all()]
        if cat in (None, "laboratory"):
            res += [lab_res(r) for r in db.scalars(select(LabResult).where(LabResult.patient_id == p.id).order_by(LabResult.resulted_at.desc())).all()]
    ctx.audit("fhir.search", resource_type=rtype, patient_id=p.id, details={"results": len(res)})
    ctx.db.commit()
    return _bundle(request, res)


for _rtype in ("Encounter", "Condition", "AllergyIntolerance", "MedicationStatement", "Observation"):
    def _handler(request: Request, patient: str | None = None, ctx: TenantContext = Depends(get_ctx), _t=_rtype):
        return _clinical_search(request, ctx, patient, _t)
    router.add_api_route(f"/{_rtype}", _handler, methods=["GET"], name=f"fhir_search_{_rtype}")
