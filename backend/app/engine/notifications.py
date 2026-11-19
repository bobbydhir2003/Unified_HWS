"""Notification service: one delivery row per (dedupe key), preference checks, patient frequency caps, delivery log.

Channels: in_app (staff/portal bell), portal (portal bell for the patient's linked user), email, sms. Email/SMS go
through the configured message gateway — simulated (outbox only) until a vendor with a BAA is connected.
"""

import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.security import now
from app.models import Case, NotificationDelivery, NotificationPreference, Patient
from app.services.notify import notify

PATIENT_DAILY_CAP = 3  # patient-facing deliveries per 24h across all cases (email+sms+portal)


def _pref(db: Session, org_id: uuid.UUID, *, user_id=None, patient_id=None, category: str) -> NotificationPreference | None:
    q = select(NotificationPreference).where(NotificationPreference.organization_id == org_id,
                                             NotificationPreference.category.in_((category, "*")))
    q = q.where(NotificationPreference.user_id == user_id) if user_id else q.where(NotificationPreference.patient_id == patient_id)
    prefs = db.scalars(q).all()
    return next((p for p in prefs if p.category == category), None) or next(iter(prefs), None)


def deliver(db: Session, org_id: uuid.UUID, *, channel: str, dedupe: str, subject: str, body: str, category: str = "general",
            link: str | None = None, case: Case | None = None, user_id: uuid.UUID | None = None,
            patient_id: uuid.UUID | None = None) -> NotificationDelivery | None:
    """Send once per dedupe key. Returns the delivery row, or None if this step was already delivered."""
    row = {"id": uuid.uuid4(), "organization_id": org_id, "case_id": case.id if case else None, "channel": channel,
           "category": category, "recipient_user_id": user_id, "recipient_patient_id": patient_id, "subject": subject[:300],
           "body": body, "link": link, "dedupe_key": dedupe[:200], "status": "queued"}
    new_id = db.execute(insert(NotificationDelivery).values(**row).on_conflict_do_nothing(
        index_elements=["organization_id", "dedupe_key"]).returning(NotificationDelivery.id)).scalar()
    if new_id is None:
        return None
    d = db.get(NotificationDelivery, new_id)
    d.attempts = 1
    pref = _pref(db, org_id, user_id=user_id, patient_id=patient_id, category=category) if (user_id or patient_id) else None
    if pref is not None and not getattr(pref, channel, True):
        d.status, d.status_reason = "suppressed", f"recipient opted out of {channel} for {category}"
        return d
    patient = db.get(Patient, patient_id) if patient_id else None
    if patient is not None:
        sent_24h = db.scalar(select(func.count()).select_from(NotificationDelivery).where(
            NotificationDelivery.organization_id == org_id, NotificationDelivery.recipient_patient_id == patient_id,
            NotificationDelivery.status.in_(("sent", "simulated")), NotificationDelivery.created_at > now() - timedelta(hours=24)))
        if sent_24h >= PATIENT_DAILY_CAP:
            d.status, d.status_reason = "suppressed", f"daily patient cap ({PATIENT_DAILY_CAP}) reached"
            return d
    try:
        if channel == "in_app":
            if not user_id:
                raise ValueError("in_app needs a user")
            notify(db, org_id, user_id, category, subject[:200], body[:500], link)
            d.status = "sent"
        elif channel == "portal":
            if not (patient and patient.portal_user_id):
                d.status, d.status_reason = "suppressed", "patient has no portal account"
                return d
            notify(db, org_id, patient.portal_user_id, category, subject[:200], body[:500], link)
            d.status = "sent"
        elif channel in ("email", "sms"):
            to = (patient.email if channel == "email" else patient.phone) if patient else None
            if not to:
                d.status, d.status_reason = "suppressed", f"no {channel} address on file"
                return d
            from app.integrations.adapters import message_gateway

            message_gateway().send(db, channel=channel, to=to, subject=subject, body=body, org_id=org_id)
            d.address, d.status, d.status_reason = to, "simulated", "development outbox — not sent externally"
        else:
            raise ValueError(f"unknown channel {channel}")
        d.sent_at = now()
    except Exception as e:  # noqa: BLE001
        d.status, d.status_reason = "failed", f"{type(e).__name__}: {str(e)[:150]}"
    if case is not None and d.status in ("sent", "simulated"):
        from app.engine.cases import log_event

        who = "patient" if patient_id else "staff"
        log_event(db, case, "notification", f"{channel.replace('_', '-')} notification to {who}: {subject[:120]}",
                  data={"delivery_id": str(d.id), "channel": channel, "status": d.status})
    return d


def deliver_to_role(db: Session, org_id: uuid.UUID, role: str, *, subject: str, body: str, dedupe: str, link: str | None = None,
                    case: Case | None = None, category: str = "general") -> int:
    from app.engine.cases import role_user_ids

    n = 0
    for uid in role_user_ids(db, org_id, role):
        if deliver(db, org_id, channel="in_app", dedupe=f"{dedupe}:u:{uid}", subject=subject, body=body, link=link, case=case,
                   category=category, user_id=uid):
            n += 1
    return n


def failures(db: Session, org_id: uuid.UUID, hours: int = 24) -> int:
    return db.scalar(select(func.count()).select_from(NotificationDelivery).where(
        NotificationDelivery.organization_id == org_id, NotificationDelivery.status == "failed",
        NotificationDelivery.created_at > now() - timedelta(hours=hours))) or 0


