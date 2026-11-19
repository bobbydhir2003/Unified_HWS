"""Background tasks. Each task opens its own DB session."""

import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import now
from app.worker import celery_app

log = logging.getLogger("undeclared.tasks")


@celery_app.task(name="app.tasks.send_appointment_reminders")
def send_appointment_reminders() -> int:
    """Queue reminders for appointments 24–25h out. Delivery is simulated (outbox) until an SMS/email vendor is wired."""
    from app.models import Appointment
    from app.services.identity import send_email

    db = SessionLocal()
    try:
        window_start, window_end = now() + timedelta(hours=23), now() + timedelta(hours=25)
        appts = db.scalars(select(Appointment).where(
            Appointment.start_at.between(window_start, window_end),
            Appointment.status.in_(("scheduled", "confirmed")),
            Appointment.reminder_sent_at.is_(None),
        )).all()
        for a in appts:
            if a.patient.email:
                send_email(db, a.patient.email, "Appointment reminder",
                           f"Reminder: you have an appointment at {a.clinic.name} on "
                           f"{a.start_at:%A %b %d at %I:%M %p} UTC.", a.organization_id)
            a.reminder_sent_at = now()
        db.commit()
        log.info("reminders queued", extra={"count": len(appts)})
        return len(appts)
    finally:
        db.close()


@celery_app.task(name="app.tasks.process_document", autoretry_for=(), acks_late=True)
def process_document_task(doc_id: str) -> None:
    import uuid

    from app.services.documents import process_document

    db = SessionLocal()
    try:
        process_document(db, uuid.UUID(doc_id))
    finally:
        db.close()


@celery_app.task(name="app.tasks.scribe_transcribe")
def scribe_transcribe_task(session_id: str) -> None:
    import uuid

    from app.services.scribe import transcribe

    db = SessionLocal()
    try:
        transcribe(db, uuid.UUID(session_id))
    finally:
        db.close()


@celery_app.task(name="app.tasks.scribe_draft")
def scribe_draft_task(session_id: str) -> None:
    import uuid

    from app.services.scribe import draft

    db = SessionLocal()
    try:
        draft(db, uuid.UUID(session_id))
    finally:
        db.close()
