"""Closed-loop inpatient medication management.

    draft ─sign─▶ pending_verification ─pharmacist verify─▶ active ─▶ (dispense) ─▶ administer (eMAR) ─▶ completed
                         │   ▲                       │            │
                         │   └── resubmit ◀── clarification_needed │ hold ⇄ on_hold
                         └─ reject ─▶ rejected (terminal)          └─ discontinue ─▶ discontinued (terminal)

Rules enforced here (never only in the browser):
* An inpatient medication order is never "completed" by signing. It waits for an independent pharmacist decision; the
  pharmacist can't be the prescriber.
* Dispensing to a patient and documenting an administration both require an `active` (verified) order. Rejected,
  discontinued, held or unverified orders are blocked.
* "Given" requires a positive patient + dose-label scan (simulated barcode workflow, labelled as such), the ordered dose
  and route, and the correct scheduled slot. A slot can be documented once (DB UNIQUE); PRN doses respect a minimum
  interval; a dispensed label covers at most the dispensed quantity.
* High-alert medications need an independent witness (a second person) recorded separately.
* Interaction screening needs a licensed drug knowledge base. Without one, screening is reported as INCOMPLETE — never
  as "no interactions" — and the pharmacist must confirm a manual interaction review to verify.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import now
from app.models import (
    InpatientStay,
    MedicationAdministration,
    MedicationAdministrationWitness,
    MedicationVerification,
    Order,
    Organization,
    Patient,
    PatientMedication,
    StockMovement,
)

# Scheduled administration hours (organization local time). Demonstration defaults — configurable per organization later.
FREQUENCIES: dict[str, dict] = {
    "once": {"label": "Once", "hours": None},
    "daily": {"label": "Daily", "hours": [9]},
    "bid": {"label": "Twice daily", "hours": [9, 21]},
    "tid": {"label": "Three times daily", "hours": [8, 14, 22]},
    "qid": {"label": "Four times daily", "hours": [8, 12, 16, 20]},
    "q4h": {"label": "Every 4 hours", "hours": [0, 4, 8, 12, 16, 20]},
    "q6h": {"label": "Every 6 hours", "hours": [0, 6, 12, 18]},
    "q8h": {"label": "Every 8 hours", "hours": [6, 14, 22]},
    "q12h": {"label": "Every 12 hours", "hours": [9, 21]},
    "prn": {"label": "As needed", "hours": None},
}
HIGH_ALERT_CLASSES = {"anticoagulant", "insulin", "opioid"}
EARLY_MINUTES = 60   # a scheduled dose can't be given more than this early
LATE_MINUTES = 60    # later than this is documented as late (reason required)
ACTIVE_STAY = ("admitted", "discharge_ordered")


class MedicationError(Exception):
    """A rule violation the caller should show to the user (HTTP 409)."""

    def __init__(self, message: str, code: str = "medication_rule", status: int = 409):
        super().__init__(message)
        self.code = code
        self.status = status  # 400 = missing input (reason/note), 409 = rule blocks the action


# ---------------------------------------------------------------------------------------------- drug knowledge base

@dataclass
class Screening:
    status: str  # complete | unavailable
    source: str
    findings: list[dict] = field(default_factory=list)


class DrugKnowledgeBase(Protocol):
    """Licensed, clinically validated interaction / contraindication content (e.g. a commercial drug database)."""

    def screen(self, medication: dict, active_medications: list[str]) -> Screening: ...


class UnconfiguredKnowledgeBase:
    """No licensed knowledge base is connected. Screening is reported as incomplete; nothing is called 'safe'."""

    def screen(self, medication: dict, active_medications: list[str]) -> Screening:
        return Screening(status="unavailable", source="none")


def knowledge_base() -> DrugKnowledgeBase:
    return UnconfiguredKnowledgeBase()


def screening_warning(details: dict, active: list[str]) -> dict | None:
    s = knowledge_base().screen(details, active)
    if s.status == "complete":
        return None
    return {"type": "screening_incomplete", "severity": "info",
            "message": "Drug–drug interaction and contraindication screening is NOT available (no licensed drug knowledge base is "
                       "connected). Interactions were not checked; the pharmacist must review them manually."}


# ---------------------------------------------------------------------------------------------- helpers

def is_high_alert(details: dict) -> bool:
    return bool(details.get("high_alert")) or (details.get("drug_class") in HIGH_ALERT_CLASSES)


def active_stay(db: Session, org_id, patient_id) -> InpatientStay | None:
    return db.scalar(select(InpatientStay).where(InpatientStay.organization_id == org_id, InpatientStay.patient_id == patient_id,
                                                 InpatientStay.status.in_(ACTIVE_STAY)).order_by(InpatientStay.admitted_at.desc()))


def is_inpatient(o: Order) -> bool:
    return o.order_type == "medication" and (o.details or {}).get("setting") == "inpatient"


def ordered_dose(o: Order) -> str:
    d = o.details or {}
    return (d.get("dose") or d.get("strength") or "").strip()


def _norm(s: str | None) -> str:
    return " ".join((s or "").lower().replace("-", " ").split())


def latest_decision(db: Session, order_id) -> MedicationVerification | None:
    return db.scalar(select(MedicationVerification).where(MedicationVerification.order_id == order_id)
                     .order_by(MedicationVerification.at.desc()).limit(1))


def patient_barcode(p: Patient) -> str:
    return f"PT-{p.mrn}"


def dose_label_barcode(movement_id) -> str:
    return f"RXD-{movement_id}"


# ---------------------------------------------------------------------------------------------- lifecycle

def on_sign(db: Session, o: Order, *, actor_id, org_id) -> None:
    """Called by the sign endpoint after signature/attribution are set."""
    d = dict(o.details or {})
    if not d.get("setting"):
        d["setting"] = "inpatient" if active_stay(db, org_id, o.patient_id) else "outpatient"
    o.details = d
    if d["setting"] == "inpatient":
        if not d.get("frequency"):
            raise MedicationError("Inpatient medication orders need a frequency (schedule) before signing", "frequency_required")
        if not d.get("route"):
            raise MedicationError("Inpatient medication orders need a route before signing", "route_required")
        o.status = "pending_verification"
        o.transmission = {"channel": "pharmacy_verification_queue", "simulated": False}
    else:
        # Outpatient prescription: sent to an external pharmacy (simulated e-prescribing channel), added to the med list.
        o.status = "transmitted"
        db.add(PatientMedication(organization_id=org_id, patient_id=o.patient_id, name=d["name"], dose=d["strength"], route=d.get("route"),
                                 frequency=d["sig"][:100], source="prescribed", start_date=date.today(),
                                 indication=", ".join(o.indication_codes) or None, recorded_by_id=actor_id))


def decide(db: Session, o: Order, *, pharmacist_id, decision: str, note: str | None, manual_interaction_review: bool) -> MedicationVerification:
    if not is_inpatient(o):
        raise MedicationError("Only inpatient medication orders go through pharmacist verification")
    if o.status != "pending_verification":
        raise MedicationError(f"This order is {o.status.replace('_', ' ')}, not awaiting verification", "wrong_state")
    if pharmacist_id in (o.signed_by_id, o.ordered_by_id):
        raise MedicationError("A pharmacist can't verify an order they ordered or signed (independent double check)", "self_verification")
    if decision != "verified" and not (note and note.strip()):
        raise MedicationError("Explain the rejection or the clarification needed", "reason_required", 400)
    incomplete = any(w.get("type") == "screening_incomplete" for w in (o.safety_warnings or []))
    if decision == "verified" and incomplete and not manual_interaction_review:
        raise MedicationError("Interaction screening is unavailable for this order. Confirm that you reviewed interactions manually.",
                              "manual_review_required")
    v = MedicationVerification(organization_id=o.organization_id, order_id=o.id, patient_id=o.patient_id, status=decision, note=note,
                               pharmacist_id=pharmacist_id, at=now(), manual_interaction_review=bool(manual_interaction_review))
    db.add(v)
    o.status = {"verified": "active", "rejected": "rejected", "clarify": "clarification_needed"}[decision]
    if decision == "verified":
        d = o.details or {}
        db.add(PatientMedication(organization_id=o.organization_id, patient_id=o.patient_id, name=(d.get("name") or o.title)[:200], dose=ordered_dose(o),
                                 route=d.get("route"), frequency=(FREQUENCIES.get(d.get("frequency") or "", {}).get("label") or d.get("sig") or "")[:100],
                                 source="prescribed", start_date=date.today(), indication=", ".join(o.indication_codes) or None,
                                 recorded_by_id=pharmacist_id))
    return v


def resubmit(o: Order, note: str) -> None:
    if o.status != "clarification_needed":
        raise MedicationError("Only orders sent back for clarification can be resubmitted", "wrong_state")
    o.status = "pending_verification"
    o.notes = ((o.notes or "") + f"\nClarification: {note.strip()}").strip()[:2000]


def set_hold(o: Order, hold: bool, reason: str | None) -> None:
    if hold:
        if o.status != "active":
            raise MedicationError("Only active orders can be held", "wrong_state")
        if not reason:
            raise MedicationError("Give a reason for holding the order", "reason_required", 400)
        o.status, o.cancelled_reason = "on_hold", reason
    else:
        if o.status != "on_hold":
            raise MedicationError("The order is not on hold", "wrong_state")
        o.status = "active"


def discontinue(db: Session, o: Order, *, actor_id, reason: str) -> None:
    if o.status not in ("active", "on_hold", "pending_verification", "clarification_needed"):
        raise MedicationError(f"An order that is {o.status.replace('_', ' ')} can't be discontinued", "wrong_state")
    if not reason or len(reason.strip()) < 3:
        raise MedicationError("Give a reason for discontinuing", "reason_required", 400)
    o.status, o.cancelled_reason, o.discontinued_at, o.discontinued_by_id = "discontinued", reason.strip(), now(), actor_id
    name = (o.details or {}).get("name")
    for m in db.scalars(select(PatientMedication).where(PatientMedication.patient_id == o.patient_id, PatientMedication.name == name,
                                                        PatientMedication.status == "active", PatientMedication.source == "prescribed")):
        m.status = "discontinued"
        m.end_date = date.today()


def assert_dispensable(o: Order | None, patient_id) -> None:
    """Patient-specific medication dispensing requires a verified order for that same patient."""
    if o is None:
        raise MedicationError("Dispensing a medication to a patient requires the verified medication order", "order_required")
    if o.order_type != "medication":
        raise MedicationError("That order is not a medication order")
    if patient_id and o.patient_id != patient_id:
        raise MedicationError("The order belongs to a different patient", "patient_mismatch")
    if is_inpatient(o) and o.status != "active":
        raise MedicationError(f"Can't dispense: the order is {o.status.replace('_', ' ')} (pharmacist verification is required first)",
                              "not_verified")
    if not is_inpatient(o) and o.status not in ("transmitted", "signed"):
        raise MedicationError(f"Can't dispense: the prescription is {o.status.replace('_', ' ')}", "not_dispensable")


# ---------------------------------------------------------------------------------------------- schedule

def _tz(db: Session, org_id) -> ZoneInfo:
    try:
        return ZoneInfo(db.get(Organization, org_id).timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def start_time(o: Order) -> datetime:
    """Doses start from the pharmacist's verification (an unverified order has no administrable slots)."""
    return o.signed_at or o.created_at


