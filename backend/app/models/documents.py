import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, OrgScoped, Timestamps, UUIDPk, fk

DOCUMENT_STATUSES = ("processing", "needs_review", "filed", "rejected", "failed")
DOCUMENT_TYPES = (
    "lab_result", "imaging_report", "referral", "consult_note", "discharge_summary", "insurance_card",
    "id_card", "prescription", "intake_form", "correspondence", "other",
)


class Document(UUIDPk, Timestamps, OrgScoped, Base):
    """Uploaded/received clinical document. Bytes live in object storage; never auto-filed to a chart."""

    __tablename__ = "documents"
    clinic_id: Mapped[uuid.UUID | None] = fk("clinics.id", nullable=True, ondelete="SET NULL")
    source: Mapped[str] = mapped_column(String(20), default="upload")  # upload | fax | scan | portal | sample
    status: Mapped[str] = mapped_column(String(20), default="processing")
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300))
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    sender: Mapped[str | None] = mapped_column(String(200))  # fax number / sending facility

    # Final (human-confirmed) metadata
    patient_id: Mapped[uuid.UUID | None] = fk("patients.id", nullable=True, ondelete="SET NULL")
    doc_type: Mapped[str | None] = mapped_column(String(30))
    title: Mapped[str | None] = mapped_column(String(300))
    document_date: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)

    # AI output (draft; shown with confidence until a human confirms)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    text_source: Mapped[str | None] = mapped_column(String(20))  # pdf_text | ocr | none
    ai_output: Mapped[dict | None] = mapped_column(JSONB)
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    suggested_patient_id: Mapped[uuid.UUID | None] = fk("patients.id", nullable=True, ondelete="SET NULL")
    match_candidates: Mapped[list | None] = mapped_column(JSONB)
    processing_error: Mapped[str | None] = mapped_column(Text)

    reviewed_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        CheckConstraint("status in (" + ",".join(f"'{s}'" for s in DOCUMENT_STATUSES) + ")", name="status"),
        CheckConstraint("doc_type is null or doc_type in (" + ",".join(f"'{s}'" for s in DOCUMENT_TYPES) + ")", name="doc_type"),
        CheckConstraint("status <> 'filed' or patient_id is not null", name="filed_has_patient"),
        Index("ix_documents_org_status", "organization_id", "status", "created_at"),
        Index("ix_documents_org_sha", "organization_id", "sha256"),
    )


class AIJob(UUIDPk, OrgScoped, Base):
    """Every AI invocation: what ran, on which provider/model, whether PHI left the system, and the outcome."""

    __tablename__ = "ai_jobs"
    kind: Mapped[str] = mapped_column(String(40), index=True)  # document_analysis | scribe_note | chart_qa | ...
    status: Mapped[str] = mapped_column(String(20), default="queued")
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str | None] = mapped_column(String(60))
    subject_type: Mapped[str | None] = mapped_column(String(40))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    phi_sent_externally: Mapped[bool] = mapped_column(default=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))  # from AI_PRICES; null = unknown
    error: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("status in ('queued','running','succeeded','failed')", name="status"),
                      Index("ix_ai_jobs_org_created", "organization_id", "created_at"))  # governance/usage windows
