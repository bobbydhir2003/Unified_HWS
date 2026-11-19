"""ADT + bed management service. Every state change validates the transition, writes history (adt_events,
bed_status_events), audits, emits a domain event, and publishes a live update. Occupancy invariants are also
enforced by the database (see app/models/inpatient.py)."""

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import now
from app.engine.events import emit
from app.models import AdtEvent, BedAssignment, BedStatusEvent, Department, InpatientStay, Location, Task
from app.services import audit
from app.services.realtime import publish

BED_TRANSITIONS = {
    "available": {"reserved", "occupied", "blocked", "cleaning"},
    "reserved": {"available", "occupied", "blocked"},
    "occupied": {"cleaning"},
    "cleaning": {"available", "blocked"},
    "blocked": {"available", "cleaning"},
}


class AdtError(ValueError):
    pass


def set_bed_status(db: Session, bed: Location, to: str, *, actor_id: uuid.UUID | None, reason: str | None = None,
                   system: bool = False) -> None:
    frm = bed.bed_status
    if bed.kind != "bed":
        raise AdtError("Not a bed")
    if frm == to:
        return
    if to not in BED_TRANSITIONS.get(frm or "", set()):
        raise AdtError(f"A bed can't go from {frm} to {to}")
    if not system and to == "occupied":
        raise AdtError("Beds become occupied only by admitting or transferring a patient")
    if not system and frm == "occupied":
        raise AdtError("An occupied bed is released by transferring or discharging the patient")
    if to == "blocked" and not (reason and reason.strip()):
        raise AdtError("Give a reason for blocking the bed")
    bed.bed_status, bed.bed_status_reason, bed.bed_status_changed_at = to, reason, now()
    db.add(BedStatusEvent(organization_id=bed.organization_id, bed_id=bed.id, from_status=frm, to_status=to, reason=reason,
                          actor_id=actor_id, at=now()))
    if to == "cleaning":
        _housekeeping_task(db, bed)
    if frm == "cleaning" and to == "available":
        for t in db.scalars(select(Task).where(Task.dedupe_key == f"evs:clean:{bed.id}", Task.status.in_(("open", "in_progress")))):
            t.status, t.completed_at, t.completed_by_id = "done", now(), actor_id
    emit(db, bed.organization_id, "bed.status_changed", {"subject_type": "bed", "subject_id": bed.id, "from": frm, "to": to},
         actor_id=actor_id, facility_id=bed.facility_id)
    publish(db, bed.organization_id, "beds", bed_id=bed.id, facility_id=bed.facility_id)


def _housekeeping_task(db: Session, bed: Location) -> None:
    from app.engine.cases import add_task

    evs = db.scalar(select(Department.id).where(Department.facility_id == bed.facility_id, Department.code == "EVS"))
    add_task(db, None, org_id=bed.organization_id, title=f"Clean and turn over bed {bed.code}", role="bed_manager",
             dedupe_key=f"evs:clean:{bed.id}", priority="high", kind="evs.clean_bed", link="/beds", due_minutes=45,
             department_id=evs)


def _event(db: Session, stay: InpatientStay, kind: str, actor_id, *, frm=None, to=None, note=None) -> None:
    db.add(AdtEvent(organization_id=stay.organization_id, stay_id=stay.id, patient_id=stay.patient_id, kind=kind, from_bed_id=frm,
                    to_bed_id=to, actor_id=actor_id, note=note, at=now()))
    audit.record(db, f"adt.{kind}", org_id=stay.organization_id, actor_id=actor_id, resource_type="inpatient_stay",
                 resource_id=stay.id, patient_id=stay.patient_id, details={"from_bed": str(frm) if frm else None, "to_bed": str(to) if to else None})
    emit(db, stay.organization_id, f"adt.{kind}", {"subject_type": "inpatient_stay", "subject_id": stay.id, "patient_id": stay.patient_id,
                                                   "from_bed": str(frm) if frm else None, "to_bed": str(to) if to else None},
         actor_id=actor_id, facility_id=stay.facility_id)
    publish(db, stay.organization_id, "adt", stay_id=stay.id, facility_id=stay.facility_id)


def current_assignment(db: Session, stay_id: uuid.UUID) -> BedAssignment | None:
    return db.scalar(select(BedAssignment).where(BedAssignment.stay_id == stay_id, BedAssignment.end_at.is_(None)))


def request_admission(db: Session, *, org_id, facility_id, patient_id, department_id, attending_provider_id, reason, source="direct",
                      level_of_care="med_surg", expected_discharge_date: date | None = None, isolation: str | None = None,
                      actor_id=None, ed_visit_id=None) -> InpatientStay:
    stay = InpatientStay(organization_id=org_id, facility_id=facility_id, patient_id=patient_id, requested_department_id=department_id,
                         attending_provider_id=attending_provider_id, reason=reason, admit_source=source, level_of_care=level_of_care,
                         expected_discharge_date=expected_discharge_date, isolation=isolation, requested_by_id=actor_id,
                         requested_at=now(), ed_visit_id=ed_visit_id, status="pending")
    sp = db.begin_nested()
    try:
        db.add(stay)
        db.flush()
        sp.commit()
    except IntegrityError:
        sp.rollback()
        raise AdtError("This patient already has an active hospital stay") from None
    _event(db, stay, "admission_requested", actor_id, note=reason)
    return stay