def slots(db: Session, o: Order, start: datetime, end: datetime, verified_at: datetime | None) -> list[datetime]:
    d = o.details or {}
    freq = d.get("frequency")
    if freq == "prn" or not verified_at:
        return []
    first = verified_at - timedelta(minutes=EARLY_MINUTES)  # the first dose may be scheduled right at verification
    if freq == "once":
        t = verified_at.replace(second=0, microsecond=0)
        return [t] if start <= t <= end else []
    hours = FREQUENCIES.get(freq, {}).get("hours") or []
    tz = _tz(db, o.organization_id)
    out: list[datetime] = []
    day = start.astimezone(tz).date() - timedelta(days=1)
    last = end.astimezone(tz).date() + timedelta(days=1)
    while day <= last:
        for h in hours:
            t = datetime(day.year, day.month, day.day, h, tzinfo=tz)
            if start <= t <= end and t >= first and (not o.discontinued_at or t < o.discontinued_at):
                out.append(t)
        day += timedelta(days=1)
    return sorted(out)


# ---------------------------------------------------------------------------------------------- administration

@dataclass
class AdministrationInput:
    order_id: uuid.UUID
    status: str
    scheduled_for: datetime | None = None
    dose: str | None = None
    route: str | None = None
    site: str | None = None
    reason: str | None = None
    patient_barcode: str | None = None
    medication_barcode: str | None = None


