import hmac
import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.ai.config import active_provider
from app.api.deps import TenantContext, get_ctx, require
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import bad_request, forbidden, not_found
from app.core.permissions import P
from app.core.security import now
from app.models import AIJob, Document, Organization, Patient, User
from app.models.documents import DOCUMENT_TYPES
from app.schemas.common import ORM, Message, Page
from app.services import audit
from app.services.documents import create_document
from app.services.patients import get_patient
from app.services.sample_docs import make_sample
from app.services.storage import storage

router = APIRouter(tags=["documents"])


class DocumentOut(ORM):
    id: uuid.UUID
    source: str
    status: str
    filename: str
    content_type: str
    size_bytes: int
    page_count: int | None
    sender: str | None
    patient_id: uuid.UUID | None
    patient_name: str | None = None
    doc_type: str | None
    title: str | None
    document_date: date | None
    summary: str | None
    ai_confidence: float | None
    suggested_patient_id: uuid.UUID | None
    processing_error: str | None
    uploaded_by_name: str | None = None
    reviewed_at: datetime | None
    reject_reason: str | None
    created_at: datetime


class DocumentDetail(DocumentOut):
    ai_output: dict | None
    match_candidates: list | None
    text_source: str | None
    extracted_text: str | None
    ai_provider: str | None = None
    ai_model: str | None = None
    duplicate_of: uuid.UUID | None = None


class DocumentUpdate(BaseModel):
    doc_type: Literal[DOCUMENT_TYPES] | None = None  # type: ignore[valid-type]
    title: str | None = Field(default=None, max_length=300)
    document_date: date | None = None
    summary: str | None = Field(default=None, max_length=5000)


class FileToChart(BaseModel):
    patient_id: uuid.UUID
    doc_type: Literal[DOCUMENT_TYPES]  # type: ignore[valid-type]
    title: str = Field(min_length=1, max_length=300)
    document_date: date | None = None
    summary: str | None = Field(default=None, max_length=5000)
    identity_confirmed: bool


class RejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class SampleIn(BaseModel):
    kind: Literal["lab_result", "imaging_report", "discharge_summary", "referral"] = "lab_result"
    fidelity: Literal["exact", "ambiguous", "unknown"] = "exact"
    patient_id: uuid.UUID | None = None
    source: Literal["sample", "fax"] = "sample"


def _names(ctx: TenantContext, docs: list[Document]) -> tuple[dict, dict]:
    pids = {d.patient_id for d in docs if d.patient_id}
    uids = {d.uploaded_by_id for d in docs if d.uploaded_by_id}
    pn = dict(ctx.db.execute(select(Patient.id, Patient.first_name + " " + Patient.last_name).where(Patient.id.in_(pids))).all())
    un = dict(ctx.db.execute(select(User.id, User.first_name + " " + User.last_name).where(User.id.in_(uids))).all())
    return pn, un


def _out(ctx: TenantContext, docs: list[Document]) -> list[DocumentOut]:
    pn, un = _names(ctx, docs)
    res = []
    for d in docs:
        o = DocumentOut.model_validate(d)
        o.patient_name, o.uploaded_by_name = pn.get(d.patient_id), un.get(d.uploaded_by_id)
        res.append(o)
    return res


def _get(ctx: TenantContext, doc_id: uuid.UUID) -> Document:
    d = ctx.db.get(Document, doc_id)
    if not d or d.organization_id != ctx.org_id:
        raise not_found("Document")
    if d.patient_id:  # filed documents inherit the patient's access rules (restricted charts, portal scoping)
        get_patient(ctx, d.patient_id)
    return d


def _detail(ctx: TenantContext, d: Document) -> DocumentDetail:
    base = _out(ctx, [d])[0]
    job = ctx.db.scalar(select(AIJob).where(AIJob.subject_id == d.id).order_by(AIJob.created_at.desc()))
    dup = ctx.db.scalar(select(Document.id).where(Document.organization_id == ctx.org_id, Document.sha256 == d.sha256,
                                                  Document.id != d.id, Document.status != "rejected"))
    return DocumentDetail(**base.model_dump(), ai_output=d.ai_output, match_candidates=d.match_candidates,
                          text_source=d.text_source, extracted_text=d.extracted_text,
                          ai_provider=job.provider if job else None, ai_model=job.model if job else None, duplicate_of=dup)


def _enqueue(doc_id: uuid.UUID) -> None:
    from app.tasks import process_document_task

    process_document_task.delay(str(doc_id))


