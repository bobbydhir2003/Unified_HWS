"""AI receptionist conversation engine (sandbox). Deterministic state machine with safety rules that hold on every turn:

1. The caller is told they're speaking with an automated assistant and that the call is recorded; consent is required.
2. Emergency language → advise 911, create an urgent staff task, stop automation.
3. No patient information is disclosed until name AND date of birth match exactly one record (3 attempts, then staff handoff).
4. Anything clinical (refills, results, symptoms) is handed to staff as a task — the assistant never gives medical advice.
"""

import re
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import now
from app.models import (
    Appointment,
    AppointmentType,
    Clinic,
    Organization,
    Patient,
    ProviderAvailability,
    Task,
    VoiceCall,
)
from app.models.scheduling import INACTIVE_APPOINTMENT_STATUSES

EMERGENCY = re.compile(r"\b(chest pain|can'?t breathe|not breathing|suicid|kill myself|overdose|stroke|unconscious|severe bleeding|heart attack)\b", re.I)
HUMAN = re.compile(r"\b(human|person|operator|representative|someone|staff|receptionist|front desk)\b", re.I)
YES = re.compile(r"^\s*(y|yes|yeah|yep|sure|ok|okay|correct|that'?s fine|go ahead)\b", re.I)
NO = re.compile(r"^\s*(n|no|nope|don'?t|do not)\b", re.I)
BYE = re.compile(r"\b(bye|goodbye|that'?s all|that is all|nothing else|no thanks|hang up)\b", re.I)


def _say(call: VoiceCall, speaker: str, text: str) -> None:
    call.transcript = [*call.transcript, {"speaker": speaker, "text": text, "at": now().isoformat()}]


def _task(db: Session, call: VoiceCall, title: str, role: str, priority: str = "normal", detail: str | None = None) -> None:
    db.add(Task(organization_id=call.organization_id, title=title[:200], description=detail, patient_id=call.verified_patient_id,
                assigned_role=role, priority=priority, source="receptionist", link="/receptionist"))


def _parse_dob(text: str) -> date | None:
    t = text.strip()
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%B %d %Y", "%B %d, %Y", "%b %d %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(re.sub(r"(\d)(st|nd|rd|th)", r"\1", t), fmt).date()
        except ValueError:
            continue
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def _clinic(db: Session, org_id: uuid.UUID) -> Clinic:
    return db.scalar(select(Clinic).where(Clinic.organization_id == org_id, Clinic.is_active.is_(True)).order_by(Clinic.name))