def _verified_at(db: Session, o: Order) -> datetime | None:
    v = latest_decision(db, o.id)
    return v.at if v and v.status == "verified" else None


def administer(db: Session, o: Order, a: AdministrationInput, *, actor_id) -> MedicationAdministration:
    if not is_inpatient(o):
        raise MedicationError("Only inpatient medication orders are documented on the MAR")
    if o.status in ("pending_verification", "clarification_needed"):
        raise MedicationError("Blocked: this order has not been verified by a pharmacist", "not_verified")
    if o.status in ("rejected", "discontinued", "cancelled", "completed"):
        raise MedicationError(f"Blocked: the order is {o.status}", "order_closed")
    if o.status == "on_hold" and a.status == "given":
        raise MedicationError(f"Blocked: the order is on hold ({o.cancelled_reason or 'no reason given'})", "on_hold")
    if a.status not in ("given", "held", "refused", "omitted"):
        raise MedicationError("Unknown administration status")
    if a.status != "given" and not (a.reason and a.reason.strip()):
        raise MedicationError("A reason is required when a dose is held, refused or omitted", "reason_required", 400)

    ts = now()
    d = o.details or {}
    prn = d.get("frequency") == "prn"
    verified_at = _verified_at(db, o)
    late = False
    if prn:
        if a.scheduled_for is not None:
            raise MedicationError("PRN doses are not scheduled")
        interval = float(d.get("prn_interval_hours") or 4)
        last_given = db.scalar(select(func.max(MedicationAdministration.administered_at))
                               .where(MedicationAdministration.order_id == o.id, MedicationAdministration.status == "given"))
        if a.status == "given" and last_given and ts - last_given < timedelta(hours=interval):
            nxt = last_given + timedelta(hours=interval)
            raise MedicationError(f"Blocked: last PRN dose was given at {last_given:%H:%M}; the minimum interval is {interval:g} h "
                                  f"(next allowed at {nxt:%H:%M} UTC)", "prn_interval")
    else:
        if a.scheduled_for is None:
            raise MedicationError("Choose the scheduled dose this documentation is for")
        window = slots(db, o, a.scheduled_for - timedelta(minutes=1), a.scheduled_for + timedelta(minutes=1), verified_at)
        if not window:
            raise MedicationError("That time is not a scheduled dose for this order", "not_a_slot")
        sched = window[0]
        if a.status == "given" and ts < sched - timedelta(minutes=EARLY_MINUTES):
            raise MedicationError(f"Blocked: this dose is due at {sched:%H:%M} UTC and can't be given more than {EARLY_MINUTES} minutes early",
                                  "too_early")
        late = ts > sched + timedelta(minutes=LATE_MINUTES)
        if late and a.status == "given" and not (a.reason and a.reason.strip()):
            raise MedicationError("This dose is late — document the reason for the delay", "late_reason_required")
        if db.scalar(select(MedicationAdministration.id).where(MedicationAdministration.order_id == o.id,
                                                               MedicationAdministration.scheduled_for == sched)):
            raise MedicationError("This scheduled dose has already been documented", "duplicate")
        a.scheduled_for = sched

    scan: dict = {"simulated": True}
    movement_id = None
    if a.status == "given":
        patient = db.get(Patient, o.patient_id)
        if not a.patient_barcode:
            raise MedicationError("Scan the patient's wristband", "scan_patient")
        if a.patient_barcode.strip() != patient_barcode(patient):
            raise MedicationError("Wrong patient: the wristband scanned does not match this patient. Do not administer.", "patient_mismatch")
        scan["patient"] = "match"
        if not a.medication_barcode:
            raise MedicationError("Scan the medication's dispensing label", "scan_medication")
        code = a.medication_barcode.strip()
        if not code.startswith("RXD-"):
            raise MedicationError("Unrecognized medication barcode. Scan the pharmacy dispensing label.", "medication_unknown")
        try:
            mid = uuid.UUID(code[4:])
        except ValueError:
            raise MedicationError("Unrecognized medication barcode", "medication_unknown") from None
        mv = db.get(StockMovement, mid)
        if not mv or mv.organization_id != o.organization_id or mv.kind != "dispense":
            raise MedicationError("This label was not issued by the pharmacy", "medication_unknown")
        if mv.patient_id and mv.patient_id != o.patient_id:
            raise MedicationError("Wrong patient: this dose was dispensed for a different patient. Do not administer.", "patient_mismatch")
        if mv.reference_type != "order" or mv.reference_id != str(o.id):
            raise MedicationError("Wrong medication: this dose was dispensed for a different order. Do not administer.", "medication_mismatch")
        used = db.scalar(select(func.count()).select_from(MedicationAdministration).where(
            MedicationAdministration.dispense_movement_id == mv.id, MedicationAdministration.status == "given"))
        if used >= mv.quantity:
            raise MedicationError("Every dose on this label has already been documented as given", "label_used")
        scan["medication"] = "match"
        movement_id = mv.id
        if _norm(a.dose) != _norm(ordered_dose(o)):
            raise MedicationError(f"Wrong dose: the order is for {ordered_dose(o)}, not {a.dose or 'unspecified'}", "dose_mismatch")
        if _norm(a.route) != _norm(d.get("route")):
            raise MedicationError(f"Wrong route: the order is {d.get('route')}, not {a.route or 'unspecified'}", "route_mismatch")
        scan["dose"] = scan["route"] = "match"

    stay = active_stay(db, o.organization_id, o.patient_id)
    m = MedicationAdministration(organization_id=o.organization_id, order_id=o.id, patient_id=o.patient_id, stay_id=stay.id if stay else None,
                                 scheduled_for=a.scheduled_for, status=a.status, dose=a.dose if a.status == "given" else None,
                                 route=a.route if a.status == "given" else None, site=a.site, reason=(a.reason or None), late=late,
                                 administered_at=ts, administered_by_id=actor_id, dispense_movement_id=movement_id, scan=scan,
                                 requires_witness=a.status == "given" and is_high_alert(d))
    db.add(m)
    if d.get("frequency") == "once" and a.status == "given":
        o.status = "completed"
    return m


def witness(db: Session, m: MedicationAdministration, *, witness_id, note: str | None) -> MedicationAdministrationWitness:
    if not m.requires_witness:
        raise MedicationError("This administration doesn't need a witness")
    if witness_id == m.administered_by_id:
        raise MedicationError("The witness must be a different person from the nurse who gave the dose", "self_witness")
    if db.scalar(select(MedicationAdministrationWitness.id).where(MedicationAdministrationWitness.administration_id == m.id)):
        raise MedicationError("Already witnessed", "duplicate")
    w = MedicationAdministrationWitness(organization_id=m.organization_id, administration_id=m.id, witness_id=witness_id, note=note, at=now())
    db.add(w)
    return w
