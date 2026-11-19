"""Insurance Guardian monitors.

1. insurance.visit_readiness — every upcoming visit must have payer-verified coverage for its date of service. The monitor
   first runs automatic (batch) eligibility checks, then opens one case per visit that is still not verified. Patients are
   asked for updated insurance only when the payer says inactive or nothing is on file; staff get a task otherwise.
2. insurance.stored_end_date — a stored plan end date is approaching. This is a prompt to *confirm renewal*, never a claim
   that coverage ended; it clears when the payer reports coverage continuing, a newer plan is on file, or the date changes.

Every reminder step is delivered at most once (dedupe key per case + step); patient messages are capped per day.
"""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import now
from app.engine.cases import Finding, add_task, log_event
from app.engine.events import handler
from app.engine.monitors import Monitor, register, run_monitor
from app.engine.notifications import deliver
from app.models import (
    Appointment,
    Case,
    CoverageUpdateRequest,
    DomainEvent,
    EligibilityCheck,
    Patient,
    PatientInsurance,
)
from app.services.insurance import coverage_state, hours_until, run_check

STATE_TEXT = {
    "no_coverage": "No insurance on file",
    "verified_inactive": "Payer reports coverage inactive",
    "unverified": "Eligibility not yet verified",
    "stale": "Eligibility needs re-verification",
    "error": "Payer could not be reached",
}
PATIENT_ACTION_STATES = {"no_coverage", "verified_inactive"}


def _local_date(a: Appointment) -> date:
    from zoneinfo import ZoneInfo

    return a.start_at.astimezone(ZoneInfo(a.clinic.timezone or "UTC")).date()


def ensure_update_request(db: Session, case: Case, patient_id: uuid.UUID, reason: str,
                          appointment_id: uuid.UUID | None) -> CoverageUpdateRequest:
    req = db.scalar(select(CoverageUpdateRequest).where(CoverageUpdateRequest.patient_id == patient_id,
                                                        CoverageUpdateRequest.status.in_(("requested", "submitted"))))
    if req:
        if req.case_id is None:
            req.case_id = case.id
        return req
    req = CoverageUpdateRequest(organization_id=case.organization_id, patient_id=patient_id, case_id=case.id, reason=reason[:300],
                                appointment_id=appointment_id)
    db.add(req)
    db.flush()
    log_event(db, case, "patient_request", "Asked the patient to confirm or update insurance in the portal",
              data={"request_id": str(req.id)})
    return req


def _step_due(hours_left: float, steps: list[int]) -> int | None:
    """Most recent reminder threshold crossed (e.g. steps [336,168,48], 100h left → 168). Earlier steps are skipped."""
    crossed = [h for h in steps if hours_left <= h]
    return min(crossed) if crossed else None


