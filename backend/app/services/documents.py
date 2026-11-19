"""Document intake pipeline: validate → store → extract text → AI analysis → patient-match suggestions → review queue.

Documents are never attached to a chart automatically; filing always requires a human with documents:review.
"""

import hashlib
import io
import logging
import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.provider import AIError, get_provider
from app.core.config import settings
from app.core.security import now
from app.models import AIJob, Document, Patient
from app.services.storage import storage

log = logging.getLogger("undeclared.documents")

ALLOWED = {
    b"%PDF": "application/pdf",
    b"\x89PNG": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"II*\x00": "image/tiff",
    b"MM\x00*": "image/tiff",
}


def sniff_type(data: bytes) -> str | None:
    """Trust the bytes, not the client-supplied Content-Type or extension."""
    for magic, ctype in ALLOWED.items():
        if data.startswith(magic):
            return ctype
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_upload(data: bytes) -> str:
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"Files must be {settings.max_upload_mb} MB or smaller.")
    ctype = sniff_type(data)
    if not ctype:
        raise ValueError("Unsupported file type. Upload a PDF, PNG, JPEG, TIFF or WebP.")
    return ctype


def create_document(db: Session, *, org_id: uuid.UUID, data: bytes, filename: str, source: str,
                    uploaded_by_id: uuid.UUID | None, clinic_id: uuid.UUID | None = None,
                    patient_hint_id: uuid.UUID | None = None, sender: str | None = None) -> tuple[Document, AIJob]:
    ctype = validate_upload(data)
    digest = hashlib.sha256(data).hexdigest()
    doc_id = uuid.uuid4()
    key = f"{org_id}/documents/{doc_id}/{digest}"  # no filenames/PHI in object keys
    storage.put(key, data, ctype)
    doc = Document(
        id=doc_id, organization_id=org_id, clinic_id=clinic_id, source=source, status="processing",
        filename=(filename or "document")[:255], content_type=ctype, size_bytes=len(data), sha256=digest, storage_key=key,
        uploaded_by_id=uploaded_by_id, sender=sender, suggested_patient_id=patient_hint_id,
    )
    db.add(doc)
    job = AIJob(organization_id=org_id, kind="document_analysis", provider=settings.ai_provider, subject_type="document",
                subject_id=doc_id, created_by_id=uploaded_by_id)
    db.add(job)
    db.flush()
    return doc, job


def extract_text(data: bytes, content_type: str) -> tuple[str | None, str, int | None]:
    if content_type == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            pages = [p.extract_text() or "" for p in reader.pages]
            text = "\n".join(pages).strip()
            return (text or None), ("pdf_text" if text else "none"), len(reader.pages)
        except Exception:  # noqa: BLE001 - corrupt PDFs are reported, not raised
            log.warning("pdf text extraction failed")
            return None, "none", None
    return None, "none", 1


