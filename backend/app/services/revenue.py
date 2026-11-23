"""Revenue cycle expansion (B10).

- Prior authorization: which services need it (org setting `prior_auth_codes`, default advanced imaging), a document
  checklist, submission to a SIMULATED payer (X12 278 not connected), validity window, expiry.
- Claim review: deterministic rules + an optional AI consistency check (OpenAI when configured). Findings are advisory;
  they never modify a claim. Blocker findings stop submission until resolved by a person.
- Facility charges: room & board per inpatient day posted to the inpatient encounter at discharge.
"""

import hashlib
import math
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import now
from app.engine.events import handler
from app.models import (
    Charge,
    Claim,
    ClaimFinding,
    ClinicalNote,
    DomainEvent,
    FeeScheduleItem,
    InpatientStay,
    Order,
    Organization,
    PatientInsurance,
    PriorAuthorization,
)
from app.services import audit
from app.services.insurance import primary_insurance

DEFAULT_PA_CODES = {"74177": "CT abdomen/pelvis with contrast", "70450": "CT head without contrast", "72148": "MRI lumbar spine without contrast"}
CHECKLIST = [("order", "Signed order with clinical question"), ("notes", "Supporting clinical notes"), ("insurance", "Current insurance card on file"),
             ("prior_treatment", "Prior conservative treatment documented (if required by payer)")]
FACILITY_CODES = {"icu": ("RB-ICU", "Room & board — intensive care (per day)", 420000), "default": ("RB-MS", "Room & board — med/surg (per day)", 185000)}


class RevenueError(ValueError):
    pass


def pa_codes(db: Session, org_id) -> dict:
    org = db.get(Organization, org_id)
    return (org.settings or {}).get("prior_auth_codes") or DEFAULT_PA_CODES


def approved_auth(db: Session, patient_id, code: str, on: date) -> PriorAuthorization | None:
    return db.scalar(select(PriorAuthorization).where(PriorAuthorization.patient_id == patient_id, PriorAuthorization.service_code == code,
                                                      PriorAuthorization.status == "approved", PriorAuthorization.valid_from <= on,
                                                      PriorAuthorization.valid_to >= on).limit(1))


def ensure_pa_for_order(db: Session, order: Order, *, source="monitor", actor_id=None) -> PriorAuthorization:
    pa = db.scalar(select(PriorAuthorization).where(PriorAuthorization.order_id == order.id,
                                                    PriorAuthorization.status.not_in(("denied", "expired", "cancelled"))))
    if pa:
        return pa
    ins = primary_insurance(db, order.patient_id)
    pa = PriorAuthorization(organization_id=order.organization_id, patient_id=order.patient_id, insurance_id=ins.id if ins else None, order_id=order.id,
                            service_code=order.code or "", service_description=order.title, payer_name=ins.payer_name if ins else None,
                            checklist=[{"key": k, "label": label, "done": k == "order", "note": None} for k, label in CHECKLIST],
                            clinical_summary=(order.details or {}).get("clinical_question"), source=source, created_by_id=actor_id)
    db.add(pa)
    db.flush()
    return pa


def simulated_payer_decision(pa: PriorAuthorization, member_id: str | None) -> dict:
    """Deterministic SIMULATED 278 response: member IDs ending 7 → denied; ending 5 → pended (more info); otherwise approved 60 days."""
    last = (member_id or "")[-1:]
    if last == "7":
        return {"status": "denied", "reason": "Medical necessity not established (simulated payer)"}
    if last == "5":
        return {"status": "pended", "reason": "Additional clinical documentation requested (simulated payer)"}
    ref = "SIM-PA-" + hashlib.sha256(str(pa.id).encode()).hexdigest()[:8].upper()
    return {"status": "approved", "auth_number": ref, "valid_from": date.today(), "valid_to": date.today() + timedelta(days=60), "units": 1}


def submit_pa(db: Session, pa: PriorAuthorization, *, actor_id) -> PriorAuthorization:
    if pa.status not in ("draft", "pended"):
        raise RevenueError(f"Authorization is {pa.status}")
    missing = [c["label"] for c in pa.checklist if not c.get("done") and c["key"] != "prior_treatment"]
    if missing:
        raise RevenueError("Complete the checklist first: " + "; ".join(missing))
    ins = db.get(PatientInsurance, pa.insurance_id) if pa.insurance_id else None
    if not ins:
        raise RevenueError("No insurance on file for this patient")
    pa.status, pa.submitted_at = "submitted", now()
    r = simulated_payer_decision(pa, ins.member_id)
    pa.decided_at = now()
    if r["status"] == "approved":
        pa.status, pa.auth_number, pa.valid_from, pa.valid_to, pa.units_approved = "approved", r["auth_number"], r["valid_from"], r["valid_to"], r["units"]
    else:
        pa.status, pa.denial_reason = r["status"], r["reason"]
    audit.record(db, f"prior_auth.{pa.status}", org_id=pa.organization_id, actor_id=actor_id, resource_type="prior_auth", resource_id=pa.id,
                 patient_id=pa.patient_id, details={"code": pa.service_code, "simulated": True})
    return pa


# ---------- Claim review ----------