class VisitReadiness(Monitor):
    key = "insurance.visit_readiness"
    name = "Insurance Guardian — visit readiness"
    description = ("Verifies coverage with the payer for every upcoming visit (automatic batch checks first), then opens one "
                   "case per visit that is still not verified. Patients are asked for new insurance only when the payer reports "
                   "inactive coverage or none is on file.")
    category = "insurance"
    default_config = {"lookahead_days": 14, "fresh_days": 7, "auto_verify": True, "max_auto_checks": 200,
                      "reminder_hours_before_visit": [336, 168, 48], "assign_role": "insurance_specialist",
                      "escalate_to": "clinic_admin"}
    config_help = {"lookahead_days": "How far ahead to check scheduled visits",
                   "fresh_days": "An active payer response within this many days of the visit counts as verified",
                   "auto_verify": "Run automatic eligibility checks before opening cases",
                   "max_auto_checks": "Upper bound of automatic payer inquiries per run",
                   "reminder_hours_before_visit": "Patient reminder steps (hours before the visit); each sent once",
                   "assign_role": "Role that owns these cases", "escalate_to": "Role that receives escalations"}

    def evaluate(self, db: Session, org_id: uuid.UUID, cfg: dict) -> list[Finding]:
        horizon = now() + timedelta(days=int(cfg["lookahead_days"]))
        appts = db.scalars(select(Appointment).where(
            Appointment.organization_id == org_id, Appointment.start_at > now(), Appointment.start_at <= horizon,
            Appointment.status.in_(("scheduled", "confirmed")), Appointment.coverage_override.is_(None))
            .order_by(Appointment.start_at)).all()
        budget = [int(cfg["max_auto_checks"]) if cfg.get("auto_verify") else 0]
        by_patient: dict[uuid.UUID, list[Appointment]] = {}
        for a in appts:
            by_patient.setdefault(a.patient_id, []).append(a)
        out: list[Finding] = []
        for pid, visits in by_patient.items():
            problems = []
            for a in visits:
                st = self._state(db, a, cfg, budget)
                if not st.verified:
                    problems.append((a, st))
            if not problems:
                continue
            a, st = problems[0]  # the earliest unverified visit drives severity and SLA
            h = hours_until(a.start_at)
            severity = "high" if h <= 48 else "medium" if h <= 168 else "low"
            p = a.patient
            more = f" (+{len(problems) - 1} more visit{'s' if len(problems) > 2 else ''})" if len(problems) > 1 else ""
            out.append(Finding(
                dedupe_key=f"ins.readiness:{pid}", kind=self.key, category="insurance", severity=severity,
                title=f"{STATE_TEXT[st.state]} — {p.full_name}, visit {a.start_at:%b %d}{more}",
                summary=f"{st.reason}. Next affected visit {a.start_at:%a %b %d %H:%M} UTC at {a.clinic.name}.",
                patient_id=p.id, subject_type="appointment", subject_id=str(a.id), facility_id=a.clinic_id,
                assign_role=cfg["assign_role"], link=f"/insurance?patient={p.id}", sla_minutes=max(int((h - 48) * 60), 60),
                escalate_to=cfg["escalate_to"],
                evidence={"state": st.state, "reason": st.reason, "visit_at": a.start_at.isoformat(),
                          "insurance_id": str(st.insurance.id) if st.insurance else None,
                          "payer": st.insurance.payer_name if st.insurance else None,
                          "stored_end_date": st.insurance.termination_date.isoformat() if st.insurance and st.insurance.termination_date else None,
                          "last_check": {"id": str(st.check.id), "result": st.check.result, "at": st.check.checked_at.isoformat(),
                                         "source": st.check.source, "trace": st.check.payer_trace} if st.check else None,
                          "visits": [{"appointment_id": str(v.id), "at": v.start_at.isoformat(), "state": vs.state} for v, vs in problems]},
                data={"appointment_id": str(a.id), "visit_at": a.start_at.isoformat(), "state": st.state}))
        return out

    def _state(self, db: Session, a: Appointment, cfg: dict, budget: list[int]):
        dos = _local_date(a)
        st = coverage_state(db, a.patient_id, dos, int(cfg["fresh_days"]))
        if st.state in ("unverified", "stale", "error") and st.insurance and budget[0] > 0:
            recent_same_dos = db.scalar(select(EligibilityCheck.id).where(
                EligibilityCheck.insurance_id == st.insurance.id, EligibilityCheck.date_of_service == dos,
                EligibilityCheck.checked_at > now() - timedelta(hours=12)).limit(1))
            if not recent_same_dos:
                run_check(db, st.insurance, dos=dos, trigger="auto_batch", actor_id=None, appointment_id=a.id, emit_event=False)
                budget[0] -= 1
                st = coverage_state(db, a.patient_id, dos, int(cfg["fresh_days"]))
        return st

    def on_open(self, db: Session, case: Case, f: Finding, cfg: dict) -> None:
        state = f.evidence["state"]
        what = {"no_coverage": "Collect insurance or confirm self-pay", "verified_inactive": "Resolve inactive coverage",
                "error": "Re-run eligibility / call payer", "stale": "Re-verify eligibility", "unverified": "Verify eligibility"}[state]
        add_task(db, case, org_id=case.organization_id, title=f"{what}: {case.title.split(' — ', 1)[-1]}", role=cfg["assign_role"],
                 dedupe_key=f"task:{case.dedupe_key}", priority="high" if case.severity == "high" else "normal",
                 kind="insurance.verify", link=case.link, due_minutes=max(int((hours_until(datetime.fromisoformat(f.data["visit_at"])) - 48) * 60), 60))

    def on_tick(self, db: Session, case: Case, f: Finding, cfg: dict) -> None:
        state = f.evidence["state"]
        if state not in PATIENT_ACTION_STATES or not case.patient_id:
            return
        visit_at = datetime.fromisoformat(f.data["visit_at"])
        req = ensure_update_request(db, case, case.patient_id, f"Before your visit on {visit_at:%b %d}, please confirm your insurance.",
                                    uuid.UUID(f.data["appointment_id"]))
        if req.status == "submitted":
            return  # waiting on staff confirmation; don't nag the patient
        step = _step_due(hours_until(visit_at), list(cfg["reminder_hours_before_visit"]))
        if step is None:
            return
        p = db.get(Patient, case.patient_id)
        when = f"{visit_at:%A, %B %d}"
        subject = "Please confirm your insurance before your visit"
        body = (f"Hi {p.first_name}, before your visit on {when} we need current insurance information. "
                "Please sign in to the patient portal and upload a photo of your insurance card (front and back), or let us know "
                "if you'll be paying yourself. — Your care team")
        for channel in ("portal", "email"):
            deliver(db, case.organization_id, channel=channel, dedupe=f"{case.dedupe_key}:patient:{step}h:{channel}", subject=subject,
                    body=body, category="insurance", link="/portal/insurance", case=case, patient_id=p.id)

    def clear(self, db: Session, case: Case, cfg: dict) -> tuple[str, str]:
        appt = db.get(Appointment, uuid.UUID(case.subject_id)) if case.subject_id else None
        upcoming = db.scalars(select(Appointment).where(
            Appointment.patient_id == case.patient_id, Appointment.start_at > now(),
            Appointment.start_at <= now() + timedelta(days=int(cfg["lookahead_days"])),
            Appointment.status.in_(("scheduled", "confirmed")))).all()
        if not upcoming:
            return "no_longer_applicable", "No upcoming visits in the monitoring window (cancelled, completed or moved)."
        if appt is not None and appt.coverage_override and all(a.coverage_override for a in upcoming):
            return "staff_override", f"Staff cleared the visit(s) as {appt.coverage_override.replace('_', ' ')}: {appt.coverage_override_reason}"
        st = coverage_state(db, case.patient_id, _local_date(upcoming[0]), int(cfg["fresh_days"]))
        if st.verified and st.check:
            return "verified_active", (f"Verified: payer reported active coverage ({st.check.source} check {st.check.payer_trace}, "
                                       f"{st.check.checked_at:%b %d %H:%M} UTC) for every upcoming visit.")
        return "staff_override", "Remaining visits were cleared by staff."


