"""AI scribe: transcription adapter + SOAP drafting.

Transcription: no speech-to-text engine ships with Undeclared. `get_transcriber()` returns an adapter that raises
`TranscriptionUnavailable` unless one is configured — recorded audio is never replaced with invented text.
Drafting: `simulated` (rule-based sentence sorting, labeled) or `anthropic` (Claude, structured output, PHI-gated).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from app.ai.provider import AIError, AIPolicyError
from app.core.config import settings


class Segment(BaseModel):
    speaker: str  # clinician | patient | other
    text: str


class SOAPDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subjective: str
    objective: str
    assessment: str
    plan: str
    chief_complaint: str | None
    follow_up: str | None
    medications_mentioned: list[str]
    allergies_mentioned: list[str]
    uncertainties: list[str]


@dataclass
class DraftResult:
    draft: SOAPDraft
    provider: str
    model: str | None
    phi_sent_externally: bool
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None


class TranscriptionUnavailable(AIError):
    pass


class NoTranscriber:
    name = "none"

    def transcribe(self, audio: bytes, content_type: str) -> list[Segment]:
        raise TranscriptionUnavailable(
            "No speech-to-text service is configured, so this recording can't be transcribed. "
            "Type or paste the conversation instead (or use the synthetic demo in test organizations). "
            "See docs/INTEGRATIONS.md for connecting a HIPAA-eligible transcription vendor.")


def get_transcriber():
    from app.ai.config import active_provider, effective

    if active_provider() == "openai" and effective().transcription_model:
        from app.ai.openai_provider import OpenAITranscriber, available

        if available("medical_scribe"):
            return OpenAITranscriber()
    return NoTranscriber()


# ---------------------------------------------------------------------------------------------------------------------
# Synthetic demo conversations (clearly labeled; synthetic organizations only)
# ---------------------------------------------------------------------------------------------------------------------

_DEMOS = {
    "cough": [
        ("clinician", "Hi, I'm Dr. {doc}. What brings you in today?"),
        ("patient", "I've had a cough for about five days. It's mostly dry, a little worse at night."),
        ("clinician", "Any fever, chills or shortness of breath?"),
        ("patient", "I felt warm the first two days but no fever since. No trouble breathing."),
        ("clinician", "Anyone sick at home? Have you tried anything for it?"),
        ("patient", "My son had a cold last week. I've been taking honey and tea, and some Tylenol."),
        ("clinician", "Any allergies to medications?"),
        ("patient", "Just penicillin, it gives me hives."),
        ("clinician", "Let me listen to your lungs. Lungs are clear bilaterally, no wheezes. Throat is mildly red, no exudate."),
        ("clinician", "This looks like an acute bronchitis, most likely viral, so antibiotics won't help."),
        ("clinician", "I recommend rest, fluids, honey for the cough, and you can use benzonatate 100 mg three times a day as needed."),
        ("clinician", "Return if you develop fever over 101, shortness of breath, or the cough lasts more than three weeks."),
        ("patient", "Okay, thank you."),
    ],
    "back": [
        ("clinician", "Hi, I'm Dr. {doc}. What's going on?"),
        ("patient", "My lower back started hurting three days ago after I moved some boxes."),
        ("clinician", "Does the pain go down your legs? Any numbness, weakness, or trouble with bladder or bowels?"),
        ("patient", "No, it stays in my lower back. No numbness. Bathroom is normal."),
        ("clinician", "What have you taken for it?"),
        ("patient", "Ibuprofen 400 mg a couple times a day. It helps a bit."),
        ("clinician", "On exam there's tenderness over the right lumbar paraspinal muscles, straight leg raise is negative, strength and reflexes are normal."),
        ("clinician", "This is consistent with a lumbar muscle strain. No red flags."),
        ("clinician", "Plan is to continue ibuprofen 400 mg with food up to three times a day, use heat, and stay gently active. I'll refer you to physical therapy."),
        ("clinician", "Follow up in four weeks if it's not improving, sooner if you get leg weakness or numbness."),
    ],
    "bp": [
        ("clinician", "Good to see you again. We're here to follow up on your blood pressure."),
        ("patient", "Yes. I've been checking at home, mostly around 140 over 90."),
        ("clinician", "Are you taking the lisinopril every day? Any cough or dizziness?"),
        ("patient", "I take lisinopril 10 mg every morning. No side effects."),
        ("clinician", "How about salt and exercise?"),
        ("patient", "I've been walking three times a week, but I still eat out a lot."),
        ("clinician", "Today your blood pressure is elevated again. Heart has a regular rhythm, no murmurs, no leg swelling."),
        ("clinician", "Your hypertension is not at goal on the current dose."),
        ("clinician", "Let's increase lisinopril to 20 mg daily, check a basic metabolic panel in two weeks, and work on reducing sodium."),
        ("clinician", "Follow up in six weeks with your home readings."),
    ],
}


def demo_transcript(chief_complaint: str | None, clinician_last_name: str) -> list[Segment]:
    cc = (chief_complaint or "").lower()
    key = "back" if "back" in cc else "bp" if ("pressure" in cc or "bp" in cc or "hypertension" in cc) else "cough"
    return [Segment(speaker=s, text=t.format(doc=clinician_last_name)) for s, t in _DEMOS[key]]


# ---------------------------------------------------------------------------------------------------------------------
# Drafting
# ---------------------------------------------------------------------------------------------------------------------

SCRIBE_SYSTEM = """You draft a SOAP progress note from a clinician-patient conversation transcript for the clinician to review.
Rules:
- Use only information stated in the transcript or the provided vitals. Never add exam findings, results, diagnoses, doses or plans that were not said.
- Assessment: record the clinician's stated impression only. If none was stated, write "Not stated in conversation." and add an uncertainty.
- Plan: only what the clinician said (medications with stated doses, tests, referrals, education, follow-up).
- Write concise clinical prose. Third person for the patient.
- List anything ambiguous, inaudible, or contradictory in `uncertainties`.
The clinician will edit and sign; you do not make clinical decisions."""

_EXAM = re.compile(r"\b(exam|lungs?|heart|throat|abdomen|tender|reflex|strength|straight leg|murmur|swelling|clear|blood pressure is|temperature|rash)\b", re.I)
_ASSESS = re.compile(r"\b(looks like|likely|consistent with|diagnos|impression|not at goal|this is|I think)\b", re.I)
_PLAN = re.compile(r"\b(recommend|prescrib|start|increase|decrease|continue|refer|order|check|plan is|let's|use|take|follow up|return)\b", re.I)
_MED = re.compile(r"\b([A-Z]?[a-z]{4,}(?:in|ol|en|ne|ate|ide|il|am|ex))\s+(?:to\s+)?(\d+(?:\.\d+)?\s*(?:mg|mcg))", re.I)
_FOLLOW = re.compile(r"(follow up[^.]*|return if[^.]*)", re.I)


def _third_person(text: str) -> str:
    t = re.sub(r"\bI've\b", "patient has", text)
    t = re.sub(r"\bI'm\b", "patient is", t)
    t = re.sub(r"\bI\b", "patient", t)
    t = re.sub(r"\bmy\b", "their", t, flags=re.I)
    t = re.sub(r"\bme\b", "them", t)
    return t[0].upper() + t[1:] if t else t


class SimulatedDrafter:
    name, model = "simulated", "rules-v1"

    def draft(self, segments: list[Segment], vitals_text: str | None, chief_complaint: str | None, *, contains_phi: bool) -> DraftResult:
        start = time.perf_counter()
        pat = [s.text for s in segments if s.speaker == "patient" and len(s.text) > 12 and not re.match(r"(?i)(ok|okay|thank)", s.text)]
        cli = [s.text for s in segments if s.speaker == "clinician"][1:]  # skip the opening greeting
        obj = [t for t in cli if _EXAM.search(t) and not _ASSESS.search(t)]
        assess = [t for t in cli if _ASSESS.search(t) and t not in obj]
        plan = [t for t in cli if _PLAN.search(t) and t not in assess and t not in obj and not t.endswith("?")]
        meds = sorted({f"{m.group(1).capitalize()} {m.group(2)}" for s in segments for m in _MED.finditer(s.text)})
        allergies = [m.group(1).strip().capitalize() for s in segments for m in re.finditer(r"(?:allergic to|just|only)\s+(penicillin|sulfa|codeine|latex|peanuts?)", s.text, re.I)]
        follow = next((m.group(1) for t in reversed(cli) for m in [_FOLLOW.search(t)] if m), None)
        uncertainties = ["Simulated rule-based draft (not medical AI): sentences were sorted by keyword. Rewrite as needed."]
        if not assess:
            uncertainties.append("No clinician impression was detected in the conversation.")
        d = SOAPDraft(
            subjective=" ".join(_third_person(t) for t in pat) or "Not captured.",
            objective="\n".join(filter(None, [vitals_text, *obj])) or "Not captured.",
            assessment="\n".join(assess) or "Not stated in conversation.",
            plan="\n".join(f"- {t}" for t in plan) or "Not stated in conversation.",
            chief_complaint=chief_complaint, follow_up=follow, medications_mentioned=meds,
            allergies_mentioned=sorted(set(allergies)), uncertainties=uncertainties,
        )
        return DraftResult(d, self.name, self.model, False, latency_ms=int((time.perf_counter() - start) * 1000))


class AnthropicDrafter:
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic

        self._a = anthropic
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else anthropic.Anthropic()
        self.model = settings.anthropic_model

    def draft(self, segments: list[Segment], vitals_text: str | None, chief_complaint: str | None, *, contains_phi: bool) -> DraftResult:
        if contains_phi and not settings.ai_phi_allowed:
            raise AIPolicyError("External AI is disabled for patient data (AI_PHI_ALLOWED=false).")
        convo = "\n".join(f"{s.speaker.upper()}: {s.text}" for s in segments)
        user = (f"<chief_complaint>{chief_complaint or 'not recorded'}</chief_complaint>\n"
                f"<vitals>{vitals_text or 'none recorded'}</vitals>\n<transcript>\n{convo}\n</transcript>\nDraft the SOAP note.")
        start = time.perf_counter()
        try:
            resp = self.client.beta.messages.create(
                model=self.model, max_tokens=16000, system=SCRIBE_SYSTEM,
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SOAPDraft.model_json_schema()}},
                messages=[{"role": "user", "content": user}],
            )
        except self._a.RateLimitError as e:
            raise AIError("AI provider rate limit reached; try again shortly.") from e
        except self._a.APIStatusError as e:
            raise AIError(f"AI provider error ({e.status_code}).") from e
        except self._a.APIConnectionError as e:
            raise AIError("Could not reach the AI provider.") from e
        if resp.stop_reason == "refusal":
            raise AIError("The AI provider declined to draft this note; document manually.")
        if resp.stop_reason == "max_tokens":
            raise AIError("AI output was truncated; try again.")
        payload = next((b.text for b in resp.content if b.type == "text"), None)
        try:
            d = SOAPDraft.model_validate(json.loads(payload or ""))
        except Exception as e:  # noqa: BLE001
            raise AIError("AI output failed validation.") from e
        return DraftResult(d, self.name, resp.model, contains_phi, resp.usage.input_tokens, resp.usage.output_tokens,
                           int((time.perf_counter() - start) * 1000))


def get_drafter():
    from app.ai.config import active_provider

    if active_provider() == "openai":
        from app.ai.openai_provider import OpenAIDrafter, available

        if available("medical_scribe"):
            return OpenAIDrafter()
    return AnthropicDrafter() if active_provider() == "anthropic" else SimulatedDrafter()