def _rule_findings(db: Session, c: Claim) -> list[dict]:
    out = []
    codes = pa_codes(db, c.organization_id)
    for ch in c.charges:
        if ch.code in codes and not approved_auth(db, c.patient_id, ch.code, c.service_date):
            out.append({"code": "missing_prior_auth", "severity": "blocker", "message": f"{ch.code} requires prior authorization; none approved for {c.service_date}",
                        "evidence": {"charge": ch.code}})
    note = db.scalar(select(ClinicalNote).where(ClinicalNote.encounter_id == c.encounter_id, ClinicalNote.status == "signed").limit(1))
    if not note:
        out.append({"code": "no_signed_documentation", "severity": "blocker", "message": "No signed clinical note supports this claim", "evidence": {}})
    else:
        text = " ".join(str(v) for v in (note.content or {}).values()).lower()
        dx = {d for ch in c.charges for d in (ch.diagnosis_codes or [])}
        if len(dx) >= 3 and len(text) < 200:
            out.append({"code": "thin_documentation", "severity": "warning", "message": f"{len(dx)} diagnoses billed but the signed note is very short ({len(text)} characters)",
                        "evidence": {"note_id": str(note.id)}})
    dup = db.scalar(select(Claim.id).where(Claim.patient_id == c.patient_id, Claim.service_date == c.service_date, Claim.id != c.id,
                                           Claim.status.not_in(("void",))).limit(1))
    if dup:
        out.append({"code": "possible_duplicate", "severity": "warning", "message": "Another claim exists for this patient on the same date of service",
                    "evidence": {"other_claim_id": str(dup)}})
    return out


def _ai_findings(db: Session, c: Claim) -> tuple[list[dict], str | None]:
    """Optional AI consistency check between the signed note and billed codes. Flags only; never edits."""
    from app.ai.openai_provider import available

    if not available("claims_review"):
        return [], None
    from pydantic import BaseModel

    from app.ai.config import effective
    from app.ai.openai_provider import OpenAICore
    from app.ai.policy import contains_phi
    from app.ai.provider import AIError

    class _F(BaseModel):
        code: str
        severity: str
        message: str

    class _Out(BaseModel):
        findings: list[_F]

    note = db.scalar(select(ClinicalNote).where(ClinicalNote.encounter_id == c.encounter_id, ClinicalNote.status == "signed").limit(1))
    if not note:
        return [], None
    lines = "\n".join(f"{ch.code} x{ch.units} dx {','.join(ch.diagnosis_codes or [])}: {ch.description}" for ch in c.charges)
    try:
        out, meta = OpenAICore().structured(
            system=("You review a claim against the signed clinical note for missing or inconsistent documentation. Report ONLY possible issues "
                    "(e.g. a billed diagnosis not mentioned in the note, a service not documented). Never suggest higher codes. severity is 'warning' or 'info'. "
                    "code is a short snake_case label."),
            content=[{"type": "input_text", "text": f"<document>NOTE:\n{note.content}\n\nCLAIM LINES:\n{lines}</document>"}], schema=_Out,
            contains_phi=contains_phi(db, c.organization_id), model=effective().model_for("claims_review"), max_output_tokens=1500, name="claim_review")
    except AIError:
        return [], None
    return [{"code": f.code[:40], "severity": "info" if f.severity not in ("warning", "info") else f.severity, "message": f.message[:500], "evidence": {}}
            for f in out.findings[:10]], meta.model


def review_claim(db: Session, c: Claim, *, actor_id) -> list[ClaimFinding]:
    """Re-run review: replace open findings with fresh ones (resolved/dismissed history is kept)."""
    for f in db.scalars(select(ClaimFinding).where(ClaimFinding.claim_id == c.id, ClaimFinding.status == "open")):
        db.delete(f)
    rule = _rule_findings(db, c)
    ai, model = _ai_findings(db, c)
    rows = [ClaimFinding(organization_id=c.organization_id, claim_id=c.id, source="rule", created_at=now(), **f) for f in rule]
    rows += [ClaimFinding(organization_id=c.organization_id, claim_id=c.id, source="ai", created_at=now(), model=model, **f) for f in ai]
    db.add_all(rows)
    db.flush()
    audit.record(db, "claim.reviewed", org_id=c.organization_id, actor_id=actor_id, resource_type="claim", resource_id=c.id, patient_id=c.patient_id,
                 details={"rule": len(rule), "ai": len(ai), "ai_model": model})
    return rows


def open_blockers(db: Session, claim_id) -> int:
    return len(db.scalars(select(ClaimFinding.id).where(ClaimFinding.claim_id == claim_id, ClaimFinding.status == "open",
                                                        ClaimFinding.severity == "blocker")).all())


# ---------- Facility charges ----------

def post_facility_charges(db: Session, stay: InpatientStay) -> int:
    if not (stay.encounter_id and stay.admitted_at and stay.discharged_at):
        return 0
    if db.scalar(select(Charge.id).where(Charge.encounter_id == stay.encounter_id, Charge.code.in_(("RB-MS", "RB-ICU"))).limit(1)):
        return 0
    days = max(1, math.ceil((stay.discharged_at - stay.admitted_at).total_seconds() / 86400))
    code, desc, default_price = FACILITY_CODES["icu" if stay.level_of_care == "icu" else "default"]
    fee = db.scalar(select(FeeScheduleItem).where(FeeScheduleItem.organization_id == stay.organization_id, FeeScheduleItem.code == code))
    if not fee:
        fee = FeeScheduleItem(organization_id=stay.organization_id, code=code, description=desc, price_cents=default_price)
        db.add(fee)
        db.flush()
    db.add(Charge(organization_id=stay.organization_id, encounter_id=stay.encounter_id, patient_id=stay.patient_id, code=code, description=desc,
                  units=min(days, 99), unit_price_cents=fee.price_cents, amount_cents=min(days, 99) * fee.price_cents, diagnosis_codes=[]))
    return days


@handler("facility_charges", "adt.discharged")
def _on_discharge(db: Session, ev: DomainEvent) -> None:
    stay = db.get(InpatientStay, uuid.UUID(ev.subject_id)) if ev.subject_id else None
    if stay:
        post_facility_charges(db, stay)