@router.post("/documents", response_model=DocumentDetail, status_code=201)
async def upload_document(
    file: UploadFile = File(...), patient_id: uuid.UUID | None = Form(None), source: Literal["upload", "scan"] = Form("upload"),
    ctx: TenantContext = Depends(require(P.DOCUMENTS_WRITE)),
):
    if patient_id:
        get_patient(ctx, patient_id)
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        doc, _ = create_document(ctx.db, org_id=ctx.org_id, data=data, filename=file.filename or "upload", source=source,
                                 uploaded_by_id=ctx.user.id, patient_hint_id=patient_id,
                                 clinic_id=ctx.clinic_ids[0] if ctx.clinic_ids else None)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    ctx.audit("document.uploaded", resource_type="document", resource_id=doc.id, patient_id=patient_id,
              details={"content_type": doc.content_type, "size": doc.size_bytes})
    ctx.db.commit()
    _enqueue(doc.id)
    ctx.db.refresh(doc)
    return _detail(ctx, doc)


@router.post("/documents/samples", response_model=DocumentDetail, status_code=201)
def create_sample(body: SampleIn, ctx: TenantContext = Depends(require(P.DOCUMENTS_WRITE))):
    org = ctx.db.get(Organization, ctx.org_id)
    if not (org.settings or {}).get("synthetic_data"):
        raise forbidden("Synthetic samples are only available in organizations flagged as synthetic.")
    patient = get_patient(ctx, body.patient_id) if body.patient_id else ctx.db.scalar(
        select(Patient).where(Patient.organization_id == ctx.org_id, Patient.status == "active", Patient.is_restricted.is_(False))
        .order_by(func.random()))
    pdf, filename, facility = make_sample(body.kind, patient, body.fidelity)
    doc, _ = create_document(ctx.db, org_id=ctx.org_id, data=pdf, filename=filename, source=body.source,
                             uploaded_by_id=ctx.user.id, sender=f"Fax (555) 010-{1000 + len(facility)}" if body.source == "fax" else facility)
    ctx.audit("document.sample_created", resource_type="document", resource_id=doc.id, details={"kind": body.kind, "fidelity": body.fidelity})
    ctx.db.commit()
    _enqueue(doc.id)
    ctx.db.refresh(doc)
    return _detail(ctx, doc)


@router.get("/documents", response_model=Page[DocumentOut])
def list_documents(
    status: str | None = None, doc_type: str | None = None, q: str | None = None, source: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), ctx: TenantContext = Depends(require(P.DOCUMENTS_READ)),
):
    stmt = select(Document).where(Document.organization_id == ctx.org_id)
    if status:
        stmt = stmt.where(Document.status.in_(status.split(",")))
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if source:
        stmt = stmt.where(Document.source == source)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.outerjoin(Patient, Patient.id == Document.patient_id).where(or_(
            func.lower(Document.title).like(like), func.lower(Document.filename).like(like),
            func.lower(Document.summary).like(like), func.lower(Patient.first_name + " " + Patient.last_name).like(like)))
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=_out(ctx, rows), total=total, page=page, page_size=page_size)


@router.get("/documents/counts")
def document_counts(ctx: TenantContext = Depends(require(P.DOCUMENTS_READ))):
    rows = ctx.db.execute(select(Document.status, func.count()).where(Document.organization_id == ctx.org_id)
                          .group_by(Document.status)).all()
    return dict(rows)


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: uuid.UUID, ctx: TenantContext = Depends(require(P.DOCUMENTS_READ))):
    return _detail(ctx, _get(ctx, doc_id))


