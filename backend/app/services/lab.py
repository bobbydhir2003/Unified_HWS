"""Laboratory workflow: collect → receive (accession) → enter results (preliminary) → verify (different person) →
results to the clinician; critical values open a call-back alert that must be acknowledged; corrections keep history."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import now
from app.engine.events import emit
from app.models import CriticalResultAlert, LabResult, Order, Specimen
from app.services import audit
from app.services.notify import notify
from app.services.realtime import publish

CRITICAL_FLAGS = ("critical_high", "critical_low")
FLAGS = ("normal", "high", "low", "abnormal", *CRITICAL_FLAGS)


class LabError(ValueError):
    pass


def _pub(db, org_id, order_id):
    publish(db, org_id, "lab", order_id=order_id)


def collect(db: Session, order: Order, *, specimen_type: str, container: str | None, actor_id) -> Specimen:
    if order.order_type != "lab" or order.status not in ("signed", "transmitted"):
        raise LabError("Only signed lab orders awaiting collection can be collected")
    sp = Specimen(organization_id=order.organization_id, order_id=order.id, patient_id=order.patient_id, specimen_type=specimen_type,
                  container=container, collected_at=now(), collected_by_id=actor_id)
    nested = db.begin_nested()
    try:
        db.add(sp)
        db.flush()
        nested.commit()
    except IntegrityError:
        nested.rollback()
        raise LabError("A specimen is already in progress for this order") from None
    order.status = "in_progress"
    audit.record(db, "lab.collected", org_id=order.organization_id, actor_id=actor_id, resource_type="specimen", resource_id=sp.id, patient_id=order.patient_id)
    _pub(db, order.organization_id, order.id)
    return sp


def receive(db: Session, sp: Specimen, *, actor_id) -> None:
    if sp.status != "collected":
        raise LabError(f"Specimen is {sp.status}")
    sp.status, sp.received_at, sp.received_by_id = "received", now(), actor_id
    audit.record(db, "lab.received", org_id=sp.organization_id, actor_id=actor_id, resource_type="specimen", resource_id=sp.id, patient_id=sp.patient_id)
    _pub(db, sp.organization_id, sp.order_id)


def reject(db: Session, sp: Specimen, *, reason: str, actor_id) -> None:
    if sp.status not in ("collected", "received"):
        raise LabError("Only specimens not yet resulted can be rejected")
    sp.status, sp.rejected_reason = "rejected", reason
    sp.order.status = "signed"  # needs recollection
    from app.engine.cases import add_task

    add_task(db, None, org_id=sp.organization_id, title=f"Recollect {sp.order.title} — specimen rejected: {reason}", role="nurse",
             dedupe_key=f"lab:recollect:{sp.order_id}", priority="high", kind="lab.recollect", patient_id=sp.patient_id, link="/lab")
    audit.record(db, "lab.rejected", org_id=sp.organization_id, actor_id=actor_id, resource_type="specimen", resource_id=sp.id, patient_id=sp.patient_id,
                 details={"reason": reason})
    _pub(db, sp.organization_id, sp.order_id)


def enter_results(db: Session, sp: Specimen, rows: list[dict], *, actor_id) -> list[LabResult]:
    if sp.status not in ("received", "in_process"):
        raise LabError("Receive (accession) the specimen before entering results")
    if not rows:
        raise LabError("Enter at least one result")
    for r in db.scalars(select(LabResult).where(LabResult.specimen_id == sp.id, LabResult.status == "preliminary")):
        db.delete(r)  # unverified drafts may be re-entered
    out = []
    for r in rows:
        if r.get("flag", "normal") not in FLAGS:
            raise LabError(f"Unknown flag {r.get('flag')}")
        lr = LabResult(organization_id=sp.organization_id, order_id=sp.order_id, patient_id=sp.patient_id, name=r["name"], value=str(r["value"]),
                       unit=r.get("unit"), reference_range=r.get("reference_range"), flag=r.get("flag", "normal"), status="preliminary",
                       source="in_house", entered_by_id=actor_id, specimen_id=sp.id, resulted_at=now())
        db.add(lr)
        out.append(lr)
    sp.status = "in_process"
    db.flush()
    audit.record(db, "lab.results_entered", org_id=sp.organization_id, actor_id=actor_id, resource_type="specimen", resource_id=sp.id,
                 patient_id=sp.patient_id, details={"count": len(rows)})
    _pub(db, sp.organization_id, sp.order_id)
    return out


def _clinician(order: Order) -> uuid.UUID:
    return order.signed_by_id or order.ordered_by_id


def verify(db: Session, sp: Specimen, *, actor_id) -> list[CriticalResultAlert]:
    prelim = db.scalars(select(LabResult).where(LabResult.specimen_id == sp.id, LabResult.status == "preliminary")).all()
    if not prelim:
        raise LabError("Nothing to verify")
    if any(r.entered_by_id == actor_id for r in prelim):
        raise LabError("Results must be verified by a different person than the one who entered them")
    alerts = []
    for r in prelim:
        if r.supersedes_id:
            old = db.get(LabResult, r.supersedes_id)
            if old:
                old.status = "superseded"
        r.status, r.verified_by_id, r.verified_at = "final", actor_id, now()
        if r.flag in CRITICAL_FLAGS:
            a = CriticalResultAlert(organization_id=sp.organization_id, order_id=sp.order_id, result_id=r.id, patient_id=sp.patient_id,
                                    clinician_user_id=_clinician(sp.order), summary=f"{r.name} {r.value} {r.unit or ''}".strip()[:200], created_at=now())
            db.add(a)
            alerts.append(a)
    sp.status = "resulted"
    o = sp.order
    corrected = any(r.supersedes_id for r in prelim)
    o.status, o.resulted_at = "resulted", now()
    if corrected:
        o.results_reviewed_at = None  # clinician must re-review a corrected result before (re)release
    db.flush()
    abnormal = sum(1 for r in prelim if r.flag != "normal")
    notify(db, sp.organization_id, _clinician(o), "critical_result" if alerts else "result",
           f"{'CRITICAL ' if alerts else 'Corrected ' if corrected else ''}Result: {o.title} — {sp.patient.full_name}",
           f"{abnormal} abnormal value(s)", f"/patients/{sp.patient_id}/results")
    emit(db, sp.organization_id, "order.resulted", {"subject_type": "order", "subject_id": o.id, "patient_id": o.patient_id, "patient_name": sp.patient.full_name,
                                                    "title": o.title, "abnormal": abnormal > 0, "critical": bool(alerts),
                                                    "ordering_user_id": str(_clinician(o))}, actor_id=actor_id)
    if alerts:
        emit(db, sp.organization_id, "lab.critical_result", {"subject_type": "order", "subject_id": o.id, "patient_id": o.patient_id}, actor_id=actor_id)
    audit.record(db, "lab.verified", org_id=sp.organization_id, actor_id=actor_id, resource_type="specimen", resource_id=sp.id, patient_id=sp.patient_id,
                 details={"results": len(prelim), "critical": len(alerts), "corrected": corrected})
    _pub(db, sp.organization_id, sp.order_id)
    return alerts


def correct(db: Session, result: LabResult, *, value: str, flag: str, reason: str, actor_id) -> LabResult:
    if result.status != "final" or not result.specimen_id:
        raise LabError("Only verified in-house results can be corrected")
    if flag not in FLAGS:
        raise LabError("Unknown flag")
    sp = db.get(Specimen, result.specimen_id)
    new = LabResult(organization_id=result.organization_id, order_id=result.order_id, patient_id=result.patient_id, name=result.name, value=value,
                    unit=result.unit, reference_range=result.reference_range, flag=flag, status="preliminary", source="in_house", entered_by_id=actor_id,
                    specimen_id=result.specimen_id, supersedes_id=result.id, correction_reason=reason, resulted_at=now())
    db.add(new)
    sp.status = "in_process"
    db.flush()
    audit.record(db, "lab.correction_entered", org_id=result.organization_id, actor_id=actor_id, resource_type="lab_result", resource_id=result.id,
                 patient_id=result.patient_id, details={"reason": reason})
    _pub(db, result.organization_id, result.order_id)
    return new


def acknowledge(db: Session, alert: CriticalResultAlert, *, actor_id, read_back: str) -> None:
    if alert.acknowledged_at:
        raise LabError("Already acknowledged")
    alert.acknowledged_at, alert.acknowledged_by_id, alert.read_back = now(), actor_id, read_back
    audit.record(db, "lab.critical_acknowledged", org_id=alert.organization_id, actor_id=actor_id, resource_type="critical_alert", resource_id=alert.id,
                 patient_id=alert.patient_id)
    emit(db, alert.organization_id, "lab.critical_acknowledged", {"subject_type": "order", "subject_id": alert.order_id, "patient_id": alert.patient_id},
         actor_id=actor_id)
    _pub(db, alert.organization_id, alert.order_id)
