"""EHR chart assistant: answers questions about ONE patient's chart using only that chart, with citations.

Sources are built from records the caller is authorized to read. The assistant never prescribes, orders or makes
diagnoses; such requests are refused before any model is called.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import AIError, AIPolicyError
from app.core.config import settings
from app.models import (
    Allergy,
    ClinicalNote,
    Document,
    Encounter,
    HistoryEntry,
    LabResult,
    Order,
    Patient,
    PatientMedication,
    Problem,
    VitalSigns,
)


@dataclass
class Source:
    id: str
    type: str
    title: str
    date: str | None
    text: str
    link: str
    tokens: set[str] = field(default_factory=set)


@dataclass
class Answer:
    answer: str
    citations: list[Source]
    refused: bool
    provider: str
    model: str | None
    insufficient: bool = False
    phi_sent_externally: bool = False
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


SYNONYMS = {
    "bp": ["blood", "pressure", "systolic", "diastolic"], "pressure": ["blood", "bp"], "a1c": ["hemoglobin", "a1c"],
    "sugar": ["glucose", "a1c"], "diabetes": ["glucose", "a1c", "metformin", "e11.9"], "cholesterol": ["ldl", "hdl", "lipid", "triglycerides"],
    "lipids": ["ldl", "hdl", "cholesterol"], "kidney": ["creatinine", "bun"], "thyroid": ["tsh", "levothyroxine"],
    "meds": ["medication"], "medicines": ["medication"], "drugs": ["medication"], "allergic": ["allergy"], "weight": ["weight", "bmi"],
    "heart": ["heart", "hr"], "labs": ["lab"], "results": ["lab"], "visit": ["encounter"], "visits": ["encounter"],
}
STOP = {"the", "a", "an", "of", "for", "and", "is", "are", "what", "was", "were", "does", "do", "has", "have", "any", "on", "in", "to",
        "patient", "patients", "this", "their", "his", "her", "show", "me", "tell", "about", "list", "with", "last", "latest", "recent"}

REFUSE = re.compile(
    r"\b(should i (prescribe|give|start|order|stop|increase|decrease)|prescribe|what dose|what dosage|how much .* (should|to) (give|take)|"
    r"diagnose|what('s| is) (the )?diagnosis|is it cancer|order (a|an|the|some)|sign (the|this))\b", re.I)


def _tok(s: str) -> set[str]:
    words = {w for w in re.findall(r"[a-z0-9.]+", s.lower()) if w not in STOP and len(w) > 1}
    for w in list(words):
        words.update(SYNONYMS.get(w, []))
    return words


def build_sources(db: Session, p: Patient) -> list[Source]:
    out: list[Source] = []

    def add(type_: str, title: str, d: date | str | None, text: str, link: str) -> None:
        sid = f"S{len(out) + 1}"
        out.append(Source(sid, type_, title, d.isoformat() if isinstance(d, date) else d, text, link, _tok(f"{type_} {title} {text}")))

    age = (date.today() - p.date_of_birth).days // 365
    add("demographics", "Patient profile", None, f"{age}-year-old {p.sex_at_birth}; preferred language {p.preferred_language}.", f"/patients/{p.id}/demographics")
    for a in db.scalars(select(Allergy).where(Allergy.patient_id == p.id, Allergy.status == "active")).all():
        add("allergy", f"Allergy: {a.substance}", a.created_at.date(), f"{a.substance} allergy ({a.severity.replace('_', ' ')}), reaction: {a.reaction or 'not recorded'}.", f"/patients/{p.id}/allergies")
    for m in db.scalars(select(PatientMedication).where(PatientMedication.patient_id == p.id, PatientMedication.status == "active")).all():
        add("medication", f"Medication: {m.name}", m.start_date, f"{m.name} {m.dose or ''} {m.frequency or ''}".strip() + (f" for {m.indication}" if m.indication else "") + ".", f"/patients/{p.id}/medications")
    for pr in db.scalars(select(Problem).where(Problem.patient_id == p.id, Problem.status.in_(("active", "resolved")))).all():
        add("problem", f"Problem: {pr.description}", pr.onset_date, f"{pr.description} ({pr.code or 'no code'}), {pr.status}{', chronic' if pr.is_chronic else ''}.", f"/patients/{p.id}/problems")
    for h in db.scalars(select(HistoryEntry).where(HistoryEntry.patient_id == p.id)).all():
        add("history", f"{h.category.title()} history", h.occurred_on, f"{h.condition}{f' ({h.relation})' if h.relation else ''}{f': {h.details}' if h.details else ''}.", f"/patients/{p.id}/history")
    for v in db.scalars(select(VitalSigns).where(VitalSigns.patient_id == p.id).order_by(VitalSigns.measured_at.desc()).limit(5)).all():
        parts = [f"blood pressure {v.systolic}/{v.diastolic}" if v.systolic else None, f"heart rate {v.heart_rate}" if v.heart_rate else None,
                 f"weight {round(float(v.weight_kg) * 2.20462)} lb" if v.weight_kg else None, f"BMI {v.bmi}" if v.bmi else None,
                 f"temperature {round(float(v.temperature_c) * 9 / 5 + 32, 1)} F" if v.temperature_c else None]
        add("vitals", "Vital signs", v.measured_at.date(), ", ".join(x for x in parts if x) + ".", f"/patients/{p.id}/vitals")
    for e in db.scalars(select(Encounter).where(Encounter.patient_id == p.id).order_by(Encounter.started_at.desc()).limit(8)).all():
        note = db.scalar(select(ClinicalNote).where(ClinicalNote.encounter_id == e.id, ClinicalNote.status == "signed"))
        dx = "; ".join(f"{d.description} ({d.code})" for d in e.diagnoses)
        text = f"Visit with {e.provider.user.display_name} for {e.chief_complaint or e.encounter_type}. Diagnoses: {dx or 'none recorded'}."
        if note:
            text += f" Assessment: {note.content.get('assessment', '')[:400]} Plan: {note.content.get('plan', '')[:400]}"
        add("encounter", f"Visit {e.started_at:%b %d, %Y}", e.started_at.date(), text, f"/encounters/{e.id}")
    for r in db.scalars(select(LabResult).where(LabResult.patient_id == p.id).order_by(LabResult.resulted_at.desc()).limit(40)).all():
        rel = "within" if r.flag == "normal" else ("above" if "high" in r.flag else "below" if "low" in r.flag else "outside")
        add("lab", f"Lab: {r.name}", r.resulted_at.date(), f"{r.name} {r.value} {r.unit or ''} (reference {r.reference_range or 'n/a'}; {rel} the reference range).", f"/patients/{p.id}/results")
    for d in db.scalars(select(Document).where(Document.patient_id == p.id, Document.status == "filed").order_by(Document.created_at.desc()).limit(10)).all():
        add("document", f"Document: {d.title}", d.document_date, d.summary or d.title or "", f"/documents/{d.id}")
    for o in db.scalars(select(Order).where(Order.patient_id == p.id, Order.order_type.in_(("imaging", "referral")), Order.status != "cancelled")
                        .order_by(Order.created_at.desc()).limit(10)).all():
        add("order", o.title, o.created_at.date(), f"{o.title}, status {o.status}." + (f" Result: {o.result_text[:300]}" if o.result_text else ""), f"/patients/{p.id}/orders")
    return out


def retrieve(sources: list[Source], question: str, k: int = 8) -> list[Source]:
    q = _tok(question)
    scored = sorted(((len(q & s.tokens), i, s) for i, s in enumerate(sources)), key=lambda x: (-x[0], x[1]))
    return [s for score, _, s in scored if score > 0][:k]


def _clip(text: str, n: int) -> str:
    """Trim to n chars at a sentence (or word) boundary — never mid-word."""
    if len(text) <= n:
        return text
    cut = text[:n]
    end = cut.rfind(". ")
    return cut[: end + 1] if end > n * 0.5 else cut[: cut.rfind(" ")] + "…"


def _cite(srcs: list[Source]) -> str:
    return " ".join(f"[{s.id}]" for s in srcs)


class SimulatedAssistant:
    name, model = "simulated", "rules-v1"

    def answer(self, question: str, sources: list[Source], history: list[dict], *, contains_phi: bool) -> Answer:
        start = time.perf_counter()
        q = question.lower()
        by = lambda t: [s for s in sources if s.type == t]  # noqa: E731
        used: list[Source] = []
        lines: list[str] = []
        if re.search(r"\b(summar\w*|overview|background|history of|patient'?s history|medical history)\b", q):
            demo = by("demographics")[0]
            probs = [s for s in by("problem") if "active" in s.text]
            used += [demo, *probs[:6], *by("medication")[:8], *by("allergy"), *by("encounter")[:1]]
            lines.append(f"{demo.text} {_cite([demo])}")
            lines.append(f"Active problems: {', '.join(s.title.split(': ', 1)[1] for s in probs) or 'none recorded'}. {_cite(probs[:6])}".strip())
            meds = by("medication")
            lines.append(f"Active medications ({len(meds)}): {', '.join(s.title.split(': ', 1)[1] for s in meds[:8]) or 'none'}. {_cite(meds[:8])}".strip())
            alg = by("allergy")
            lines.append(f"Allergies: {', '.join(s.title.split(': ', 1)[1] for s in alg) or 'none recorded (not a confirmed no-known-allergies)'}. {_cite(alg)}".strip())
            if by("encounter"):
                e = by("encounter")[0]
                lines.append(f"Most recent visit ({e.date}): {_clip(e.text, 320)} {_cite([e])}")
            abn = [s for s in by("lab") if "above" in s.text or "below" in s.text or "outside" in s.text][:4]
            if abn:
                used += abn
                lines.append("Recent results outside the reference range: " + "; ".join(f"{s.text.split(' (')[0]} on {s.date} [{s.id}]" for s in abn) + ".")
        elif re.search(r"\ballerg", q):
            used = by("allergy")
            lines = [f"{s.text} [{s.id}]" for s in used] or ["No active allergies are recorded in this chart."]
        elif re.search(r"\b(med|medication|medicine|drug|taking)", q):
            used = by("medication")
            lines = [f"{s.text} [{s.id}]" for s in used] or ["No active medications are recorded in this chart."]
        elif re.search(r"\b(problem|condition|diagnos(es|is) list|chronic)\b", q):
            used = by("problem")
            lines = [f"{s.text} [{s.id}]" for s in used] or ["No problems are recorded in this chart."]
        elif re.search(r"\b(visit|seen|encounter|appointment)\b", q):
            used = by("encounter")[:3]
            lines = [f"{s.title}: {_clip(s.text, 400)} [{s.id}]" for s in used] or ["No visits are recorded in this chart."]
        elif re.search(r"\b(vital|bp|blood pressure|weight|bmi|heart rate|pulse|temperature)\b", q):
            used = by("vitals")[:5]
            lines = [f"{s.date}: {s.text} [{s.id}]" for s in used] or ["No vital signs are recorded in this chart."]
        else:
            hits = retrieve(sources, question)
            labs = [h for h in hits if h.type == "lab"]
            used = labs[:6] if labs else hits[:5]
            if not used:
                lines = ["I couldn't find information about that in this patient's chart."]
            else:
                lines = [f"{s.date or ''} {s.title}: {s.text} [{s.id}]".strip() for s in used]
                if labs:
                    lines.append("Reference ranges come from the reporting lab; interpretation in clinical context is up to the treating clinician.")
        text = "\n".join(lines)
        seen: set[str] = set()
        cites = [s for s in used if not (s.id in seen or seen.add(s.id))]
        return Answer(text, cites, False, self.name, self.model, insufficient=not cites, latency_ms=int((time.perf_counter() - start) * 1000))


class AssistantOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    cited_source_ids: list[str]
    insufficient_information: bool


ASSISTANT_SYSTEM = """You answer clinicians' questions about ONE patient's chart using only the numbered sources provided.
- Cite every factual statement with the source id in brackets, e.g. [S3]. Use only ids that appear in the sources.
- If the sources don't contain the answer, say so plainly and set insufficient_information=true. Never guess or use outside knowledge about the patient.
- You may explain what a value means relative to its reference range, but do not make diagnoses, recommend treatments, doses or orders.
- Be concise: short sentences or bullets."""


class AnthropicAssistant:
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        self._a = anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else anthropic.Anthropic()
        self.model = settings.anthropic_model

    def answer(self, question: str, sources: list[Source], history: list[dict], *, contains_phi: bool) -> Answer:
        if contains_phi and not settings.ai_phi_allowed:
            raise AIPolicyError("External AI is disabled for patient data (AI_PHI_ALLOWED=false).")
        src_text = "\n".join(f"[{s.id}] ({s.type}{', ' + s.date if s.date else ''}) {s.title}: {s.text}" for s in sources)
        msgs = [{"role": h["role"], "content": h["content"]} for h in history[-6:] if h.get("role") in ("user", "assistant")]
        msgs.append({"role": "user", "content": f"<sources>\n{src_text}\n</sources>\n<question>{question}</question>"})
        start = time.perf_counter()
        try:
            resp = self.client.beta.messages.create(
                model=self.model, max_tokens=4000, system=ASSISTANT_SYSTEM, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": AssistantOut.model_json_schema()}}, messages=msgs)
        except self._a.APIStatusError as e:
            raise AIError(f"AI provider error ({e.status_code}).") from e
        except self._a.APIConnectionError as e:
            raise AIError("Could not reach the AI provider.") from e
        if resp.stop_reason == "refusal":
            raise AIError("The AI provider declined this question.")
        payload = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            out = AssistantOut.model_validate(json.loads(payload))
        except Exception as e:  # noqa: BLE001
            raise AIError("AI output failed validation.") from e
        valid = {s.id: s for s in sources}
        cites = [valid[i] for i in out.cited_source_ids if i in valid]  # drop hallucinated ids
        return Answer(out.answer, cites, False, self.name, resp.model, out.insufficient_information or not cites, contains_phi,
                      int((time.perf_counter() - start) * 1000), resp.usage.input_tokens, resp.usage.output_tokens)


def get_assistant():
    from app.ai.config import active_provider

    if active_provider() == "openai":
        from app.ai.openai_provider import OpenAIAssistant, available

        if available("doctor_assistant"):
            return OpenAIAssistant()
    return AnthropicAssistant() if active_provider() == "anthropic" else SimulatedAssistant()


def refusal(question: str) -> str | None:
    if REFUSE.search(question):
        return ("I can't make prescribing, ordering or diagnostic decisions. I can show what the chart says — for example "
                "current medications, allergies, recent results or the last visit's assessment and plan — to support your decision.")
    return None
