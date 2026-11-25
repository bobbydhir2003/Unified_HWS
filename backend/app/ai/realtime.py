"""Realtime Voice sessions (OpenAI Realtime over WebRTC).

The permanent API key never leaves the server: the backend mints a short-lived client secret
(POST /v1/realtime/client_secrets) bound to the configured realtime model, voice and instructions; the browser
uses only that ephemeral value to POST its SDP offer to /v1/realtime/calls. Without a configured key/model the
caller gets mode="simulated" and the UI says so. PHI policy is the same as every other external AI call."""

from __future__ import annotations

import hashlib
import uuid

import httpx

from app.ai.provider import AIError, AIPolicyError

CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
CALLS_URL = "https://api.openai.com/v1/realtime/calls"

RECEPTIONIST_INSTRUCTIONS = (
    "You are the front-desk voice assistant for a hospital, speaking with callers. You help with routine administrative "
    "questions only: opening hours, directions, how to book or change an appointment, what to bring, portal access. "
    "Never give medical advice, diagnose, discuss test results or medications, or promise anything about billing or coverage. "
    "If the caller describes an emergency, tell them to hang up and call emergency services now. "
    "For anything clinical or account-specific, offer to have a staff member call back. Keep answers short and clear. "
    "Use get_clinic_information for facility names, phone numbers, addresses and departments — never guess them. "
    "Use request_staff_callback only after the caller agrees to a callback; it creates a follow-up task for the front desk "
    "and books nothing. You cannot look up patients, appointments, results or bills, and you cannot change any record."
)

# Server-validated, read-only or task-creating tools offered to the voice model. The browser relays each function call to
# POST /ai/realtime/tools/{name}; the server checks the name, arguments, permissions and limits before doing anything.
TOOLS = [
    {"type": "function", "name": "get_clinic_information",
     "description": "Facility names, phone numbers, addresses and departments for this hospital. Read-only.",
     "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "request_staff_callback",
     "description": "Ask the front desk to call the caller back about an administrative matter. Creates a follow-up task only.",
     "parameters": {"type": "object", "additionalProperties": False, "required": ["topic"],
                    "properties": {"topic": {"type": "string", "description": "Short administrative reason, no medical details"},
                                   "caller_first_name": {"type": "string"},
                                   "preferred_time": {"type": "string", "description": "e.g. 'tomorrow morning'"}}}},
]
TOOL_NAMES = {t["name"] for t in TOOLS}
CALLBACKS_PER_USER_PER_DAY = 10


def realtime_status() -> dict:
    from app.ai.config import effective

    e = effective()
    ready = e.provider == "openai" and bool(e.api_key) and bool(e.realtime_model)
    return {"mode": "openai" if ready else "simulated", "model": e.realtime_model or None,
            "reason": None if ready else ("Configure an OpenAI key and a Realtime model in Super Admin → AI settings, then Test connection."
                                          if e.provider == "openai" or not e.api_key else "Active AI provider is not OpenAI.")}


def probe_realtime(cfg) -> None:
    """Prove the realtime model works with this key by minting (not using) a client secret. Raises AIError."""
    with httpx.Client(timeout=15) as http:
        r = http.post(CLIENT_SECRETS_URL, json={"session": {"type": "realtime", "model": cfg.realtime_model}},
                      headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"})
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message") or r.text[:200]
        except ValueError:
            msg = r.text[:200]
        raise AIError(f"Realtime model '{cfg.realtime_model}' rejected ({r.status_code}): {msg}")


def mint_client_secret(*, org_id: uuid.UUID, user_id: uuid.UUID, contains_phi: bool, voice: str = "marin",
                       instructions: str = RECEPTIONIST_INSTRUCTIONS, tools: list[dict] | None = None,
                       client: httpx.Client | None = None) -> dict:
    """Return {"value", "expires_at", "model"} for one browser session. Raises AIError/AIPolicyError."""
    from app.ai.config import effective
    from app.core.config import settings

    e = effective()
    if not (e.provider == "openai" and e.api_key and e.realtime_model):
        raise AIError("Realtime voice is not configured")
    if contains_phi and not settings.ai_phi_allowed:
        raise AIPolicyError("External AI is disabled for patient data (AI_PHI_ALLOWED=false). Realtime voice is available only for "
                            "synthetic organizations until a BAA and data-flow review are in place.")
    max_seconds = int((e.limits or {}).get("realtime_max_seconds") or settings.ai_realtime_max_seconds)
    body = {"expires_after": {"anchor": "created_at", "seconds": 60},  # the browser must connect within a minute
            "session": {"type": "realtime", "model": e.realtime_model, "instructions": instructions, "audio": {"output": {"voice": voice}},
                        "tools": TOOLS if tools is None else tools, "tool_choice": "auto"}}
    if e.transcription_model:  # caller transcripts let the server apply its confirmation and emergency rules to voice sessions
        body["session"]["audio"]["input"] = {"transcription": {"model": e.transcription_model}}
    # Pseudonymous safety identifier (no names/emails): hash of org + user.
    safety_id = hashlib.sha256(f"{org_id}:{user_id}".encode()).hexdigest()[:32]
    from app.ai import demo_scope

    http = client or httpx.Client(timeout=15)
    try:
        with demo_scope.guard(e.realtime_model, kind="realtime") as ticket:
            ticket.cost = None  # a session's audio isn't metered here: the reserved per-session estimate stands
            r = http.post(CLIENT_SECRETS_URL, json=body, headers={"Authorization": f"Bearer {e.api_key}", "Content-Type": "application/json",
                                                                  "OpenAI-Safety-Identifier": safety_id})
    except httpx.HTTPError as ex:
        raise AIError(f"Could not reach OpenAI: {type(ex).__name__}") from None
    finally:
        if client is None:
            http.close()
    if r.status_code >= 400:
        # Never echo request headers; the provider's error message is safe to show to an admin.
        try:
            msg = r.json().get("error", {}).get("message") or r.text[:200]
        except ValueError:
            msg = r.text[:200]
        raise AIError(f"OpenAI rejected the realtime session ({r.status_code}): {msg}")
    data = r.json()
    value = data.get("value") or (data.get("client_secret") or {}).get("value")
    if not value:
        raise AIError("OpenAI response did not include a client secret")
    return {"value": value, "expires_at": data.get("expires_at") or (data.get("client_secret") or {}).get("expires_at"),
            "model": e.realtime_model, "calls_url": CALLS_URL, "max_seconds": max_seconds}
