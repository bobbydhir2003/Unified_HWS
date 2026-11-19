import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import AIError
from app.ai.scribe import Segment, get_drafter, get_transcriber
from app.core.config import settings
from app.core.security import now
from app.models import AIJob, Encounter, ScribeSession, VitalSigns
from app.services.storage import storage

log = logging.getLogger("undeclared.scribe")

AUDIO_MAGIC = {b"\x1aE\xdf\xa3": "audio/webm", b"OggS": "audio/ogg", b"fLaC": "audio/flac", b"ID3": "audio/mpeg"}


def sniff_audio(data: bytes) -> str | None:
    for magic, ctype in AUDIO_MAGIC.items():
        if data.startswith(magic):
            return ctype
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[4:8] == b"ftyp":
        return "audio/mp4"
    return None


def _vitals_text(db: Session, encounter_id: uuid.UUID) -> str | None:
    v = db.scalar(select(VitalSigns).where(VitalSigns.encounter_id == encounter_id).order_by(VitalSigns.measured_at.desc()))
    if not v:
        return None
    parts = []
    if v.systolic:
        parts.append(f"BP {v.systolic}/{v.diastolic}")
    if v.heart_rate:
        parts.append(f"HR {v.heart_rate}")
    if v.respiratory_rate:
        parts.append(f"RR {v.respiratory_rate}")
    if v.temperature_c:
        parts.append(f"T {round(float(v.temperature_c) * 9 / 5 + 32, 1)}°F")
    if v.spo2:
        parts.append(f"SpO2 {v.spo2}%")
    return "Vitals: " + ", ".join(parts) if parts else None


def _job(db: Session, s: ScribeSession, kind: str, provider: str) -> AIJob:
    j = AIJob(organization_id=s.organization_id, kind=kind, provider=provider, subject_type="scribe_session",
              subject_id=s.id, patient_id=s.patient_id, status="running", created_by_id=s.clinician_id)
    db.add(j)
    db.flush()
    return j


def _phi(db: Session, org_id) -> bool:
    from app.ai.policy import contains_phi

    return contains_phi(db, org_id)


def transcribe(db: Session, session_id: uuid.UUID) -> None:
    s = db.get(ScribeSession, session_id)
    if not s or s.status != "transcribing" or not s.audio_storage_key:
        return
    t = get_transcriber()
    job = _job(db, s, "scribe_transcription", t.name)
    try:
        audio = storage.get(s.audio_storage_key)
        segs = (t.transcribe(audio, s.audio_content_type or "", contains_phi=_phi(db, s.organization_id)) if t.name == "openai"
                else t.transcribe(audio, s.audio_content_type or ""))
        s.transcript = [x.model_dump() for x in segs]
        s.transcript_source, s.status, job.status = "audio", "transcribed", "succeeded"
        if not settings.scribe_retain_audio:
            storage.delete(s.audio_storage_key)
            s.audio_deleted_at = now()
    except AIError as e:
        s.status, s.error, job.status, job.error = "failed", str(e), "failed", str(e)
    job.finished_at = now()
    db.commit()


def draft(db: Session, session_id: uuid.UUID) -> None:
    s = db.get(ScribeSession, session_id)
    if not s or s.status != "drafting" or not s.transcript:
        return
    enc = db.get(Encounter, s.encounter_id)
    d = get_drafter()
    job = _job(db, s, "scribe_note", d.name)
    try:
        r = d.draft([Segment(**x) for x in s.transcript], _vitals_text(db, s.encounter_id), enc.chief_complaint,
                    contains_phi=_phi(db, s.organization_id))
        s.draft = {**r.draft.model_dump(), "provider": r.provider, "model": r.model}
        s.draft_count += 1
        s.status, s.error = "ready", None
        job.status, job.model, job.phi_sent_externally = "succeeded", r.model, r.phi_sent_externally
        job.input_tokens, job.output_tokens, job.latency_ms = r.input_tokens, r.output_tokens, r.latency_ms
        job.cost_usd = getattr(r, "cost_usd", None)
    except AIError as e:
        s.status, s.error, job.status, job.error = "failed", str(e), "failed", str(e)
    except Exception as e:  # noqa: BLE001
        log.exception("scribe draft failed")
        s.status, s.error, job.status, job.error = "failed", "Drafting failed unexpectedly.", "failed", type(e).__name__
    job.finished_at = now()
    db.commit()