@router.get("/documents/{doc_id}/file")
def download_document(doc_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    d = ctx.db.get(Document, doc_id)
    if not d or d.organization_id != ctx.org_id:
        raise not_found("Document")
    if ctx.is_patient_only:
        if not d.patient_id or d.status != "filed":
            raise not_found("Document")
        get_patient(ctx, d.patient_id)
    else:
        ctx.require(P.DOCUMENTS_READ)
        _get(ctx, doc_id)
    data = storage.get(d.storage_key)
    ctx.audit("document.viewed", resource_type="document", resource_id=d.id, patient_id=d.patient_id)
    ctx.db.commit()
    return Response(content=data, media_type=d.content_type, headers={
        "Content-Disposition": f'inline; filename="document-{d.id}"', "Cache-Control": "no-store",
        "Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"})


@router.patch("/documents/{doc_id}", response_model=DocumentDetail)
def update_document(doc_id: uuid.UUID, body: DocumentUpdate, ctx: TenantContext = Depends(require(P.DOCUMENTS_WRITE))):
    d = _get(ctx, doc_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(d, k, v)
    ctx.audit("document.corrected", resource_type="document", resource_id=d.id, patient_id=d.patient_id,
              details={"fields": sorted(body.model_fields_set)})
    ctx.db.commit()
    return _detail(ctx, d)


@router.post("/documents/{doc_id}/file", response_model=DocumentDetail)
def file_to_chart(doc_id: uuid.UUID, body: FileToChart, ctx: TenantContext = Depends(require(P.DOCUMENTS_REVIEW))):
    d = _get(ctx, doc_id)
    if d.status != "needs_review":
        raise bad_request(f"Only documents awaiting review can be filed (this one is {d.status.replace('_', ' ')}).")
    if not body.identity_confirmed:
        raise HTTPException(422, {"code": "identity_not_confirmed",
                                  "message": "Confirm that the patient identifiers on the document match the selected patient."})
    p = get_patient(ctx, body.patient_id, P.PATIENTS_READ)
    d.patient_id, d.doc_type, d.title, d.document_date = p.id, body.doc_type, body.title, body.document_date
    if body.summary is not None:
        d.summary = body.summary
    d.status, d.reviewed_by_id, d.reviewed_at = "filed", ctx.user.id, now()
    ctx.audit("document.filed", resource_type="document", resource_id=d.id, patient_id=p.id, details={
        "doc_type": body.doc_type, "matched_suggestion": d.suggested_patient_id == p.id,
        "ai_confidence": d.ai_confidence})
    ctx.db.commit()
    return _detail(ctx, d)


@router.post("/documents/{doc_id}/reject", response_model=DocumentDetail)
def reject_document(doc_id: uuid.UUID, body: RejectIn, ctx: TenantContext = Depends(require(P.DOCUMENTS_REVIEW))):
    d = _get(ctx, doc_id)
    if d.status == "filed":
        raise bad_request("Filed documents can't be rejected")
    d.status, d.reject_reason, d.reviewed_by_id, d.reviewed_at = "rejected", body.reason, ctx.user.id, now()
    ctx.audit("document.rejected", resource_type="document", resource_id=d.id)
    ctx.db.commit()
    return _detail(ctx, d)


@router.post("/documents/{doc_id}/reprocess", response_model=DocumentDetail)
def reprocess(doc_id: uuid.UUID, ctx: TenantContext = Depends(require(P.DOCUMENTS_WRITE))):
    d = _get(ctx, doc_id)
    if d.status not in ("failed", "needs_review"):
        raise bad_request("Only failed or unreviewed documents can be reprocessed")
    d.status = "processing"
    ctx.db.add(AIJob(organization_id=ctx.org_id, kind="document_analysis", provider=active_provider(),
                     subject_type="document", subject_id=d.id, created_by_id=ctx.user.id))
    ctx.audit("document.reprocessed", resource_type="document", resource_id=d.id)
    ctx.db.commit()
    _enqueue(d.id)
    ctx.db.refresh(d)
    return _detail(ctx, d)


@router.get("/patients/{patient_id}/documents", response_model=list[DocumentOut])
def patient_documents(patient_id: uuid.UUID, ctx: TenantContext = Depends(get_ctx)):
    p = get_patient(ctx, patient_id)
    if not ctx.is_patient_only:
        ctx.require(P.DOCUMENTS_READ)
    rows = ctx.db.scalars(select(Document).where(Document.patient_id == p.id, Document.status == "filed")
                          .order_by(Document.document_date.desc().nulls_last(), Document.created_at.desc())).all()
    return _out(ctx, rows)


# ---------- Inbound fax webhook (integration architecture; any fax vendor posting multipart works) ----------

@router.post("/integrations/fax/{org_slug}/inbound", response_model=Message, status_code=202)
async def inbound_fax(org_slug: str, file: UploadFile = File(...), from_number: str = Form(""),
                      x_fax_secret: str | None = Header(default=None), db=Depends(get_db)):
    org = db.scalar(select(Organization).where(Organization.slug == org_slug))
    secret = (org.settings or {}).get("fax_webhook_secret") if org else None
    if not org or not secret or not x_fax_secret or not hmac.compare_digest(secret, x_fax_secret):
        raise HTTPException(401, "Invalid fax webhook credentials")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    try:
        doc, _ = create_document(db, org_id=org.id, data=data, filename=file.filename or "fax.pdf", source="fax",
                                 uploaded_by_id=None, sender=from_number[:200] or None)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    audit.record(db, "document.fax_received", org_id=org.id, resource_type="document", resource_id=doc.id)
    db.commit()
    _enqueue(doc.id)
    return Message(message="accepted")
