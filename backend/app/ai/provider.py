"""AI provider abstraction.

- `simulated` (default): deterministic, rule-based, runs locally, never sends data anywhere. Good enough to exercise the
  full workflow with synthetic documents; it is NOT medical AI and says so in its output.
- `anthropic`: Claude via the official SDK, structured JSON output validated with Pydantic. Refused for PHI unless
  AI_PHI_ALLOWED=true (which must only be set once a BAA and data-flow review are in place).

Every output is a draft for human review; nothing here writes to a chart.
"""

from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.config import settings

DocType = Literal[
    "lab_result", "imaging_report", "referral", "consult_note", "discharge_summary", "insurance_card",
    "id_card", "prescription", "intake_form", "correspondence", "other",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PatientIdentifiers(_Strict):
    first_name: str | None
    last_name: str | None
    date_of_birth: str | None  # YYYY-MM-DD as written on the document
    mrn: str | None


class Finding(_Strict):
    label: str
    value: str
    flag: Literal["normal", "abnormal", "unknown"]
    reference_range: str | None


class InsuranceCardFields(_Strict):
    payer_name: str | None
    plan_name: str | None
    member_id: str | None
    group_number: str | None
    subscriber_name: str | None
    effective_date: str | None  # YYYY-MM-DD
    rx_bin: str | None


class DocumentAnalysis(_Strict):
    doc_type: DocType
    title: str
    document_date: str | None  # YYYY-MM-DD
    sender: str | None
    summary: str
    patient: PatientIdentifiers
    key_findings: list[Finding]
    medications: list[str]
    diagnoses_stated: list[str]
    confidence: float  # 0..1, the model's/heuristic's confidence in the extraction overall
    uncertainties: list[str]
    insurance_card: InsuranceCardFields | None = None  # only for doc_type == insurance_card


@dataclass
class AIResult:
    data: DocumentAnalysis
    provider: str
    model: str | None
    phi_sent_externally: bool
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None


class AIError(Exception):
    """Provider failed or declined; message is safe to show to staff."""


class AIPolicyError(AIError):
    """Configuration forbids this call (e.g. PHI to an external provider without approval)."""


DOC_ANALYSIS_SYSTEM = """You extract structured data from a single clinical document for a clinic's document-intake queue.
Rules:
- Report only what is written in the document. Never infer diagnoses, values or identities that are not stated.
- Copy patient identifiers exactly as printed; dates as YYYY-MM-DD; use null when absent or unreadable.
- The summary is 1-3 plain sentences for clinic staff, describing what the document is and its stated conclusions.
- List anything illegible, ambiguous or conflicting in `uncertainties`, and lower `confidence` (0-1) accordingly.
- For insurance cards (doc_type insurance_card) fill `insurance_card` with the fields printed on the card; otherwise null.
- A human reviews every result before it is filed; do not give medical advice."""


# ----------------------------------------------------------------------------------------------------------------------
# Simulated provider
# ----------------------------------------------------------------------------------------------------------------------

_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("lab_result", ("laboratory report", "lab report", "reference range", "specimen", "hemoglobin", "lipid panel")),
    ("imaging_report", ("radiology", "impression:", "x-ray", "ct scan", "mri", "ultrasound", "imaging report")),
    ("referral", ("referral", "reason for referral", "referred by")),
    ("discharge_summary", ("discharge summary", "discharge diagnosis", "hospital course", "admission date")),
    ("consult_note", ("consultation", "consult note")),
    ("insurance_card", ("member id", "group number", "rx bin", "payer")),
    ("prescription", ("rx:", "sig:", "dispense", "refills")),
    ("intake_form", ("intake form", "patient questionnaire")),
]
_DATE = r"(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})"


