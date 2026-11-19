"""Insurance Guardian services: eligibility checks, coverage state for a date of service, coverage updates.

Coverage state for a visit (never inferred from the stored end date):
  verified_active   — the payer reported active coverage for this date of service recently enough
  verified_inactive — the latest payer response for the coverage on file is inactive
  stale             — the last active response is too old / for a different date to rely on
  error             — the payer could not be reached; nothing is known
  unverified        — never checked
  no_coverage       — no active insurance on file
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import now
from app.integrations.adapters import eligibility_gateway
from app.models import EligibilityCheck, PatientInsurance
from app.services import audit
from app.services.realtime import publish

FRESH_DAYS = 7  # an active response obtained within this many days before the visit (or for that exact date) verifies it
PRIORITY = {"primary": 0, "secondary": 1, "tertiary": 2}


@dataclass
class CoverageState:
    state: str
    insurance: PatientInsurance | None
    check: EligibilityCheck | None
    reason: str

    @property
    def verified(self) -> bool:
        return self.state == "verified_active"


def primary_insurance(db: Session, patient_id: uuid.UUID) -> PatientInsurance | None:
    rows = db.scalars(select(PatientInsurance).where(PatientInsurance.patient_id == patient_id, PatientInsurance.is_active.is_(True))).all()
    return min(rows, key=lambda i: (PRIORITY.get(i.priority, 9), -(i.created_at.timestamp() if i.created_at else 0)), default=None)


def latest_check(db: Session, insurance_id: uuid.UUID) -> EligibilityCheck | None:
    return db.scalar(select(EligibilityCheck).where(EligibilityCheck.insurance_id == insurance_id)
                     .order_by(EligibilityCheck.checked_at.desc()).limit(1))


def check_verifies(chk: EligibilityCheck, dos: date, fresh_days: int = FRESH_DAYS) -> bool:
    if chk.result != "active":
        return False
    if chk.coverage_end and chk.coverage_end < dos:
        return False
    if chk.coverage_start and chk.coverage_start > dos:
        return False
    checked = chk.checked_at.date()
    same_dos = chk.date_of_service == dos and checked >= (now() - timedelta(days=30)).date()
    recent = checked >= dos - timedelta(days=fresh_days)
    return same_dos or recent


def coverage_state(db: Session, patient_id: uuid.UUID, dos: date, fresh_days: int = FRESH_DAYS) -> CoverageState:
    ins = primary_insurance(db, patient_id)
    if ins is None:
        return CoverageState("no_coverage", None, None, "No active insurance on file")
    checks = db.scalars(select(EligibilityCheck).where(EligibilityCheck.insurance_id == ins.id)
                        .order_by(EligibilityCheck.checked_at.desc()).limit(10)).all()
    if not checks:
        return CoverageState("unverified", ins, None, "Eligibility has never been checked with the payer")
    latest = checks[0]
    ok = next((c for c in checks if check_verifies(c, dos, fresh_days)), None)
    if latest.result == "inactive":
        return CoverageState("verified_inactive", ins, latest, latest.message or "Payer reported coverage inactive")
    if ok:
        return CoverageState("verified_active", ins, ok, f"Payer reported active coverage for {dos:%b %d} ({ok.source})")
    if latest.result == "error":
        return CoverageState("error", ins, latest, latest.message or "Payer could not be reached")
    if latest.result == "active" and latest.coverage_end and latest.coverage_end < dos:
        return CoverageState("stale", ins, latest, f"Payer-reported plan end {latest.coverage_end:%b %d} is before the visit")
    return CoverageState("stale", ins, latest, "Last verification is too old for this visit")


def run_check(db: Session, ins: PatientInsurance, *, dos: date, trigger: str, actor_id: uuid.UUID | None,
              appointment_id: uuid.UUID | None = None, emit_event: bool = True) -> EligibilityCheck:
    gw = eligibility_gateway()
    r = gw.inquire(payer_name=ins.payer_name, member_id=ins.member_id, date_of_service=dos, subscriber_name=ins.subscriber_name)
    chk = EligibilityCheck(organization_id=ins.organization_id, insurance_id=ins.id, patient_id=ins.patient_id,
                           appointment_id=appointment_id, date_of_service=dos, result=r["result"], coverage_start=r.get("coverage_start"),
                           coverage_end=r.get("coverage_end"), plan_description=r.get("plan"), copay_cents=r.get("copay_cents"),
                           source="simulated" if gw.name == "simulated" else "clearinghouse", trigger=trigger, payer_trace=r.get("trace"),
                           message=r.get("message"), response={k: str(v) for k, v in r.items()}, checked_by_id=actor_id, checked_at=now())
    db.add(chk)
    if r["result"] != "error":
        ins.eligibility_status = r["result"]
    ins.eligibility_checked_at = chk.checked_at
    db.flush()
    audit.record(db, "insurance.eligibility_checked", org_id=ins.organization_id, actor_id=actor_id, resource_type="insurance",
                 resource_id=ins.id, patient_id=ins.patient_id,
                 details={"result": r["result"], "source": chk.source, "trigger": trigger, "dos": dos.isoformat()})
    if emit_event:
        from app.engine.events import emit

        emit(db, ins.organization_id, "insurance.eligibility_checked",
             {"subject_type": "insurance", "subject_id": ins.id, "patient_id": ins.patient_id, "result": r["result"]}, actor_id=actor_id)
    publish(db, ins.organization_id, "insurance", patient_id=ins.patient_id)
    return chk


def hours_until(dt: datetime) -> float:
    return (dt - now()).total_seconds() / 3600


CARD_FIELDS = ("payer_name", "plan_name", "member_id", "group_number", "subscriber_name", "effective_date")


def discrepancies(submitted: dict, extracted: dict) -> list[str]:
    """Fields where what the patient typed differs from what was read from the card (case/space-insensitive)."""
    out = []
    norm = lambda v: "".join(str(v or "").lower().split())  # noqa: E731
    for f in CARD_FIELDS:
        a, b = submitted.get(f), extracted.get(f)
        if a and b and norm(a) != norm(b):
            out.append(f)
    return out
