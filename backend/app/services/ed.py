"""Emergency department flow + patient identity reconciliation."""

import uuid
from datetime import date

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import now
from app.engine.events import emit, handler
from app.models import (
    DomainEvent,
    EdVisit,
    Encounter,
    InpatientStay,
    Location,
    Patient,
    TriageAssessment,
    VitalSigns,
)
from app.services import audit
from app.services.adt import AdtError, request_admission, set_bed_status
from app.services.realtime import publish


class EdError(ValueError):
    pass


def _pub(db: Session, v: EdVisit) -> None:
    publish(db, v.organization_id, "ed", visit_id=v.id, facility_id=v.facility_id)


def arrive(db: Session, *, org_id, facility_id, patient: Patient, complaint: str, mode: str, actor_id) -> EdVisit:
    v = EdVisit(organization_id=org_id, facility_id=facility_id, patient_id=patient.id, arrival_at=now(), arrival_mode=mode,
                chief_complaint=complaint, status="waiting")
    sp = db.begin_nested()
    try:
        db.add(v)
        db.flush()
        sp.commit()
    except IntegrityError:
        sp.rollback()
        raise EdError("This patient already has an active ED visit") from None
    audit.record(db, "ed.arrival", org_id=org_id, actor_id=actor_id, resource_type="ed_visit", resource_id=v.id, patient_id=patient.id,
                 details={"mode": mode, "temporary_identity": patient.is_temporary})
    emit(db, org_id, "ed.arrived", {"subject_type": "ed_visit", "subject_id": v.id, "patient_id": patient.id}, actor_id=actor_id,
         facility_id=facility_id)
    _pub(db, v)
    return v


def triage(db: Session, v: EdVisit, *, esi: int, actor_id, complaint: str | None, notes: str | None, vitals: dict | None) -> TriageAssessment:
    if v.status not in ("waiting", "triaged", "roomed"):
        raise EdError("Triage applies to patients still in the department")
    vit = None
    if vitals:
        vit = VitalSigns(organization_id=v.organization_id, patient_id=v.patient_id, encounter_id=v.encounter_id, recorded_by_id=actor_id,
                         measured_at=now(), **vitals)
        db.add(vit)
        db.flush()
    t = TriageAssessment(organization_id=v.organization_id, ed_visit_id=v.id, patient_id=v.patient_id, esi_level=esi, complaint=complaint,
                         notes=notes, vitals_id=vit.id if vit else None, recorded_by_id=actor_id, at=now())
    db.add(t)
    v.esi_level, v.triaged_at = esi, v.triaged_at or now()
    if complaint:
        v.chief_complaint = complaint
    if v.status == "waiting":
        v.status = "triaged"
    audit.record(db, "ed.triage", org_id=v.organization_id, actor_id=actor_id, resource_type="ed_visit", resource_id=v.id,
                 patient_id=v.patient_id, details={"esi": esi})
    _pub(db, v)
    return t


def room(db: Session, v: EdVisit, bay: Location, *, actor_id) -> None:
    if v.status not in ("waiting", "triaged", "roomed"):
        raise EdError("Patient is not waiting for a room")
    if bay.kind != "bed" or bay.facility_id != v.facility_id:
        raise EdError("Choose a bay in this department")
    if bay.bed_status not in ("available", "reserved"):
        raise EdError(f"Bay {bay.name} is {bay.bed_status}")
    old = db.get(Location, v.bed_id) if v.bed_id else None
    v.bed_id, v.roomed_at, v.status = bay.id, v.roomed_at or now(), "roomed"
    sp = db.begin_nested()
    try:
        db.flush()
        sp.commit()
    except IntegrityError:
        sp.rollback()
        raise EdError(f"Bay {bay.name} was just taken") from None
    try:
        set_bed_status(db, bay, "occupied", actor_id=actor_id, reason=f"ED visit {v.id}", system=True)
        if old and old.id != bay.id:
            set_bed_status(db, old, "cleaning", actor_id=actor_id, reason="ED patient moved", system=True)
    except AdtError as e:
        raise EdError(str(e)) from None
    _pub(db, v)


def assign_provider(db: Session, v: EdVisit, *, provider_id: uuid.UUID, actor_id) -> None:
    v.provider_id = provider_id
    if v.provider_seen_at is None:
        v.provider_seen_at = now()
    if v.encounter_id is None:
        e = Encounter(organization_id=v.organization_id, clinic_id=v.facility_id, patient_id=v.patient_id, provider_id=provider_id,
                      encounter_type="emergency", status="in_progress", chief_complaint=v.chief_complaint[:300], started_at=now())
        db.add(e)
        db.flush()
        v.encounter_id = e.id
    audit.record(db, "ed.provider_assigned", org_id=v.organization_id, actor_id=actor_id, resource_type="ed_visit", resource_id=v.id,
                 patient_id=v.patient_id)
    _pub(db, v)


def _release_bay(db: Session, v: EdVisit, actor_id) -> None:
    if v.bed_id:
        bay = db.get(Location, v.bed_id)
        if bay and bay.bed_status == "occupied":
            set_bed_status(db, bay, "cleaning", actor_id=actor_id, reason="ED patient departed", system=True)