class StoredEndDate(Monitor):
    key = "insurance.stored_end_date"
    name = "Insurance Guardian — renewal reminders"
    description = ("A plan's *stored* end date is approaching. Asks the patient to confirm renewal or upload a new card. "
                   "Clears automatically when the payer reports coverage continuing past that date, a newer plan is on file, "
                   "or the stored date is corrected.")
    category = "insurance"
    default_config = {"window_days": 30, "renewal_reminder_days": [30, 14, 7], "assign_role": "insurance_specialist",
                      "escalate_to": "clinic_admin"}
    config_help = {"window_days": "Start monitoring this many days before the stored end date",
                   "renewal_reminder_days": "Patient reminder steps (days before the stored end date); each sent once",
                   "assign_role": "Role that owns these cases", "escalate_to": "Role that receives escalations"}

    def _continues(self, db: Session, ins: PatientInsurance) -> bool:
        chk = db.scalar(select(EligibilityCheck).where(EligibilityCheck.insurance_id == ins.id, EligibilityCheck.result == "active",
                                                       EligibilityCheck.checked_at >= ins.updated_at - timedelta(seconds=5))
                        .order_by(EligibilityCheck.checked_at.desc()).limit(1))
        return bool(chk and (chk.coverage_end is None or chk.coverage_end > ins.termination_date))

    def evaluate(self, db: Session, org_id: uuid.UUID, cfg: dict) -> list[Finding]:
        today = now().date()
        rows = db.scalars(select(PatientInsurance).where(
            PatientInsurance.organization_id == org_id, PatientInsurance.is_active.is_(True),
            PatientInsurance.termination_date.is_not(None), PatientInsurance.termination_date >= today,
            PatientInsurance.termination_date <= today + timedelta(days=int(cfg["window_days"])))).all()
        out = []
        for ins in rows:
            newer = db.scalar(select(PatientInsurance.id).where(PatientInsurance.patient_id == ins.patient_id, PatientInsurance.id != ins.id,
                                                                PatientInsurance.is_active.is_(True),
                                                                PatientInsurance.effective_date > ins.termination_date))
            if newer or self._continues(db, ins):
                continue
            p = db.get(Patient, ins.patient_id)
            days = (ins.termination_date - today).days
            out.append(Finding(
                dedupe_key=f"ins.renewal:{ins.id}:{ins.termination_date.isoformat()}", kind=self.key, category="insurance",
                severity="medium" if days <= 7 else "low",
                title=f"Confirm renewal — {p.full_name}: stored end date {ins.termination_date:%b %d}",
                summary=(f"{ins.payer_name} plan has a stored end date of {ins.termination_date:%b %d, %Y} ({days} days). This is the "
                         "date on file, not a payer response — confirm renewal or collect the new plan."),
                patient_id=p.id, subject_type="insurance", subject_id=str(ins.id), assign_role=cfg["assign_role"],
                link=f"/insurance?patient={p.id}", sla_minutes=max(days - 3, 1) * 1440, escalate_to=cfg["escalate_to"],
                evidence={"stored_end_date": ins.termination_date.isoformat(), "payer": ins.payer_name, "days_left": days,
                          "eligibility_status_on_file": ins.eligibility_status},
                data={"insurance_id": str(ins.id), "end": ins.termination_date.isoformat()}))
        return out

    def on_tick(self, db: Session, case: Case, f: Finding, cfg: dict) -> None:
        days = f.evidence["days_left"]
        steps = list(cfg["renewal_reminder_days"])
        crossed = [d for d in steps if days <= d]
        if not crossed or not case.patient_id:
            return
        step = min(crossed)
        p = db.get(Patient, case.patient_id)
        end = date.fromisoformat(f.data["end"])
        ensure_update_request(db, case, p.id, f"Our records show your {f.evidence['payer']} plan may end on {end:%b %d}.", None)
        body = (f"Hi {p.first_name}, our records show your {f.evidence['payer']} plan may end on {end:%B %d}. If your coverage is "
                "renewing or changing, please upload your current insurance card in the patient portal so we can verify it. "
                "If nothing has changed, you can ignore this message. — Your care team")
        for channel in ("portal", "email"):
            deliver(db, case.organization_id, channel=channel, dedupe=f"{case.dedupe_key}:patient:{step}d:{channel}",
                    subject="Is your insurance renewing?", body=body, category="insurance", link="/portal/insurance", case=case,
                    patient_id=p.id)

    def clear(self, db: Session, case: Case, cfg: dict) -> tuple[str, str]:
        ins = db.get(PatientInsurance, uuid.UUID(case.data["insurance_id"])) if case.data.get("insurance_id") else None
        if ins is None or not ins.is_active:
            return "no_longer_applicable", "Plan is no longer on file as active."
        if ins.termination_date is None or ins.termination_date.isoformat() != case.data.get("end"):
            return "data_corrected", "Stored end date was updated."
        if self._continues(db, ins):
            return "verified_active", "Payer reports coverage continuing beyond the stored end date."
        return "verified_active", "A newer plan is on file."


register(VisitReadiness())
register(StoredEndDate())


@handler("insurance_guardian_recheck", "insurance.eligibility_checked", "insurance.coverage_changed", "appointment.coverage_override",
         "appointment.no_show")
def recheck(db: Session, ev: DomainEvent) -> None:
    """Event-driven Verify step: re-evaluate immediately instead of waiting for the next scheduled run."""
    for key in ("insurance.visit_readiness", "insurance.stored_end_date"):
        run_monitor(db, ev.organization_id, key)


