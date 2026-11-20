import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ai.scribe import demo_transcript
from app.api.deps import TenantContext, require
from app.core.config import settings
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import ClinicalNote, Encounter, Organization, ScribeSession
from app.schemas.clinical import NoteContent
from app.services.notes import save_version
from app.services.patients import get_patient
from app.services.scribe import sniff_audio
from app.services.storage import storage

router = APIRouter(tags=["scribe"])
SCRIBE_PERMS = (P.AI_USE, P.CLINICAL_WRITE)


class StartIn(BaseModel):
    consent_method: Literal["verbal", "written"]
    consent_confirmed: bool


class SegmentIn(BaseModel):
    speaker: Literal["clinician", "patient", "other"]
    text: str = Field(min_length=1, max_length=4000)


class TranscriptIn(BaseModel):
    segments: list[SegmentIn] = Field(min_length=1, max_length=500)


class ApplyIn(BaseModel):
    mode: Literal["replace", "append"] = "replace"
    expected_version: int | None = None  # current note version (None when no note exists yet)
    sections: NoteContent | None = None  # clinician-edited draft; defaults to the AI draft


class ScribeOut(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    status: str
    consent_method: str
    consent_recorded_at: datetime
    transcript_source: str | None
    audio_seconds: int | None
    audio_deleted_at: datetime | None
    transcript: list | None
    transcript_edited: bool
    draft: dict | None
    draft_count: int
    applied_note_version: int | None
    error: str | None
    created_at: datetime


def _encounter(ctx: TenantContext, encounter_id: uuid.UUID) -> Encounter:
    e = ctx.db.get(Encounter, encounter_id)
    if not e or e.organization_id != ctx.org_id:
        raise not_found("Encounter")
    get_patient(ctx, e.patient_id, P.CLINICAL_WRITE)
    ctx.require_clinic(e.clinic_id)
    return e


def _session(ctx: TenantContext, sid: uuid.UUID) -> tuple[ScribeSession, Encounter]:
    s = ctx.db.get(ScribeSession, sid)
    if not s or s.organization_id != ctx.org_id:
        raise not_found("Scribe session")
    e = _encounter(ctx, s.encounter_id)
    if s.status in ("applied", "discarded"):
        raise bad_request(f"This scribe session is {s.status}.")
    return s, e


def _out(s: ScribeSession) -> ScribeOut:
    return ScribeOut.model_validate(s, from_attributes=True)


def _queue_draft(s: ScribeSession) -> None:
    from app.ai.demo_scope import current_token as ai_scope_token
    from app.tasks import scribe_draft_task

    scribe_draft_task.delay(str(s.id), ai_scope=ai_scope_token())


@router.get("/encounters/{encounter_id}/scribe", response_model=ScribeOut | None)
def current_session(encounter_id: uuid.UUID, ctx: TenantContext = Depends(require(*SCRIBE_PERMS))):
    e = _encounter(ctx, encounter_id)
    s = ctx.db.scalar(select(ScribeSession).where(ScribeSession.encounter_id == e.id, ScribeSession.status != "discarded")
                      .order_by(ScribeSession.created_at.desc()))
    return _out(s) if s else None


@router.post("/encounters/{encounter_id}/scribe", response_model=ScribeOut, status_code=201)
def start_session(encounter_id: uuid.UUID, body: StartIn, ctx: TenantContext = Depends(require(*SCRIBE_PERMS))):
    e = _encounter(ctx, encounter_id)
    if e.status != "in_progress":
        raise bad_request("The scribe can only be used during an open visit")
    if not body.consent_confirmed:
        raise HTTPException(422, {"code": "consent_required", "message": "Patient consent to AI-assisted documentation is required."})
    active = ctx.db.scalar(select(ScribeSession).where(ScribeSession.encounter_id == e.id,
                                                       ScribeSession.status.not_in(("applied", "discarded", "failed"))))
    if active:
        raise bad_request("A scribe session is already active for this visit")
    s = ScribeSession(organization_id=ctx.org_id, encounter_id=e.id, patient_id=e.patient_id, clinician_id=ctx.user.id,
                      consent_method=body.consent_method, status="recording")
    ctx.db.add(s)
    ctx.db.flush()
    ctx.audit("scribe.consent_recorded", resource_type="scribe_session", resource_id=s.id, patient_id=e.patient_id,
              details={"method": body.consent_method})
    ctx.db.commit()
    return _out(s)


@router.post("/scribe/{sid}/audio", response_model=ScribeOut)
async def upload_audio(sid: uuid.UUID, file: UploadFile = File(...), seconds: int = Form(0),
                       ctx: TenantContext = Depends(require(*SCRIBE_PERMS))):
    s, _ = _session(ctx, sid)
    if s.status not in ("recording", "failed"):
        raise bad_request("Audio can only be added before transcription")
    data = await file.read(settings.max_upload_mb * 4 * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 4 * 1024 * 1024:
        raise HTTPException(422, "Recording is too large")
    ctype = sniff_audio(data)
    if not ctype:
        raise HTTPException(422, "Unsupported audio format")
    s.audio_storage_key = f"{ctx.org_id}/scribe/{s.id}/audio"
    storage.put(s.audio_storage_key, data, ctype)
    s.audio_content_type, s.audio_seconds, s.status, s.error = ctype, max(0, seconds), "transcribing", None
    ctx.audit("scribe.audio_uploaded", resource_type="scribe_session", resource_id=s.id, patient_id=s.patient_id,
              details={"seconds": seconds})
    ctx.db.commit()
    from app.ai.demo_scope import current_token as ai_scope_token
    from app.tasks import scribe_transcribe_task

    scribe_transcribe_task.delay(str(s.id), ai_scope=ai_scope_token())
    ctx.db.refresh(s)
    return _out(s)


@router.post("/scribe/{sid}/transcript", response_model=ScribeOut)
def set_transcript(sid: uuid.UUID, body: TranscriptIn, ctx: TenantContext = Depends(require(*SCRIBE_PERMS))):
    """Typed/pasted conversation, or clinician corrections to a transcript. Triggers a fresh draft."""
    s, _ = _session(ctx, sid)
    if s.status in ("transcribing", "drafting"):
        raise bad_request("Wait for processing to finish")
    s.transcript_edited = s.transcript is not None
    s.transcript = [x.model_dump() for x in body.segments]
    s.transcript_source = s.transcript_source or "manual"
    s.status, s.error = "drafting", None
    ctx.audit("scribe.transcript_saved", resource_type="scribe_session", resource_id=s.id, patient_id=s.patient_id,
              details={"segments": len(body.segments), "edited": s.transcript_edited})
    ctx.db.commit()
    _queue_draft(s)
    ctx.db.refresh(s)
    return _out(s)


@router.post("/scribe/{sid}/demo", response_model=ScribeOut)
def use_demo(sid: uuid.UUID, ctx: TenantContext = Depends(require(*SCRIBE_PERMS))):
    s, e = _session(ctx, sid)
    org = ctx.db.get(Organization, ctx.org_id)
    if not (org.settings or {}).get("synthetic_data"):
        raise forbidden("The synthetic demo conversation is only available in synthetic test organizations.")
    s.transcript = [x.model_dump() for x in demo_transcript(e.chief_complaint, ctx.user.last_name)]
    s.transcript_source, s.status, s.error = "synthetic_demo", "drafting", None
    ctx.audit("scribe.demo_transcript", resource_type="scribe_session", resource_id=s.id, patient_id=s.patient_id)
    ctx.db.commit()
    _queue_draft(s)
    ctx.db.refresh(s)
    return _out(s)


@router.post("/scribe/{sid}/regenerate", response_model=ScribeOut)
def regenerate(sid: uuid.UUID, ctx: TenantContext = Depends(require(*SCRIBE_PERMS))):
    s, _ = _session(ctx, sid)
    if not s.transcript or s.status in ("transcribing", "drafting"):
        raise bad_request("Nothing to regenerate yet")
    s.status = "drafting"
    ctx.db.commit()
    _queue_draft(s)
    ctx.db.refresh(s)
    return _out(s)


@router.post("/scribe/{sid}/apply", response_model=ScribeOut)
def apply_draft(sid: uuid.UUID, body: ApplyIn, ctx: TenantContext = Depends(require(*SCRIBE_PERMS))):
    s, e = _session(ctx, sid)
    if s.status != "ready" or not s.draft:
        raise bad_request("The draft isn't ready")
    if e.status != "in_progress":
        raise bad_request("Encounter is closed")
    sections = body.sections or NoteContent(**{k: s.draft[k] for k in ("subjective", "objective", "assessment", "plan")})
    note = ctx.db.scalar(select(ClinicalNote).where(ClinicalNote.encounter_id == e.id).order_by(ClinicalNote.created_at.desc()))
    if note is None:
        note = ClinicalNote(organization_id=ctx.org_id, encounter_id=e.id, patient_id=e.patient_id, author_id=ctx.user.id,
                            title="Progress note", content={}, current_version=0)
        ctx.db.add(note)
        ctx.db.flush()
        expected = 0
    else:
        if note.status == "signed":
            raise bad_request("The visit note is already signed; add an addendum instead.")
        expected = body.expected_version if body.expected_version is not None else -1
    if body.mode == "append" and note.content:
        cur = NoteContent(**note.content)
        sections = NoteContent(**{k: "\n\n".join(filter(None, [getattr(cur, k), getattr(sections, k)])) for k in NoteContent.model_fields})
    save_version(ctx, note, sections, expected, "ai_scribe")  # marks has_ai_content; signing then requires attestation
    if s.draft.get("chief_complaint") and not e.chief_complaint:
        e.chief_complaint = s.draft["chief_complaint"][:300]
    if s.draft.get("follow_up") and not e.follow_up:
        e.follow_up = s.draft["follow_up"][:300]
    s.status, s.applied_note_version = "applied", note.current_version
    ctx.audit("scribe.draft_applied", resource_type="note", resource_id=note.id, patient_id=e.patient_id,
              details={"mode": body.mode, "version": note.current_version, "provider": s.draft.get("provider")})
    ctx.db.commit()
    return _out(s)


@router.post("/scribe/{sid}/discard", response_model=ScribeOut)
def discard(sid: uuid.UUID, ctx: TenantContext = Depends(require(*SCRIBE_PERMS))):
    s, _ = _session(ctx, sid)
    if s.audio_storage_key and not s.audio_deleted_at:
        storage.delete(s.audio_storage_key)
        s.audio_deleted_at = now()
    s.status = "discarded"
    ctx.audit("scribe.discarded", resource_type="scribe_session", resource_id=s.id, patient_id=s.patient_id)
    ctx.db.commit()
    return _out(s)
