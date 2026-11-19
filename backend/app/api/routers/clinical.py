import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import TenantContext, get_ctx, require
from app.core.errors import bad_request, not_found
from app.core.permissions import P
from app.core.security import now
from app.data.icd10_common import ICD10
from app.models import (
    Allergy,
    Appointment,
    ClinicalNote,
    ClinicalNoteVersion,
    ClinicalTemplate,
    Encounter,
    EncounterDiagnosis,
    HistoryEntry,
    PatientMedication,
    Problem,
    VitalSigns,
)
from app.schemas.clinical import (
    AddendumIn,
    AllergyIn,
    AllergyOut,
    DiagnosisIn,
    EncounterCreate,
    EncounterDetail,
    EncounterOut,
    EncounterUpdate,
    HistoryIn,
    HistoryOut,
    MedicationIn,
    MedicationOut,
    NoteContent,
    NoteCreate,
    NoteOut,
    NoteSave,
    NoteSign,
    NoteVersionOut,
    ProblemIn,
    ProblemOut,
    TemplateIn,
    TemplateOut,
    UserRef,
    VitalsIn,
    VitalsOut,
)
from app.schemas.common import Message
from app.services.notes import add_addendum, note_out, save_version, sign_note, user_ref
from app.services.patients import get_patient

router = APIRouter(tags=["clinical"])


def _owned(ctx: TenantContext, model, obj_id: uuid.UUID, what: str):
    obj = ctx.db.get(model, obj_id)
    if not obj or obj.organization_id != ctx.org_id:
        raise not_found(what)
    return obj


# ---------- Generic chart lists (allergies, medications, problems, history) ----------

def _list_endpoint(model, out, order):
    def handler(patient_id: uuid.UUID, include_inactive: bool = True, ctx: TenantContext = Depends(get_ctx)):
        p = get_patient(ctx, patient_id, P.CLINICAL_READ)
        q = select(model).where(model.patient_id == p.id)
        if hasattr(model, "status"):
            q = q.where(model.status != "entered_in_error")
            if not include_inactive:
                q = q.where(model.status == "active")
        return [out.model_validate(r) for r in ctx.db.scalars(q.order_by(*order)).all()]
    return handler


def _create_endpoint(model, schema, out, action):
    def handler(patient_id: uuid.UUID, body: schema, ctx: TenantContext = Depends(get_ctx)):  # type: ignore[valid-type]
        p = get_patient(ctx, patient_id, P.CLINICAL_WRITE)
        data = body.model_dump()
        if model is Problem and data.get("encounter_id"):
            _owned(ctx, Encounter, data["encounter_id"], "Encounter")
        obj = model(organization_id=ctx.org_id, patient_id=p.id, recorded_by_id=ctx.user.id, **data)
        ctx.db.add(obj)
        ctx.db.flush()
        ctx.audit(f"{action}.created", resource_type=action, resource_id=obj.id, patient_id=p.id)
        ctx.db.commit()
        return out.model_validate(obj)
    return handler


def _update_endpoint(model, schema, out, action, what):
    def handler(item_id: uuid.UUID, body: schema, ctx: TenantContext = Depends(get_ctx)):  # type: ignore[valid-type]
        obj = _owned(ctx, model, item_id, what)
        get_patient(ctx, obj.patient_id, P.CLINICAL_WRITE)
        for k, v in body.model_dump().items():
            setattr(obj, k, v)
        ctx.audit(f"{action}.updated", resource_type=action, resource_id=obj.id, patient_id=obj.patient_id,
                  details={"status": getattr(obj, "status", None)})
        ctx.db.commit()
        return out.model_validate(obj)
    return handler


for path, model, schema, out, action, what, order in [
    ("allergies", Allergy, AllergyIn, AllergyOut, "allergy", "Allergy", (Allergy.status, Allergy.substance)),
    ("medications", PatientMedication, MedicationIn, MedicationOut, "medication", "Medication",
     (PatientMedication.status, PatientMedication.name)),
    ("problems", Problem, ProblemIn, ProblemOut, "problem", "Problem", (Problem.status, Problem.created_at.desc())),
    ("history", HistoryEntry, HistoryIn, HistoryOut, "history", "History entry",
     (HistoryEntry.category, HistoryEntry.created_at)),
]:
    router.add_api_route(f"/patients/{{patient_id}}/{path}", _list_endpoint(model, out, order), methods=["GET"],
                         response_model=list[out], name=f"list_{path}")
    router.add_api_route(f"/patients/{{patient_id}}/{path}", _create_endpoint(model, schema, out, action),
                         methods=["POST"], response_model=out, status_code=201, name=f"create_{path}")
    router.add_api_route(f"/{path}/{{item_id}}", _update_endpoint(model, schema, out, action, what), methods=["PUT"],
                         response_model=out, name=f"update_{path}")


