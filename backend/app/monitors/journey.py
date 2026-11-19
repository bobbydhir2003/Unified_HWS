"""Patient journey monitors: follow-ups that were planned but not booked, and pre-visit questionnaires still missing."""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.security import now
from app.engine.cases import Finding, add_task
from app.engine.monitors import Monitor, register
from app.engine.notifications import deliver
from app.models import Appointment, Encounter, IntakeSubmission, Patient


class FollowUpNotBooked(Monitor):
    key = "journey.follow_up_not_booked"
    name = "Follow-up planned but not booked"
    description = "A completed visit documented a follow-up plan, but no future appointment exists for the patient."
    category = "patient_followup"
    default_config = {"grace_days": 2, "lookback_days": 30, "assign_role": "receptionist"}
    config_help = {"grace_days": "Days after the visit before opening a case", "lookback_days": "How far back to check completed visits",
                   "assign_role": "Owner role"}

    def evaluate(self, db, org_id, cfg):
        out = []
        encs = db.scalars(select(Encounter).where(Encounter.organization_id == org_id, Encounter.status == "completed", Encounter.follow_up.is_not(None),
                                                  Encounter.follow_up != "", Encounter.completed_at < now() - timedelta(days=int(cfg["grace_days"])),
                                                  Encounter.completed_at > now() - timedelta(days=int(cfg["lookback_days"])))).all()
        for e in encs:
            booked = db.scalar(select(Appointment.id).where(Appointment.patient_id == e.patient_id, Appointment.start_at > e.completed_at,
                                                            Appointment.status.in_(("scheduled", "confirmed", "checked_in", "completed"))).limit(1))
            if booked:
                continue
            p = db.get(Patient, e.patient_id)
            out.append(Finding(dedupe_key=f"fu:{e.id}", kind=self.key, category="patient_followup", severity="medium",
                               title=f"Follow-up not booked — {p.full_name}: {e.follow_up[:80]}", patient_id=p.id, facility_id=e.clinic_id,
                               subject_type="encounter", subject_id=str(e.id), assign_role=cfg["assign_role"], link=f"/patients/{p.id}/appointments",
                               sla_minutes=2880, evidence={"plan": e.follow_up, "visit_completed": e.completed_at.isoformat()}))
        return out

    def on_open(self, db, case, f, cfg):
        add_task(db, case, org_id=case.organization_id, title=case.title.replace("Follow-up not booked — ", "Book follow-up: "), role=cfg["assign_role"],
                 dedupe_key=f"task:{case.dedupe_key}", kind="journey.book_follow_up")

    def clear(self, db, case, cfg):
        return "verified_active", "A follow-up appointment is now booked."


class IntakeMissing(Monitor):
    key = "journey.intake_missing"
    name = "Pre-visit questionnaire missing"
    description = "Visits within the window whose pre-visit questionnaire isn't submitted. Sends one portal reminder per visit (deduplicated)."
    category = "scheduling"
    default_config = {"hours_before": 48, "assign_role": "receptionist"}
    config_help = {"hours_before": "Remind patients this many hours before the visit", "assign_role": "Owner role"}

    def evaluate(self, db, org_id, cfg):
        out = []
        appts = db.scalars(select(Appointment).where(Appointment.organization_id == org_id, Appointment.start_at > now(),
                                                     Appointment.start_at < now() + timedelta(hours=int(cfg["hours_before"])),
                                                     Appointment.status.in_(("scheduled", "confirmed")))).all()
        for a in appts:
            if db.scalar(select(IntakeSubmission.id).where(IntakeSubmission.appointment_id == a.id)):
                continue
            if not a.patient.portal_user_id:
                continue  # front desk collects on arrival; no case needed
            out.append(Finding(dedupe_key=f"intake:{a.id}", kind=self.key, category="scheduling", severity="low",
                               title=f"Pre-visit questionnaire not completed — {a.patient.full_name}, {a.start_at:%b %d %H:%M}", patient_id=a.patient_id,
                               facility_id=a.clinic_id, subject_type="appointment", subject_id=str(a.id), assign_role=cfg["assign_role"],
                               link="/front-desk", sla_minutes=max(int((a.start_at - now()).total_seconds() // 60) - 60, 30),
                               evidence={"visit_at": a.start_at.isoformat()}))
        return out

    def on_open(self, db, case, f, cfg):
        deliver(db, case.organization_id, channel="portal", dedupe=f"{case.dedupe_key}:reminder", subject="Please complete your pre-visit questionnaire",
                body="It takes about two minutes and helps your visit go faster.", category="appointments",
                link=f"/portal/appointments/{case.subject_id}/intake", case=case, patient_id=case.patient_id)

    def clear(self, db, case, cfg):
        a = db.get(Appointment, uuid.UUID(case.subject_id))
        return ("verified_active", "Questionnaire submitted.") if a and a.status in ("scheduled", "confirmed") else ("no_longer_applicable", "Visit changed.")


register(FollowUpNotBooked())
register(IntakeMissing())