def depart(db: Session, v: EdVisit, *, disposition: str, actor_id, note: str | None) -> None:
    if v.status == "departed":
        raise EdError("Visit already closed")
    v.disposition, v.disposition_at, v.disposition_note = disposition, v.disposition_at or now(), note
    v.status, v.departed_at = "departed", now()
    _release_bay(db, v, actor_id)
    if v.encounter_id:
        e = db.get(Encounter, v.encounter_id)
        if e and e.status == "in_progress":
            e.status, e.completed_at = "completed", now()
    audit.record(db, "ed.departed", org_id=v.organization_id, actor_id=actor_id, resource_type="ed_visit", resource_id=v.id,
                 patient_id=v.patient_id, details={"disposition": disposition})
    emit(db, v.organization_id, "ed.departed", {"subject_type": "ed_visit", "subject_id": v.id, "patient_id": v.patient_id,
                                                "disposition": disposition}, actor_id=actor_id, facility_id=v.facility_id)
    _pub(db, v)


def request_admit(db: Session, v: EdVisit, *, actor_id, attending_provider_id, reason: str, department_id, level_of_care: str) -> InpatientStay:
    if v.status not in ("triaged", "roomed"):
        raise EdError("Admit is a disposition for a triaged/roomed patient")
    if v.patient.is_temporary:
        pass  # allowed: admission proceeds under the temporary identity and is reconciled later
    try:
        s = request_admission(db, org_id=v.organization_id, facility_id=v.facility_id, patient_id=v.patient_id, department_id=department_id,
                              attending_provider_id=attending_provider_id or v.provider_id, reason=reason, source="ed",
                              level_of_care=level_of_care, actor_id=actor_id, ed_visit_id=v.id)
    except AdtError as e:
        raise EdError(str(e)) from None
    v.status, v.stay_id, v.disposition_at, v.disposition = "boarding", s.id, now(), None
    audit.record(db, "ed.admit_requested", org_id=v.organization_id, actor_id=actor_id, resource_type="ed_visit", resource_id=v.id,
                 patient_id=v.patient_id, details={"stay_id": str(s.id)})
    _pub(db, v)
    return s


@handler("ed_boarding_release", "adt.admitted", "adt.cancelled")
def on_admitted(db: Session, ev: DomainEvent) -> None:
    """When the inpatient bed is assigned, the ED visit ends (disposition admitted) and the bay goes to cleaning."""
    stay = db.get(InpatientStay, uuid.UUID(ev.subject_id)) if ev.subject_id else None
    if not stay or not stay.ed_visit_id:
        return
    v = db.get(EdVisit, stay.ed_visit_id)
    if not v or v.status != "boarding":
        return
    if ev.event_type == "adt.admitted":
        depart(db, v, disposition="admitted", actor_id=ev.actor_id, note=f"Admitted to inpatient stay {stay.id}")
    else:
        v.status, v.stay_id = "roomed" if v.bed_id else "triaged", None
        _pub(db, v)


# ---------------------------------------------------------------------------------------------------------------------
# Identity reconciliation (temporary ED identity → real chart)
# ---------------------------------------------------------------------------------------------------------------------

def make_temporary_patient(db: Session, ctx, *, sex: str, approx_age: int | None) -> Patient:
    from app.services.patients import next_mrn

    code = f"{now():%m%d}-{uuid.uuid4().hex[:4].upper()}"
    year = date.today().year - (approx_age or 40)
    p = Patient(organization_id=ctx.org_id, mrn=next_mrn(ctx), first_name="Unidentified", last_name=f"{'Male' if sex == 'male' else 'Female' if sex == 'female' else 'Patient'} {code}",
                date_of_birth=date(year, 1, 1), sex_at_birth=sex if sex in ("male", "female") else "unknown", is_temporary=True)
    db.add(p)
    db.flush()
    return p


def merge_patients(db: Session, *, source: Patient, target: Patient, actor_id, org_id) -> dict:
    """Re-point every patient-linked row from a temporary identity to the real chart in one transaction.
    Append-only tables/signed notes allow only a patient_id change while app.patient_merge is on (DB-enforced).
    The audit log is never rewritten; the merge itself is audited."""
    if not source.is_temporary:
        raise EdError("Only a temporary (ED quick-registration) identity can be merged")
    if source.id == target.id or target.is_temporary or target.status == "merged":
        raise EdError("Choose a different, permanent patient record")
    tables = [r[0] for r in db.execute(text(
        "SELECT c.table_name FROM information_schema.columns c JOIN information_schema.tables t ON t.table_name = c.table_name "
        "AND t.table_schema = c.table_schema WHERE c.table_schema = 'public' AND c.column_name = 'patient_id' AND t.table_type = 'BASE TABLE' "
        "AND c.table_name NOT IN ('audit_events')")).all()]
    moved: dict[str, int] = {}
    sp = db.begin_nested()
    try:
        db.execute(text("SELECT set_config('app.patient_merge', 'on', true)"))
        for t in sorted(tables):
            n = db.execute(text(f'UPDATE "{t}" SET patient_id = :dst WHERE patient_id = :src'), {"dst": target.id, "src": source.id}).rowcount
            if n:
                moved[t] = n
        db.execute(text("SELECT set_config('app.patient_merge', 'off', true)"))
        sp.commit()
    except IntegrityError as e:
        sp.rollback()
        msg = str(e.orig).split("\n")[0]
        raise EdError("Both records have an active visit or hospital stay; close one before merging" if "uq_" in msg else
                      f"Merge blocked by a data conflict: {msg[:150]}") from None
    source.status, source.merged_into_id, source.merged_at = "merged", target.id, now()
    db.flush()
    db.expire_all()  # in-memory relationships still point at the old ids
    audit.record(db, "patient.merged", org_id=org_id, actor_id=actor_id, resource_type="patient", resource_id=target.id, patient_id=target.id,
                 details={"from_patient": str(source.id), "moved": moved})
    audit.record(db, "patient.merged_away", org_id=org_id, actor_id=actor_id, resource_type="patient", resource_id=source.id,
                 patient_id=source.id, details={"into_patient": str(target.id)})
    return moved