def _norm_date(s: str | None) -> str | None:
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _field(text: str, *labels: str) -> str | None:
    for label in labels:
        m = re.search(rf"{label}\s*[:#]\s*(.+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


class SimulatedProvider:
    name = "simulated"
    model = "rules-v1"

    def analyze_document(self, text: str | None, file_bytes: bytes, content_type: str, *, contains_phi: bool) -> AIResult:
        start = time.perf_counter()
        uncertainties: list[str] = ["Simulated rule-based extraction (no medical AI). Verify every field against the document."]
        if not text or len(text.strip()) < 20:
            data = DocumentAnalysis(
                doc_type="other", title="Unreadable document", document_date=None, sender=None,
                summary="No machine-readable text was found. This looks like a scanned image; OCR needs a vision-capable AI provider.",
                patient=PatientIdentifiers(first_name=None, last_name=None, date_of_birth=None, mrn=None),
                key_findings=[], medications=[], diagnoses_stated=[], confidence=0.05,
                uncertainties=[*uncertainties, "No text layer found (scanned image)."],
            )
            return AIResult(data, self.name, self.model, False, latency_ms=int((time.perf_counter() - start) * 1000))

        low = text.lower()
        doc_type = next((t for t, kws in _TYPE_KEYWORDS if any(k in low for k in kws)), "other")

        first = last = None
        raw_name = _field(text, "Patient Name", "Patient", "Name")
        if raw_name:
            raw_name = re.split(r"\s{2,}|\s+(?:DOB|MRN|Sex)\b", raw_name)[0].strip()
            if "," in raw_name:
                last, first = [x.strip() or None for x in raw_name.split(",", 1)]
            else:
                parts = raw_name.split()
                if len(parts) >= 2:
                    first, last = parts[0], parts[-1]
        dob_m = re.search(rf"(?:DOB|Date of Birth)\s*[:#]?\s*{_DATE}", text, re.IGNORECASE)
        mrn_m = re.search(r"MRN\s*[:#]?\s*([A-Z]{0,4}\d{4,})", text, re.IGNORECASE)
        date_m = re.search(rf"(?:Date of Service|Report Date|Collected|Date of Referral|Discharge Date|Date)\s*[:#]?\s*{_DATE}", text, re.IGNORECASE)
        sender = _field(text, "From", "Ordering Facility", "Facility", "Referring Provider")

        findings: list[Finding] = []
        for line in text.splitlines():
            m = re.match(r"^\s*([A-Za-z][A-Za-z0-9 ,()/%-]{1,40}?):\s*([<>]?[\d.]+\s*[A-Za-z/%0-9^.]*)\s*(\((H|L|N)\))?\s*(\[ref ([^\]]+)\])?\s*$", line)
            if m and not re.match(r"(?i)(dob|mrn|date|phone|fax)", m.group(1)) and not re.search(r"\d+/\d+/\d{4}", m.group(2)):
                flag = {"H": "abnormal", "L": "abnormal", "N": "normal"}.get(m.group(4) or "", "unknown")
                findings.append(Finding(label=m.group(1).strip(), value=m.group(2).strip(), flag=flag, reference_range=m.group(6)))
        meds = [m.strip() for m in re.findall(r"(?im)^\s*[-*]\s*((?:[A-Z][a-z]+)(?:\s+\d+(?:\.\d+)?\s*(?:mg|mcg|units?))[^\n]*)", text)][:10]

        section = None
        for header in ("Impression", "Assessment", "Reason for Referral", "Discharge Diagnosis", "Summary", "Comments"):
            m = re.search(rf"{header}\s*:\s*(.+?)(?:\n\s*\n|\n[A-Z][A-Za-z ]+:|$)", text, re.IGNORECASE | re.DOTALL)
            if m:
                section = " ".join(m.group(1).split())
                break
        title = {"lab_result": "Laboratory report", "imaging_report": "Imaging report", "referral": "Referral",
                 "discharge_summary": "Discharge summary", "consult_note": "Consultation note", "insurance_card": "Insurance card",
                 "prescription": "Prescription", "intake_form": "Intake form"}.get(doc_type, "Document")
        abnormal = [f for f in findings if f.flag == "abnormal"]
        if doc_type == "lab_result" and findings:
            section = None  # lead lab summaries with the results, not the boilerplate comment
        summary = section or (f"{title} with {len(findings)} result(s)" + (f"; abnormal: {', '.join(f.label for f in abnormal[:4])}." if abnormal else ".") if findings else text.strip()[:280])

        score = 0.25 + 0.15 * bool(first and last) + 0.15 * bool(dob_m) + 0.1 * bool(mrn_m) + 0.1 * (doc_type != "other") + 0.1 * bool(date_m)
        if not (first and last):
            uncertainties.append("Patient name not found.")
        if not dob_m:
            uncertainties.append("Date of birth not found.")
        card = None
        if doc_type == "insurance_card":
            eff = re.search(rf"Effective(?: Date)?\s*[:#]?\s*{_DATE}", text, re.IGNORECASE)
            card = InsuranceCardFields(
                payer_name=_field(text, "Payer", "Insurance Company", "Carrier"), plan_name=_field(text, "Plan", "Plan Name"),
                member_id=(_field(text, "Member ID", "Member Number", "ID") or "").split()[0] or None,
                group_number=(_field(text, "Group Number", "Group", "Group No") or "").split()[0] or None,
                subscriber_name=_field(text, "Member Name", "Subscriber", "Name"),
                effective_date=_norm_date(eff.group(1)) if eff else None, rx_bin=_field(text, "RX BIN", "RxBIN"))
            if raw_name is None and card.subscriber_name:
                parts = card.subscriber_name.split()
                first, last = (parts[0], parts[-1]) if len(parts) >= 2 else (first, last)
            if not card.member_id:
                uncertainties.append("Member ID not found on the card.")
        data = DocumentAnalysis(
            insurance_card=card,
            doc_type=doc_type, title=title, document_date=_norm_date(date_m.group(1)) if date_m else None, sender=sender,
            summary=summary[:600],
            patient=PatientIdentifiers(first_name=first, last_name=last, date_of_birth=_norm_date(dob_m.group(1)) if dob_m else None,
                                       mrn=mrn_m.group(1).upper() if mrn_m else None),
            key_findings=findings[:25], medications=meds, diagnoses_stated=[section] if doc_type == "discharge_summary" and section else [],
            confidence=round(min(score, 0.85), 2), uncertainties=uncertainties,
        )
        return AIResult(data, self.name, self.model, False, latency_ms=int((time.perf_counter() - start) * 1000))


# ----------------------------------------------------------------------------------------------------------------------
# Anthropic provider
# ----------------------------------------------------------------------------------------------------------------------

class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        self._anthropic = anthropic
        # Zero-arg client resolves credentials from the environment (ANTHROPIC_API_KEY or an `ant auth login` profile).
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else anthropic.Anthropic()
        self.model = settings.anthropic_model

    def analyze_document(self, text: str | None, file_bytes: bytes, content_type: str, *, contains_phi: bool) -> AIResult:
        if contains_phi and not settings.ai_phi_allowed:
            raise AIPolicyError("External AI is disabled for patient data (AI_PHI_ALLOWED=false). "
                                "Enable only with a BAA in place, or use the simulated provider.")
        a = self._anthropic
        b64 = base64.standard_b64encode(file_bytes).decode()
        if content_type == "application/pdf":
            source_block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
        elif content_type in ("image/png", "image/jpeg", "image/webp", "image/gif"):
            source_block = {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": b64}}
        else:
            source_block = {"type": "text", "text": f"<document_text>\n{text or ''}\n</document_text>"}
        start = time.perf_counter()
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=DOC_ANALYSIS_SYSTEM,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": "medium",
                               "format": {"type": "json_schema", "schema": DocumentAnalysis.model_json_schema()}},
                messages=[{"role": "user", "content": [source_block, {"type": "text", "text": "Extract the document data."}]}],
            )
        except a.RateLimitError as e:
            raise AIError("AI provider rate limit reached; the document will need reprocessing.") from e
        except a.APIStatusError as e:
            raise AIError(f"AI provider error ({e.status_code}).") from e
        except a.APIConnectionError as e:
            raise AIError("Could not reach the AI provider.") from e
        if resp.stop_reason == "refusal":
            raise AIError("The AI provider declined to process this document; review it manually.")
        if resp.stop_reason == "max_tokens":
            raise AIError("AI output was truncated; review manually or reprocess.")
        payload = next((b.text for b in resp.content if b.type == "text"), None)
        if payload is None:
            raise AIError("AI provider returned no structured output.")
        try:
            data = DocumentAnalysis.model_validate(json.loads(payload))
        except Exception as e:  # noqa: BLE001
            raise AIError("AI output failed validation.") from e
        data.confidence = max(0.0, min(1.0, data.confidence))
        return AIResult(data, self.name, resp.model, contains_phi, resp.usage.input_tokens, resp.usage.output_tokens,
                        int((time.perf_counter() - start) * 1000))


def get_provider():
    from app.ai.config import active_provider

    if active_provider() == "anthropic":
        return AnthropicProvider()
    if active_provider() == "openai":
        from app.ai.openai_provider import OpenAIDocumentProvider, available

        if available():
            return OpenAIDocumentProvider()
    return SimulatedProvider()  # also the graceful fallback when OpenAI isn't configured (labeled "simulated")
