# Integrations

Every external dependency sits behind an adapter (`app/integrations/adapters.py`: `OrderTransmitter`, `Clearinghouse`, `MessageGateway` protocols + registry selected by `*_ADAPTER` settings). Until a real, contracted and validated partner is connected, the adapter is **simulated**: deterministic, offline, and labeled `Simulated` in the UI and API.

| Integration | Status | Adapter / location | Production path |
|---|---|---|---|
| Email | Simulated (DB outbox, Admin › Message outbox) | `services/identity.send_email` | SES / SendGrid with BAA |
| SMS reminders | Simulated (beat task writes outbox) | `tasks.send_appointment_reminders` | Twilio with BAA |
| Insurance eligibility (270/271) | Simulated (member ID ends 0 → inactive, 9 → plan ends end of month, 8 → payer error); history in `eligibility_checks` | `integrations/adapters.SimulatedEligibility`, `services/insurance.py` | Clearinghouse (e.g., Availity, Change) |
| Object storage | Local disk or S3 | `services/storage.py` | S3 with SSE-KMS, private bucket |
| ICD-10-CM | Built-in common subset | `data/icd10_common.py` | Import annual CMS release into a table |
| AI (documents, scribe drafting, chart assistant, transcription, agents) | Simulated default; Anthropic and **OpenAI** providers implemented (OpenAI: Responses API, strict JSON-schema outputs, server-side tool loop, retries/timeouts, cost via `AI_PRICES`). **OpenAI live validation pending — no key configured during development; contract tests use a fake client.** PHI-gated; synthetic orgs exempt | `app/ai/provider.py` | Claude with BAA; set `AI_PROVIDER=anthropic`, `AI_PHI_ALLOWED=true` only after review |
| Inbound fax | Webhook implemented (`POST /api/integrations/fax/{org_slug}/inbound`, `X-Fax-Secret`, multipart `file` + `from_number`); simulated faxes from UI | `routers/documents.py` | Any fax vendor with BAA that can POST multipart; per-org secret in `organizations.settings.fax_webhook_secret` |
| OCR for scanned images | Not available in simulated mode | — | Vision-capable AI provider or Textract/tesseract |
| Speech-to-text (scribe) | Not configured — adapter `NoTranscriber` raises a clear error | `app/ai/scribe.py:get_transcriber` | HIPAA-eligible ASR with diarization (BAA), implement `transcribe(audio, content_type) -> [Segment]` |
| e-Prescribing | Simulated channel on sign (`transmission.simulated=true`) | `routers/orders.py:sign_order` | Surescripts-certified eRx partner (NewRx/CancelRx/RxChange), EPCS for controlled substances |
| Medication/lab/imaging catalogs | Built-in subsets | `data/catalogs.py` | Licensed drug database (RxNorm + interactions), lab compendium (LOINC), CPT licensing |
| Labs / imaging (HL7 v2 ORM/ORU) | Simulated order transmission + simulated results endpoint (synthetic orgs) | `routers/orders.py` | Interface engine; map ORU → `lab_results` with `source='interface'` |
| Referrals | Simulated fax delivery; manual status tracking | `routers/orders.py` | Direct messaging / fax vendor |
| Clearinghouse claims (837P/277CA/835) | Simulated: immediate acceptance, deterministic adjudication & appeals (synthetic orgs) | `routers/billing.py` | Clearinghouse partner; map 835 ERA → `payments(source=insurance)` + claim adjustments; real eligibility via 270/271 |
| Patient payments | Simulated processor (`card_simulated`); no card data collected | `routers/billing.py:_apply_payment` | PCI-compliant processor with hosted fields/tokenization (card data never touches Undeclared servers) |
| Telehealth video | Browser WebRTC (peer-to-peer, STUN only) with authenticated API signaling | `routers/telehealth.py`, `features/telehealth/VideoVisit.tsx` | BAA-covered video vendor (e.g. TURN/SFU, bandwidth adaptation); swap `join` to return vendor tokens |
| Telephony / AI receptionist | Sandbox simulator + webhook (`POST /api/integrations/voice/{org_slug}/inbound`, `X-Voice-Secret`, JSON `{call_sid, from_number, speech}` → `{say, hangup, transfer}`) | `routers/ai.py`, `services/receptionist.py` | BAA-covered telephony + speech recognition/TTS vendor posting recognized speech per turn; warm transfer to staff line |
| FHIR R4 | Read API implemented: `/api/fhir/R4/metadata`, `Patient/{id}`, `Patient?identifier|family|birthdate`, `Encounter|Condition|AllergyIntolerance|MedicationStatement|Observation?patient=` (Observation `category=vital-signs|laboratory`) | `app/integrations/fhir.py` | Add SMART on FHIR (OAuth scopes), US Core profiles + Inferno testing, write operations, `$export` |
