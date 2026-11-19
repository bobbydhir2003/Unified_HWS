"""Clinical note lifecycle: draft → (versions) → signed (frozen) → addenda. DB triggers back these rules up."""

from fastapi import HTTPException

from app.api.deps import TenantContext
from app.core.errors import bad_request, forbidden
from app.core.permissions import P
from app.core.security import now
from app.models import ClinicalNote, ClinicalNoteVersion, Encounter, NoteAddendum
from app.schemas.clinical import AddendumOut, NoteContent, NoteOut, UserRef


def user_ref(u) -> UserRef | None:
    return UserRef(id=u.id, name=u.display_name) if u else None


def note_out(n: ClinicalNote) -> NoteOut:
    return NoteOut(
        id=n.id, encounter_id=n.encounter_id, patient_id=n.patient_id, note_type=n.note_type, title=n.title,
        status=n.status, current_version=n.current_version, content=NoteContent(**(n.content or {})),
        has_ai_content=n.has_ai_content, ai_reviewed=n.ai_reviewed, author=user_ref(n.author),
        signed_by=user_ref(n.signed_by), signed_at=n.signed_at, created_at=n.created_at, updated_at=n.updated_at,
        addenda=[AddendumOut(id=a.id, body=a.body, author=user_ref(a.author), created_at=a.created_at) for a in n.addenda],
    )


def save_version(ctx: TenantContext, note: ClinicalNote, content: NoteContent, expected_version: int, source: str) -> None:
    if note.status == "signed":
        raise bad_request("This note is signed. Add an addendum instead.")
    if expected_version != note.current_version:
        raise HTTPException(409, {"code": "version_conflict",
                                  "message": "This note was changed by someone else. Reload to see the latest version.",
                                  "current_version": note.current_version})
    note.current_version += 1
    note.content = content.model_dump()
    if source == "ai_scribe":
        note.has_ai_content = True
        note.ai_reviewed = False
    ctx.db.add(ClinicalNoteVersion(organization_id=ctx.org_id, note_id=note.id, version=note.current_version,
                                   content=note.content, source=source, created_by_id=ctx.user.id))


def sign_note(ctx: TenantContext, note: ClinicalNote, encounter: Encounter, expected_version: int,
              attest_ai_reviewed: bool) -> None:
    ctx.require(P.CLINICAL_SIGN)
    if note.status == "signed":
        raise bad_request("Note is already signed")
    if expected_version != note.current_version:
        raise HTTPException(409, {"code": "version_conflict", "message": "Note changed since you loaded it. Reload and review before signing."})
    if encounter.status == "cancelled":
        raise bad_request("Cannot sign a note on a cancelled encounter")
    c = note.content or {}
    if not (c.get("assessment", "").strip() and c.get("plan", "").strip()):
        raise bad_request("Assessment and Plan are required before signing")
    if note.has_ai_content and not attest_ai_reviewed:
        raise HTTPException(422, {"code": "ai_review_required",
                                  "message": "This note contains AI-generated content. Confirm you reviewed and edited it before signing."})
    if ctx.provider is None:
        raise forbidden("Only clinicians with a provider profile can sign notes")
    ts = now()
    # Final immutable snapshot, then freeze the note.
    ctx.db.add(ClinicalNoteVersion(organization_id=ctx.org_id, note_id=note.id, version=note.current_version + 1,
                                   content=note.content, source="sign", created_by_id=ctx.user.id))
    ctx.db.flush()
    note.current_version += 1
    note.ai_reviewed = note.has_ai_content
    note.status = "signed"
    note.signed_at = ts
    note.signed_by_id = ctx.user.id


def add_addendum(ctx: TenantContext, note: ClinicalNote, body: str) -> NoteAddendum:
    ctx.require(P.CLINICAL_WRITE)
    if note.status != "signed":
        raise bad_request("Addenda can only be added to signed notes; edit the draft instead.")
    a = NoteAddendum(organization_id=ctx.org_id, note_id=note.id, author_id=ctx.user.id, body=body)
    ctx.db.add(a)
    return a