def _sim(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return 1.0
    # character bigram Dice coefficient — cheap and deterministic
    ga = {a[i:i + 2] for i in range(len(a) - 1)}
    gb = {b[i:i + 2] for i in range(len(b) - 1)}
    return 2 * len(ga & gb) / (len(ga) + len(gb)) if ga and gb else 0.0


def match_patients(db: Session, org_id: uuid.UUID, first: str | None, last: str | None, dob: str | None,
                   mrn: str | None) -> list[dict]:
    """Rule-based candidate scoring. Returns up to 3 candidates with score 0..1 and human-readable reasons."""
    dob_d = None
    if dob:
        try:
            dob_d = date.fromisoformat(dob)
        except ValueError:
            dob_d = None
    conds = []
    if mrn:
        conds.append(Patient.mrn == mrn.upper())
    if dob_d:
        conds.append(Patient.date_of_birth == dob_d)
    if first or last:
        full = f"{first or ''} {last or ''}".strip().lower()
        conds.append(func.similarity(func.lower(Patient.first_name + " " + Patient.last_name), full) > 0.35)
    if not conds:
        return []
    pool = db.scalars(select(Patient).where(Patient.organization_id == org_id, or_(*conds)).limit(50)).all()
    out = []
    for p in pool:
        score, reasons = 0.0, []
        if mrn and p.mrn == mrn.upper():
            score += 0.45
            reasons.append("MRN matches")
        if dob_d and p.date_of_birth == dob_d:
            score += 0.35
            reasons.append("date of birth matches")
        ls, fs = _sim(last, p.last_name), _sim(first, p.first_name)
        if ls == 1.0:
            score += 0.15
            reasons.append("last name matches")
        elif ls >= 0.6:
            score += 0.08
            reasons.append("last name similar")
        if fs == 1.0:
            score += 0.05
            reasons.append("first name matches")
        elif fs >= 0.6:
            score += 0.03
            reasons.append("first name similar")
        if mrn and p.mrn != mrn.upper() and mrn.upper().startswith("UD"):
            reasons.append("MRN on document differs")
            score -= 0.1
        if dob_d and p.date_of_birth != dob_d:
            reasons.append("date of birth differs")
            score -= 0.15
        if score > 0.2:
            out.append({"patient_id": str(p.id), "name": p.full_name, "mrn": p.mrn, "date_of_birth": p.date_of_birth.isoformat(),
                        "score": round(max(0.0, min(score, 1.0)), 2), "reasons": reasons})
    return sorted(out, key=lambda c: -c["score"])[:3]


def suggestion_from(candidates: list[dict]) -> uuid.UUID | None:
    """Only suggest when the top candidate is strong AND clearly ahead; otherwise leave it to the reviewer."""
    if not candidates or candidates[0]["score"] < 0.6:
        return None
    if len(candidates) > 1 and candidates[0]["score"] - candidates[1]["score"] < 0.15:
        return None
    return uuid.UUID(candidates[0]["patient_id"])


def process_document(db: Session, doc_id: uuid.UUID) -> None:
    doc = db.get(Document, doc_id)
    if not doc or doc.status not in ("processing", "failed", "needs_review"):
        return
    job = db.scalar(select(AIJob).where(AIJob.subject_id == doc.id, AIJob.status.in_(("queued", "running")))
                    .order_by(AIJob.created_at.desc()))
    if job is None:
        job = AIJob(organization_id=doc.organization_id, kind="document_analysis", provider=settings.ai_provider,
                    subject_type="document", subject_id=doc.id)
        db.add(job)
    job.status = "running"
    doc.status, doc.processing_error = "processing", None
    db.commit()
    hint = doc.suggested_patient_id if doc.source == "upload" and doc.match_candidates is None else None
    try:
        data = storage.get(doc.storage_key)
        text, text_source, pages = extract_text(data, doc.content_type)
        doc.extracted_text, doc.text_source, doc.page_count = text, text_source, pages
        provider = get_provider()
        result = provider.analyze_document(text, data, doc.content_type, contains_phi=True)
        a = result.data
        doc.ai_output = a.model_dump()
        doc.ai_confidence = a.confidence
        doc.doc_type, doc.title, doc.summary = a.doc_type, a.title[:300], a.summary
        try:
            doc.document_date = date.fromisoformat(a.document_date) if a.document_date else None
        except ValueError:
            doc.document_date = None
        doc.sender = doc.sender or (a.sender[:200] if a.sender else None)
        cands = match_patients(db, doc.organization_id, a.patient.first_name, a.patient.last_name, a.patient.date_of_birth, a.patient.mrn)
        if hint:
            # Uploaded from a chart: keep the chosen patient but surface disagreement with the document.
            hp = db.get(Patient, hint)
            if hp and not any(c["patient_id"] == str(hp.id) for c in cands):
                cands.insert(0, {"patient_id": str(hp.id), "name": hp.full_name, "mrn": hp.mrn,
                                 "date_of_birth": hp.date_of_birth.isoformat(), "score": 0.0,
                                 "reasons": ["selected at upload", "document identifiers do not match this patient"]})
            doc.suggested_patient_id = hint
        else:
            doc.suggested_patient_id = suggestion_from(cands)
        doc.match_candidates = cands
        doc.status = "needs_review"
        from app.services.automation import emit

        emit(db, doc.organization_id, "document.needs_review", {
            "subject_type": "document", "subject_id": doc.id, "document_id": str(doc.id), "doc_type": doc.doc_type,
            "confidence": doc.ai_confidence, "patient_id": None})
        job.status, job.model, job.provider = "succeeded", result.model, result.provider
        job.phi_sent_externally = result.phi_sent_externally
        job.input_tokens, job.output_tokens, job.latency_ms = result.input_tokens, result.output_tokens, result.latency_ms
        job.patient_id = doc.suggested_patient_id
    except AIError as e:
        doc.status, doc.processing_error = "failed", str(e)
        job.status, job.error = "failed", str(e)
    except Exception as e:  # noqa: BLE001
        log.exception("document processing failed")
        doc.status, doc.processing_error = "failed", "Processing failed unexpectedly. Try reprocessing."
        job.status, job.error = "failed", type(e).__name__
    job.finished_at = now()
    db.commit()
