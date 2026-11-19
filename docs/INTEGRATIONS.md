# Integrations

Every external dependency sits behind an adapter. Until a real, contracted and validated partner is connected, the adapter is **simulated**: deterministic, offline, and labeled `Simulated` in the UI and API.

| Integration | Status | Adapter / location | Production path |
|---|---|---|---|
| Email | Simulated (DB outbox, Admin › Message outbox) | `services/identity.send_email` | SES / SendGrid with BAA |
| SMS reminders | Simulated (beat task writes outbox) | `tasks.send_appointment_reminders` | Twilio with BAA |
| Insurance eligibility (270/271) | Simulated (member IDs ending in 0 → inactive) | `patients.check_eligibility` | Clearinghouse (e.g., Availity, Change) |
| Object storage | Local disk or S3 | `services/storage.py` | S3 with SSE-KMS, private bucket |
| ICD-10-CM | Built-in common subset | `data/icd10_common.py` | Import annual CMS release into a table |
| AI document analysis | Simulated (rule-based) default; Anthropic provider implemented, PHI-gated | `app/ai/provider.py` | Claude with BAA; set `AI_PROVIDER=anthropic`, `AI_PHI_ALLOWED=true` only after review |
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
| Telephony / AI receptionist | Planned (phase 10), sandbox | — | Telephony provider with BAA |
| FHIR R4 | Planned (phase 12) | — | Read API for Patient, Encounter, Condition, AllergyIntolerance, Observation |