def _check_bed(db: Session, stay: InpatientStay, bed: Location) -> None:
    if bed.kind != "bed" or bed.facility_id != stay.facility_id or not bed.is_active:
        raise AdtError("Choose an active bed in the same facility")
    if bed.bed_status not in ("available", "reserved"):
        raise AdtError(f"Bed {bed.code} is {bed.bed_status}")


def _occupy(db: Session, stay: InpatientStay, bed: Location, actor_id, reason: str) -> None:
    sp = db.begin_nested()
    try:
        db.add(BedAssignment(organization_id=stay.organization_id, stay_id=stay.id, bed_id=bed.id, patient_id=stay.patient_id,
                             start_at=now(), reason=reason, assigned_by_id=actor_id))
        db.flush()
        sp.commit()
    except IntegrityError:
        sp.rollback()
        raise AdtError(f"Bed {bed.code} was just taken by another patient") from None
    set_bed_status(db, bed, "occupied", actor_id=actor_id, reason=f"{reason}: stay {stay.id}", system=True)
    stay.department_id = bed.department_id


def ensure_encounter(db: Session, stay: InpatientStay) -> None:
    """Inpatient documentation (progress, nursing, discharge summary notes) lives on one inpatient encounter."""
    if stay.encounter_id:
        return
    if not stay.attending_provider_id:
        raise AdtError("Assign an attending physician before admitting")
    from app.models import Encounter

    e = Encounter(organization_id=stay.organization_id, clinic_id=stay.facility_id, patient_id=stay.patient_id,
                  provider_id=stay.attending_provider_id, encounter_type="inpatient", status="in_progress", chief_complaint=stay.reason[:300],
                  started_at=stay.admitted_at or now())
    db.add(e)
    db.flush()
    stay.encounter_id = e.id


def admit(db: Session, stay: InpatientStay, bed: Location, *, actor_id) -> None:
    if stay.status != "pending":
        raise AdtError(f"Stay is {stay.status}; only pending admissions can be assigned a first bed")
    _check_bed(db, stay, bed)
    if not stay.attending_provider_id:
        raise AdtError("Assign an attending physician before admitting")
    _occupy(db, stay, bed, actor_id, "admit")
    stay.status, stay.admitted_at = "admitted", now()
    ensure_encounter(db, stay)
    _event(db, stay, "admitted", actor_id, to=bed.id)


def transfer(db: Session, stay: InpatientStay, bed: Location, *, actor_id, note: str | None = None) -> None:
    if stay.status not in ("admitted", "discharge_ordered"):
        raise AdtError("Only admitted patients can be transferred")
    _check_bed(db, stay, bed)
    cur = current_assignment(db, stay.id)
    if cur and cur.bed_id == bed.id:
        raise AdtError("Patient is already in that bed")
    if cur:
        cur.end_at = now()
        db.flush()
        set_bed_status(db, db.get(Location, cur.bed_id), "cleaning", actor_id=actor_id, reason="patient transferred out", system=True)
    _occupy(db, stay, bed, actor_id, "transfer")
    _event(db, stay, "transferred", actor_id, frm=cur.bed_id if cur else None, to=bed.id, note=note)


def order_discharge(db: Session, stay: InpatientStay, *, actor_id, disposition: str, expected_at: datetime | None = None,
                    note: str | None = None) -> None:
    if stay.status != "admitted":
        raise AdtError("Discharge can be ordered only for admitted patients")
    stay.status, stay.discharge_ordered_at, stay.discharge_ordered_by_id, stay.discharge_disposition = "discharge_ordered", now(), actor_id, disposition
    if expected_at:
        stay.data = {**(stay.data or {}), "expected_departure": expected_at.isoformat()}
    _event(db, stay, "discharge_ordered", actor_id, note=note or disposition)


def cancel_discharge_order(db: Session, stay: InpatientStay, *, actor_id, reason: str) -> None:
    if stay.status != "discharge_ordered":
        raise AdtError("No discharge order to cancel")
    stay.status, stay.discharge_ordered_at, stay.discharge_ordered_by_id = "admitted", None, None
    _event(db, stay, "discharge_order_cancelled", actor_id, note=reason)


def discharge(db: Session, stay: InpatientStay, *, actor_id, note: str | None = None) -> None:
    if stay.status != "discharge_ordered":
        raise AdtError("A discharge order is required before the patient leaves")
    cur = current_assignment(db, stay.id)
    if cur:
        cur.end_at = now()
        db.flush()
        set_bed_status(db, db.get(Location, cur.bed_id), "cleaning", actor_id=actor_id, reason="patient discharged", system=True)
    stay.status, stay.discharged_at = "discharged", now()
    if stay.encounter_id:
        from app.models import Encounter

        e = db.get(Encounter, stay.encounter_id)
        if e and e.status == "in_progress":
            e.status, e.completed_at = "completed", now()
    _event(db, stay, "discharged", actor_id, frm=cur.bed_id if cur else None, note=note)


def cancel(db: Session, stay: InpatientStay, *, actor_id, reason: str) -> None:
    if stay.status != "pending":
        raise AdtError("Only pending admissions can be cancelled")
    stay.status, stay.cancel_reason = "cancelled", reason
    _event(db, stay, "cancelled", actor_id, note=reason)
