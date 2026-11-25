# HMS Voice Concierge

Conversational administrative front-desk agent (replaces the scripted "AI receptionist" simulator). Page: **/receptionist**
(sidebar: *HMS Voice Concierge*), permission `schedule:write` to run calls, `schedule:read` for the list and stats.

## How it works
- **One engine for every channel** — `app/services/concierge.py`. Typed test calls, browser voice (OpenAI Realtime over
  WebRTC) and the telephony webhook all call the same server-validated tools. The browser only relays the voice model's
  tool requests (`/receptionist/calls/{id}/voice/tools/{name}`) and transcripts (`.../voice/utterance`).
- **Conversation** — with an OpenAI text model configured (and the organization allowed to send data to it) each caller
  turn runs the shared `OpenAICore.tool_loop` under the shared AI request/spend limits (`app/ai/limits.py`, agent key
  `voice_concierge`), logged as `AIJob(kind="voice_concierge")`. Otherwise, or on provider failure/limit, a deterministic
  language engine drives the same tools. The overview endpoint reports which is active.
- **Dedicated tool set** (no access to other agents' tools): facility information, verify caller, check verification
  code, find available slots, list the caller's appointments, prepare booking / reschedule / cancellation, confirm or
  discard the pending action, create a callback request, request a staff handoff, end call.

## Safety rules enforced in code
- Greeting discloses the AI assistant, recording and 911; continuing after it is recorded as consent; "don't record /
  no AI" → staff handoff and the call ends.
- Emergency language → approved 911 direction, urgent staff task, automation stops.
- **Name + date of birth are never verification.** An exact match (non-restricted, active patient with portal access)
  gets a one-time 6-digit code sent to the patient's portal notifications (10-minute expiry, 3 identity attempts, 3 code
  attempts). The response is identical whether or not a record matched. Synthetic test calls show the code to staff.
- Changes execute only from a prepared pending action, when the caller's **latest** utterance (in a later turn) is an
  explicit yes; availability, minimum notice (2 h), clinician schedule and patient/provider conflicts are re-checked;
  changes within 24 h go to staff. Each executed action has an idempotency key; call rows are locked per request.
- Test calls in an organization with real patient data never change appointments.
- No live call transfer exists: handoffs create a high-priority front-desk task and the caller is told so.
- Calls are scoped to the viewer's facilities; lists carry no transcripts; transcript views by other staff are audited.
- Facility hours come only from `clinics.settings.published_hours`; when absent the concierge says so.

## Not connected (feature-flagged off)
- Public phone answering: requires an approved (BAA-covered) telephony provider; set `VOICE_TELEPHONY_ENABLED=true` only
  after validating it. Live transfer to a staff line is not implemented.
- Identity verification beyond the portal code (e.g. SMS/IVR one-time codes) is not available; patients without portal
  access are routed to a staff callback.
- Realtime voice requires a configured Realtime model and, for real patient data, `AI_PHI_ALLOWED` with a BAA.