@router.delete("/history/{item_id}", response_model=Message)
def delete_history(item_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    h = _owned(ctx, HistoryEntry, item_id, "History entry")
    get_patient(ctx, h.patient_id, P.CLINICAL_WRITE)
    ctx.db.delete(h)
    ctx.audit("history.deleted", resource_type="history", resource_id=item_id, patient_id=h.patient_id)
    ctx.db.commit()
    return Message(message="Removed")


# ---------- Vitals ----------

def _vitals_out(v: VitalSigns) -> VitalsOut:
    return VitalsOut.model_validate(v)


@router.get("/patients/{patient_id}/vitals", response_model=list[VitalsOut])
def list_vitals(patient_id: uuid.UUID, limit: int = Query(50, le=500), ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id, P.CLINICAL_READ)
    rows = ctx.db.scalars(select(VitalSigns).where(VitalSigns.patient_id == p.id)
                          .order_by(VitalSigns.measured_at.desc()).limit(limit)).all()
    return [_vitals_out(v) for v in rows]


@router.post("/patients/{patient_id}/vitals", response_model=VitalsOut, status_code=201)
def record_vitals(patient_id: uuid.UUID, body: VitalsIn, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id, P.CLINICAL_WRITE)
    data = body.model_dump(exclude_none=True)
    if len([k for k in data if k not in ("encounter_id", "measured_at")]) == 0:
        raise bad_request("Enter at least one measurement")
    if (body.systolic is None) != (body.diastolic is None):
        raise bad_request("Blood pressure needs both systolic and diastolic values")
    if body.systolic and body.diastolic and body.diastolic >= body.systolic:
        raise bad_request("Diastolic must be lower than systolic")
    if body.encounter_id:
        e = _owned(ctx, Encounter, body.encounter_id, "Encounter")
        if e.patient_id != p.id:
            raise bad_request("Encounter belongs to a different patient")
        if e.status != "in_progress":
            raise bad_request("Encounter is closed")
    data.setdefault("measured_at", now())
    v = VitalSigns(organization_id=ctx.org_id, patient_id=p.id, recorded_by_id=ctx.user.id, **data)
    ctx.db.add(v)
    ctx.db.flush()
    ctx.audit("vitals.recorded", resource_type="vitals", resource_id=v.id, patient_id=p.id)
    ctx.db.commit()
    return _vitals_out(v)


# ---------- Encounters ----------

def encounter_out(ctx: TenantContext, e: Encounter, note_status: str | None = None) -> EncounterOut:
    p = e.patient
    return EncounterOut(
        id=e.id, patient_id=e.patient_id,
        patient={"id": p.id, "name": p.full_name, "mrn": p.mrn, "date_of_birth": p.date_of_birth, "sex_at_birth": p.sex_at_birth},
        provider=UserRef(id=e.provider.user.id, name=e.provider.user.display_name), provider_id=e.provider_id,
        clinic_id=e.clinic_id, appointment_id=e.appointment_id, encounter_type=e.encounter_type, status=e.status,
        chief_complaint=e.chief_complaint, follow_up=e.follow_up, started_at=e.started_at, completed_at=e.completed_at,
        diagnoses=[d for d in e.diagnoses], note_status=note_status,
    )


def _encounter(ctx: TenantContext, encounter_id: uuid.UUID, perm: str = P.CLINICAL_READ) -> Encounter:
    e = _owned(ctx, Encounter, encounter_id, "Encounter")
    get_patient(ctx, e.patient_id, perm)
    ctx.require_clinic(e.clinic_id)
    return e


def _detail(ctx: TenantContext, e: Encounter) -> EncounterDetail:
    notes = ctx.db.scalars(select(ClinicalNote).where(ClinicalNote.encounter_id == e.id).order_by(ClinicalNote.created_at)).all()
    vitals = ctx.db.scalars(select(VitalSigns).where(VitalSigns.encounter_id == e.id).order_by(VitalSigns.measured_at.desc())).all()
    base = encounter_out(ctx, e, notes[0].status if notes else None)
    return EncounterDetail(**base.model_dump(), notes=[note_out(n) for n in notes], vitals=[_vitals_out(v) for v in vitals])


@router.get("/patients/{patient_id}/encounters", response_model=list[EncounterOut])
def list_encounters(patient_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id, P.CLINICAL_READ)
    rows = ctx.db.scalars(select(Encounter).where(Encounter.patient_id == p.id).order_by(Encounter.started_at.desc())).all()
    statuses = dict(ctx.db.execute(select(ClinicalNote.encounter_id, ClinicalNote.status)
                                   .where(ClinicalNote.encounter_id.in_([r.id for r in rows]))).all())
    return [encounter_out(ctx, e, statuses.get(e.id)) for e in rows]


@router.get("/encounters", response_model=list[EncounterOut])
def my_encounters(status: str | None = "in_progress", mine: bool = True, ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    q = select(Encounter).where(Encounter.organization_id == ctx.org_id)
    if status:
        q = q.where(Encounter.status == status)
    if mine and ctx.provider:
        q = q.where(Encounter.provider_id == ctx.provider.id)
    if ctx.clinic_ids is not None:
        q = q.where(Encounter.clinic_id.in_(ctx.clinic_ids))
    rows = ctx.db.scalars(q.order_by(Encounter.started_at.desc()).limit(100)).all()
    statuses = dict(ctx.db.execute(select(ClinicalNote.encounter_id, ClinicalNote.status)
                                   .where(ClinicalNote.encounter_id.in_([r.id for r in rows]))).all())
    return [encounter_out(ctx, e, statuses.get(e.id)) for e in rows]


@router.post("/encounters", response_model=EncounterDetail, status_code=201)
def start_encounter(body: EncounterCreate, ctx: TenantContext = Depends(require(P.CLINICAL_WRITE))):
    p = get_patient(ctx, body.patient_id, P.CLINICAL_WRITE)
    appt = None
    if body.appointment_id:
        appt = _owned(ctx, Appointment, body.appointment_id, "Appointment")
        if appt.patient_id != p.id:
            raise bad_request("Appointment belongs to a different patient")
        existing = ctx.db.scalar(select(Encounter).where(Encounter.appointment_id == appt.id))
        if existing:
            return _detail(ctx, existing)
        if appt.status not in ("checked_in", "roomed", "confirmed", "scheduled"):
            raise bad_request(f"Can't start a visit for an appointment that is {appt.status.replace('_', ' ')}")
        provider_id, clinic_id = appt.provider_id, appt.clinic_id
    else:
        if not ctx.provider:
            raise bad_request("Unscheduled encounters must be started by a provider")
        provider_id = ctx.provider.id
        clinic_id = body.clinic_id or p.primary_clinic_id
        if not clinic_id:
            raise bad_request("Choose a clinic for this encounter")
    ctx.require_clinic(clinic_id)
    etype = "telehealth" if appt and appt.mode == "telehealth" else body.encounter_type
    e = Encounter(organization_id=ctx.org_id, clinic_id=clinic_id, patient_id=p.id, provider_id=provider_id,
                  appointment_id=appt.id if appt else None, encounter_type=etype,
                  chief_complaint=body.chief_complaint or (appt.reason if appt else None))
    ctx.db.add(e)
    if appt:
        appt.status = "in_progress"
    ctx.db.flush()
    ctx.audit("encounter.started", resource_type="encounter", resource_id=e.id, patient_id=p.id)
    ctx.db.commit()
    ctx.db.refresh(e)
    return _detail(ctx, e)


@router.get("/encounters/{encounter_id}", response_model=EncounterDetail)
def get_encounter(encounter_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    e = _encounter(ctx, encounter_id)
    ctx.audit("encounter.viewed", resource_type="encounter", resource_id=e.id, patient_id=e.patient_id)
    ctx.db.commit()
    return _detail(ctx, e)


@router.patch("/encounters/{encounter_id}", response_model=EncounterDetail)
def update_encounter(encounter_id: uuid.UUID, body: EncounterUpdate, ctx: TenantContext = Depends(get_ctx)):
    e = _encounter(ctx, encounter_id, P.CLINICAL_WRITE)
    if e.status != "in_progress":
        raise bad_request("Encounter is closed")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    ctx.db.commit()
    return _detail(ctx, e)


@router.put("/encounters/{encounter_id}/diagnoses", response_model=EncounterDetail)
def set_diagnoses(encounter_id: uuid.UUID, body: list[DiagnosisIn], ctx: TenantContext = Depends(get_ctx)):
    e = _encounter(ctx, encounter_id, P.CLINICAL_WRITE)
    if e.status != "in_progress":
        raise bad_request("Encounter is closed")
    codes = [d.code.upper() for d in body]
    if len(codes) != len(set(codes)):
        raise bad_request("Duplicate diagnosis codes")
    e.diagnoses.clear()
    ctx.db.flush()
    existing_problems = set(ctx.db.scalars(select(Problem.code).where(Problem.patient_id == e.patient_id,
                                                                     Problem.status == "active")).all())
    for rank, d in enumerate(body, start=1):
        e.diagnoses.append(EncounterDiagnosis(organization_id=ctx.org_id, code=d.code.upper(), description=d.description, rank=rank))
        if d.add_to_problem_list and d.code.upper() not in existing_problems:
            ctx.db.add(Problem(organization_id=ctx.org_id, patient_id=e.patient_id, code=d.code.upper(),
                               description=d.description, encounter_id=e.id, recorded_by_id=ctx.user.id))
    ctx.audit("encounter.diagnoses_set", resource_type="encounter", resource_id=e.id, patient_id=e.patient_id,
              details={"codes": codes})
    ctx.db.commit()
    ctx.db.refresh(e)
    return _detail(ctx, e)


@router.post("/encounters/{encounter_id}/complete", response_model=EncounterDetail)
def complete_encounter(encounter_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    e = _encounter(ctx, encounter_id, P.CLINICAL_SIGN)
    if e.status != "in_progress":
        raise bad_request("Encounter is not in progress")
    notes = ctx.db.scalars(select(ClinicalNote).where(ClinicalNote.encounter_id == e.id)).all()
    if not notes or any(n.status != "signed" for n in notes):
        raise bad_request("All notes must be signed before the encounter can be completed")
    if not e.diagnoses:
        raise bad_request("Add at least one diagnosis before completing the encounter")
    e.status, e.completed_at = "completed", now()
    if e.appointment_id:
        appt = ctx.db.get(Appointment, e.appointment_id)
        if appt and appt.status == "in_progress":
            appt.status = "completed"
    ctx.audit("encounter.completed", resource_type="encounter", resource_id=e.id, patient_id=e.patient_id)
    ctx.db.commit()
    return _detail(ctx, e)


# ---------- Notes ----------

def _note(ctx: TenantContext, note_id: uuid.UUID, perm: str = P.CLINICAL_READ) -> tuple[ClinicalNote, Encounter]:
    n = _owned(ctx, ClinicalNote, note_id, "Note")
    return n, _encounter(ctx, n.encounter_id, perm)


@router.post("/encounters/{encounter_id}/notes", response_model=NoteOut, status_code=201)
def create_note(encounter_id: uuid.UUID, body: NoteCreate, ctx: TenantContext = Depends(get_ctx)):
    e = _encounter(ctx, encounter_id, P.CLINICAL_WRITE)
    if e.status != "in_progress":
        raise bad_request("Encounter is closed")
    if ctx.db.scalar(select(ClinicalNote.id).where(ClinicalNote.encounter_id == e.id, ClinicalNote.status == "draft")):
        raise bad_request("This encounter already has a draft note")
    content, source = NoteContent(), "manual"
    if body.template_id:
        t = _owned(ctx, ClinicalTemplate, body.template_id, "Template")
        content, source = NoteContent(**t.content), "template"
    if e.chief_complaint and not content.subjective:
        content.subjective = f"Chief complaint: {e.chief_complaint}\n"
    n = ClinicalNote(organization_id=ctx.org_id, encounter_id=e.id, patient_id=e.patient_id, author_id=ctx.user.id,
                     title=body.title, content={}, current_version=0)
    ctx.db.add(n)
    ctx.db.flush()
    save_version(ctx, n, content, 0, source)
    ctx.audit("note.created", resource_type="note", resource_id=n.id, patient_id=e.patient_id)
    ctx.db.commit()
    ctx.db.refresh(n)
    return note_out(n)


@router.get("/notes/{note_id}", response_model=NoteOut)
def get_note(note_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    n, _ = _note(ctx, note_id)
    return note_out(n)


@router.put("/notes/{note_id}", response_model=NoteOut)
def save_note(note_id: uuid.UUID, body: NoteSave, ctx: TenantContext = Depends(get_ctx)):
    n, e = _note(ctx, note_id, P.CLINICAL_WRITE)
    if e.status != "in_progress":
        raise bad_request("Encounter is closed")
    save_version(ctx, n, body.content, body.expected_version, body.source)
    if body.title:
        n.title = body.title
    ctx.audit("note.saved", resource_type="note", resource_id=n.id, patient_id=n.patient_id,
              details={"version": n.current_version, "source": body.source})
    ctx.db.commit()
    ctx.db.refresh(n)
    return note_out(n)


@router.post("/notes/{note_id}/sign", response_model=NoteOut)
def sign(note_id: uuid.UUID, body: NoteSign, ctx: TenantContext = Depends(get_ctx)):
    n, e = _note(ctx, note_id, P.CLINICAL_SIGN)
    sign_note(ctx, n, e, body.expected_version, body.attest_ai_reviewed)
    ctx.audit("note.signed", resource_type="note", resource_id=n.id, patient_id=n.patient_id,
              details={"version": n.current_version, "ai_content": n.has_ai_content})
    ctx.db.commit()
    ctx.db.refresh(n)
    return note_out(n)


@router.post("/notes/{note_id}/addenda", response_model=NoteOut, status_code=201)
def addendum(note_id: uuid.UUID, body: AddendumIn, ctx: TenantContext = Depends(get_ctx)):
    n, _ = _note(ctx, note_id, P.CLINICAL_WRITE)
    a = add_addendum(ctx, n, body.body)
    ctx.db.flush()
    ctx.audit("note.addendum_added", resource_type="note", resource_id=n.id, patient_id=n.patient_id,
              details={"addendum_id": str(a.id)})
    ctx.db.commit()
    ctx.db.expire(n)
    return note_out(ctx.db.get(ClinicalNote, n.id))


@router.get("/notes/{note_id}/versions", response_model=list[NoteVersionOut])
def note_versions(note_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    n, _ = _note(ctx, note_id)
    rows = ctx.db.scalars(select(ClinicalNoteVersion).where(ClinicalNoteVersion.note_id == n.id)
                          .order_by(ClinicalNoteVersion.version.desc())).all()
    return [NoteVersionOut(version=v.version, content=NoteContent(**v.content), source=v.source,
                           created_by=user_ref(v.created_by), created_at=v.created_at) for v in rows]


# ---------- Templates & codes ----------

@router.get("/templates", response_model=list[TemplateOut])
def list_templates(ctx: TenantContext = Depends(require(P.CLINICAL_READ))):
    return ctx.db.scalars(select(ClinicalTemplate).where(ClinicalTemplate.organization_id == ctx.org_id,
                                                         ClinicalTemplate.is_active.is_(True)).order_by(ClinicalTemplate.name)).all()


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(body: TemplateIn, ctx: TenantContext = Depends(require(P.CLINICAL_SIGN))):
    t = ClinicalTemplate(organization_id=ctx.org_id, name=body.name, specialty=body.specialty,
                         content=body.content.model_dump(), is_active=body.is_active)
    ctx.db.add(t)
    ctx.db.commit()
    return t


@router.get("/codes/icd10")
def search_icd10(q: str = Query(min_length=1), ctx: TenantContext = Depends(get_ctx)):
    ql = q.lower().strip()
    hits = [{"code": c, "description": d} for c, d in ICD10 if c.lower().startswith(ql) or ql in d.lower()]
    return hits[:20]


# ---------- Timeline & summary ----------

@router.get("/patients/{patient_id}/timeline")
def timeline(patient_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id, P.CLINICAL_READ)
    items: list[dict] = []
    for e in ctx.db.scalars(select(Encounter).where(Encounter.patient_id == p.id)).all():
        items.append({"type": "encounter", "id": str(e.id), "at": e.started_at, "title": e.encounter_type.replace("_", " ").title(),
                      "detail": e.chief_complaint, "status": e.status, "by": e.provider.user.display_name})
    for n in ctx.db.scalars(select(ClinicalNote).where(ClinicalNote.patient_id == p.id, ClinicalNote.status == "signed")).all():
        items.append({"type": "note", "id": str(n.id), "encounter_id": str(n.encounter_id), "at": n.signed_at,
                      "title": f"{n.title} signed", "detail": None, "status": "signed",
                      "by": n.signed_by.display_name if n.signed_by else None})
    for v in ctx.db.scalars(select(VitalSigns).where(VitalSigns.patient_id == p.id)).all():
        parts = []
        if v.systolic:
            parts.append(f"BP {v.systolic}/{v.diastolic}")
        if v.heart_rate:
            parts.append(f"HR {v.heart_rate}")
        if v.temperature_c:
            parts.append(f"T {v.temperature_c}°C")
        items.append({"type": "vitals", "id": str(v.id), "at": v.measured_at, "title": "Vitals recorded", "detail": " · ".join(parts)})
    for a in ctx.db.scalars(select(Appointment).where(Appointment.patient_id == p.id)).all():
        items.append({"type": "appointment", "id": str(a.id), "at": a.start_at,
                      "title": (a.appointment_type.name if a.appointment_type else "Appointment"),
                      "detail": a.reason, "status": a.status, "by": a.provider.user.display_name})
    for pr in ctx.db.scalars(select(Problem).where(Problem.patient_id == p.id, Problem.status != "entered_in_error")).all():
        items.append({"type": "problem", "id": str(pr.id), "at": pr.created_at, "title": f"Problem added: {pr.description}",
                      "detail": pr.code, "status": pr.status})
    for al in ctx.db.scalars(select(Allergy).where(Allergy.patient_id == p.id, Allergy.status != "entered_in_error")).all():
        items.append({"type": "allergy", "id": str(al.id), "at": al.created_at, "title": f"Allergy: {al.substance}",
                      "detail": al.reaction, "status": al.severity})
    items.sort(key=lambda i: i["at"] or datetime.min, reverse=True)
    return items[:300]


@router.get("/patients/{patient_id}/summary")
def chart_summary(patient_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    """Compact header data. Clinical sections are only included for users with clinical access."""
    p = get_patient(ctx, patient_id)
    clinical = ctx.can(P.CLINICAL_READ) or ctx.is_patient_only
    out: dict = {"clinical_access": clinical}
    upcoming = ctx.db.scalars(select(Appointment).where(Appointment.patient_id == p.id, Appointment.start_at >= now(),
                                                        Appointment.status.not_in(("cancelled", "no_show")))
                              .order_by(Appointment.start_at).limit(3)).all()
    out["upcoming_appointments"] = [{"id": a.id, "start_at": a.start_at, "provider": a.provider.user.display_name,
                                     "type": a.appointment_type.name if a.appointment_type else None, "status": a.status}
                                    for a in upcoming]
    if clinical:
        out["allergies"] = [AllergyOut.model_validate(a) for a in ctx.db.scalars(
            select(Allergy).where(Allergy.patient_id == p.id, Allergy.status == "active")).all()]
        out["problems"] = [ProblemOut.model_validate(x) for x in ctx.db.scalars(
            select(Problem).where(Problem.patient_id == p.id, Problem.status == "active")).all()]
        out["medications"] = [MedicationOut.model_validate(x) for x in ctx.db.scalars(
            select(PatientMedication).where(PatientMedication.patient_id == p.id, PatientMedication.status == "active")).all()]
        lv = ctx.db.scalar(select(VitalSigns).where(VitalSigns.patient_id == p.id).order_by(VitalSigns.measured_at.desc()))
        out["last_vitals"] = _vitals_out(lv) if lv else None
        last = ctx.db.scalar(select(Encounter).where(Encounter.patient_id == p.id).order_by(Encounter.started_at.desc()))
        out["last_encounter"] = encounter_out(ctx, last) if last else None
    return out