def _intent(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\b(cancel)\b", t):
        return "cancel"
    if re.search(r"\b(book|schedule|make an appointment|new appointment|see the doctor|reschedule)\b", t):
        return "book"
    if re.search(r"\b(my appointment|when is|upcoming|next appointment)\b", t):
        return "list"
    if re.search(r"\b(hours|open|close|address|location|where are you|directions|parking|phone number|fax)\b", t):
        return "info"
    if re.search(r"\b(refill|prescription|pharmacy|medication|results?|lab|test|symptom|sick|pain|fever|question for (the )?(doctor|nurse))\b", t):
        return "clinical"
    if re.search(r"\b(bill|payment|insurance|balance|charge)\b", t):
        return "billing"
    return None


def start(db: Session, org: Organization, from_number: str | None, user_id: uuid.UUID | None, channel: str = "sandbox") -> VoiceCall:
    call = VoiceCall(organization_id=org.id, from_number=from_number, channel=channel, state={"stage": "consent", "attempts": 0}, transcript=[],
                     started_by_id=user_id)
    db.add(call)
    _say(call, "assistant", f"Thank you for calling {org.name}. I'm an automated AI assistant, and this call is recorded for quality and "
                            "documentation. If this is a medical emergency, hang up and dial 911. Is it okay to continue with me? You can also say 'staff' "
                            "at any time to reach a person.")
    return call


def _transfer(db: Session, call: VoiceCall, reason: str, priority: str = "normal") -> str:
    call.status, call.outcome = "transferred", reason
    _task(db, call, f"Call back: {reason}" + (f" ({call.from_number})" if call.from_number else ""), "receptionist", priority,
          "Caller requested a person or the assistant couldn't help.")
    return "I'll connect you with our staff. In this sandbox a call-back task has been created for the front desk."


def _offer_slots(db: Session, call: VoiceCall, p: Patient) -> str:
    clinic = db.get(Clinic, p.primary_clinic_id) if p.primary_clinic_id else _clinic(db, call.organization_id)
    tz = ZoneInfo(clinic.timezone)
    prov_ids = [p.primary_provider_id] if p.primary_provider_id else list(db.scalars(select(ProviderAvailability.provider_id).where(
        ProviderAvailability.clinic_id == clinic.id).distinct()).all())
    t = db.scalar(select(AppointmentType).where(AppointmentType.organization_id == call.organization_id, AppointmentType.name == "Follow-up")) \
        or db.scalar(select(AppointmentType).where(AppointmentType.organization_id == call.organization_id, AppointmentType.is_telehealth.is_(False)))
    offers = []
    day = now().astimezone(tz).date() + timedelta(days=1)
    for _ in range(14):
        for prov in prov_ids:
            blocks = db.scalars(select(ProviderAvailability).where(ProviderAvailability.provider_id == prov, ProviderAvailability.clinic_id == clinic.id,
                                                                   ProviderAvailability.weekday == day.weekday()).order_by(ProviderAvailability.start_time)).all()
            for b in blocks:
                s = datetime.combine(day, b.start_time, tz)
                while s + timedelta(minutes=t.duration_minutes) <= datetime.combine(day, b.end_time, tz) and len(offers) < 3:
                    e = s + timedelta(minutes=t.duration_minutes)
                    busy = db.scalar(select(func.count()).select_from(Appointment).where(
                        Appointment.provider_id == prov, Appointment.status.not_in(INACTIVE_APPOINTMENT_STATUSES), Appointment.start_at < e, Appointment.end_at > s))
                    if not busy and not any(o["start"][:10] == s.isoformat()[:10] for o in offers):
                        offers.append({"start": s.isoformat(), "end": e.isoformat(), "provider_id": str(prov), "clinic_id": str(clinic.id), "type_id": str(t.id)})
                    s += timedelta(minutes=30)
        if len(offers) >= 3:
            break
        day += timedelta(days=1)
    call.state = {**call.state, "stage": "book_pick", "offers": offers}
    if not offers:
        call.state["stage"] = "menu"
        return _transfer(db, call, "No open slots found for booking")
    opts = "; ".join(f"option {i + 1}, {datetime.fromisoformat(o['start']):%A %B %-d at %-I:%M %p}" for i, o in enumerate(offers))
    return f"I have these openings at {clinic.name}: {opts}. Which option would you like?"


def _pick(text: str, n: int) -> int | None:
    m = re.search(r"\b([1-9])\b", text) or re.search(r"\b(one|two|three|first|second|third)\b", text.lower())
    if not m:
        return None
    v = {"one": 1, "first": 1, "two": 2, "second": 2, "three": 3, "third": 3}.get(m.group(1), None) or int(m.group(1))
    return v - 1 if 1 <= v <= n else None


def _verified(db: Session, call: VoiceCall) -> Patient | None:
    return db.get(Patient, call.verified_patient_id) if call.verified_patient_id else None


def _handle_intent(db: Session, call: VoiceCall, intent: str) -> str:
    p = _verified(db, call)
    call.intent = intent
    if intent == "info":
        c = _clinic(db, call.organization_id)
        return (f"{c.name} is at {c.address_line1 or 'our main location'}, {c.city or ''}. We're open Monday to Friday, 8 AM to 5 PM. "
                f"Our phone number is {c.phone or 'on our website'}. Is there anything else?")
    if intent in ("clinical", "billing"):
        role = "nurse" if intent == "clinical" else "billing"
        call.outcome = f"{intent.title()} request routed to {role}"
        _task(db, call, f"Phone request ({intent}) from {p.full_name if p else 'unverified caller'}", role, "normal", "Created by AI receptionist.")
        return (f"I can't help with {'medical questions, refills or results' if intent == 'clinical' else 'billing details'} directly, "
                f"but I've sent your request to our {'nursing' if intent == 'clinical' else 'billing'} team and they'll call you back. Anything else?")
    if not p:
        call.state = {**call.state, "stage": "identify_name", "pending_intent": intent}
        return "I can help with that. First I need to confirm who you are. Please tell me the patient's first and last name."
    if intent == "book":
        return _offer_slots(db, call, p)
    upcoming = db.scalars(select(Appointment).where(Appointment.patient_id == p.id, Appointment.start_at > now(),
                                                    Appointment.status.in_(("scheduled", "confirmed"))).order_by(Appointment.start_at).limit(3)).all()
    if not upcoming:
        call.state = {**call.state, "stage": "menu"}
        return "I don't see any upcoming appointments for you. Would you like to book one?"
    listing = "; ".join(f"option {i + 1}, {a.start_at.astimezone(ZoneInfo(a.clinic.timezone)):%A %B %-d at %-I:%M %p} with {a.provider.user.display_name}" for i, a in enumerate(upcoming))
    if intent == "list":
        call.state = {**call.state, "stage": "menu"}
        return f"Your upcoming appointments: {listing}. Anything else?"
    call.state = {**call.state, "stage": "cancel_pick", "appts": [str(a.id) for a in upcoming]}
    return f"Your upcoming appointments are: {listing}. Which one would you like to cancel?"


def message(db: Session, call: VoiceCall, text: str) -> str:
    text = text.strip()[:500]
    _say(call, "caller", text)
    st = dict(call.state or {})
    stage = st.get("stage", "consent")
    reply: str
    if EMERGENCY.search(text):
        call.status, call.outcome = "transferred", "Possible emergency — caller advised to dial 911"
        _task(db, call, f"URGENT: possible emergency call{f' from {call.from_number}' if call.from_number else ''}", "doctor", "urgent", f"Caller said: {text[:300]}")
        reply = "This sounds like it could be an emergency. Please hang up and dial 911 now, or go to the nearest emergency department. I've alerted our clinical staff."
    elif stage == "consent":
        if YES.search(text):
            st["stage"] = "menu"
            call.consented = True
            reply = "Thank you. I can help you book or cancel an appointment, check your upcoming appointments, or answer questions about our hours and location. How can I help?"
        elif NO.search(text) or HUMAN.search(text):
            reply = _transfer(db, call, "Caller declined the AI assistant")
        else:
            reply = "Sorry, I didn't catch that. Is it okay to continue with the automated assistant? Please say yes or no."
    elif HUMAN.search(text):
        reply = _transfer(db, call, "Caller asked for a person")
    elif BYE.search(text) and stage not in ("identify_name", "identify_dob"):
        call.status = "completed"
        reply = "Thank you for calling. Goodbye!"
    elif stage == "identify_name":
        parts = re.findall(r"[A-Za-z'-]+", text)
        if len(parts) < 2:
            reply = "Please say both the first and last name."
        else:
            st.update(stage="identify_dob", first=parts[0], last=parts[-1])
            reply = "Thank you. And the date of birth?"
    elif stage == "identify_dob":
        dob = _parse_dob(text)
        if not dob:
            reply = "Please say the date of birth as month, day and year — for example 04/12/1986."
        else:
            matches = db.scalars(select(Patient).where(Patient.organization_id == call.organization_id, Patient.status == "active",
                                                       func.lower(Patient.first_name) == st["first"].lower(),
                                                       func.lower(Patient.last_name) == st["last"].lower(), Patient.date_of_birth == dob)).all()
            if len(matches) == 1 and not matches[0].is_restricted:
                call.verified_patient_id = matches[0].id
                st["stage"] = "menu"
                pending = st.pop("pending_intent", None)
                call.state = st
                reply = f"Thanks, {matches[0].first_name}, you're verified. " + (_handle_intent(db, call, pending) if pending else "How can I help?")
                st = dict(call.state)
            else:
                st["attempts"] = st.get("attempts", 0) + 1
                if st["attempts"] >= 3:
                    call.state = st
                    reply = _transfer(db, call, "Caller identity could not be verified")
                    st = dict(call.state)
                else:
                    st["stage"] = "identify_name"
                    # Same response whether or not the name exists, so callers can't probe records.
                    reply = "I'm sorry, I couldn't verify those details. Let's try again — please tell me the patient's first and last name."
    elif stage == "book_pick":
        offers = st.get("offers", [])
        i = _pick(text, len(offers))
        if i is None:
            reply = "Please choose option 1, 2 or 3, or say 'staff' to speak with someone."
        else:
            o = offers[i]
            p = _verified(db, call)
            s, e = datetime.fromisoformat(o["start"]), datetime.fromisoformat(o["end"])
            clash = db.scalar(select(Appointment.id).where(Appointment.provider_id == uuid.UUID(o["provider_id"]),
                                                           Appointment.status.not_in(INACTIVE_APPOINTMENT_STATUSES), Appointment.start_at < e, Appointment.end_at > s))
            if clash:
                reply = "Sorry, that time was just taken. " + _offer_slots(db, call, p)
                st = dict(call.state)
            else:
                a = Appointment(organization_id=call.organization_id, clinic_id=uuid.UUID(o["clinic_id"]), patient_id=p.id,
                                provider_id=uuid.UUID(o["provider_id"]), appointment_type_id=uuid.UUID(o["type_id"]), start_at=s, end_at=e,
                                reason="Booked by phone (AI receptionist)", booked_via="ai_phone")
                db.add(a)
                db.flush()
                st["stage"] = "menu"
                call.outcome = f"Booked appointment {s:%b %d %I:%M %p}"
                reply = f"You're booked for {s:%A %B %-d at %-I:%M %p}. You'll see it in your patient portal. Anything else?"
    elif stage == "cancel_pick":
        ids = st.get("appts", [])
        i = _pick(text, len(ids))
        if i is None:
            reply = "Which appointment — option 1, 2 or 3?"
        else:
            a = db.get(Appointment, uuid.UUID(ids[i]))
            if a and a.patient_id == call.verified_patient_id and a.status in ("scheduled", "confirmed"):
                a.status, a.cancel_reason = "cancelled", "Cancelled by phone (AI receptionist)"
                call.outcome = f"Cancelled appointment {a.start_at:%b %d}"
                reply = "That appointment is cancelled. Would you like to book a new one?"
            else:
                reply = "I couldn't cancel that one; I'll have our staff follow up."
                _transfer(db, call, "Cancellation needs staff review")
            st["stage"] = "menu"
    else:  # menu
        intent = _intent(text)
        if intent is None and YES.search(text) and call.intent == "list":
            intent = "book"
        if intent is None:
            reply = "I can help with booking, cancelling, your upcoming appointments, or our hours and location. What would you like to do?"
        else:
            call.state = st
            reply = _handle_intent(db, call, intent)
            st = dict(call.state)
    if call.status == "active":
        call.state = st
    _say(call, "assistant", reply)
    if call.status != "active":
        finish(db, call)
    return reply


def finish(db: Session, call: VoiceCall) -> None:
    if call.status == "active":
        call.status = "completed"
    p = _verified(db, call)
    who = f"{p.full_name} (identity verified)" if p else "Unverified caller"
    call.summary = f"{who}{f' from {call.from_number}' if call.from_number else ''}. Intent: {call.intent or 'general'}. Outcome: {call.outcome or 'no action taken'}. Turns: {sum(1 for t in call.transcript if t['speaker'] == 'caller')}."
    call.ended_at = now()
