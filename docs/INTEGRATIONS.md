# Integrations

Every external dependency sits behind an adapter. Until a real, contracted and validated partner is connected, the adapter is **simulated**: deterministic, offline, and labeled `Simulated` in the UI and API.

| Integration | Status | Adapter / location | Production path |
|---|---|---|---|
| Email | Simulated (DB outbox, Admin › Message outbox) | `services/identity.send_email` | SES / SendGrid with BAA |
| SMS reminders | Simulated (beat task writes outbox) | `tasks.send_appointment_reminders` | Twilio with BAA |
| Insurance eligibility (270/271) | Simulated (member IDs ending in 0 → inactive) | `patients.check_eligibility` | Clearinghouse (e.g., Availity, Change) |
| Object storage | Local disk or S3 | `services/storage.py` | S3 with SSE-KMS, private bucket |
| ICD-10-CM | Built-in common subset | `data/icd10_common.py` | Import annual CMS release into a table |
| AI (LLM/OCR/ASR) | Planned: simulated default | `app/ai/` | Provider with BAA; PHI gate `AI_PHI_ALLOWED` |
| e-Prescribing | Planned (phase 7), simulated | — | Surescripts-certified partner |
| Labs (HL7 v2 ORM/ORU) | Planned (phase 7), simulated | — | Lab interface engine / partner |
| Clearinghouse claims (837/835) | Planned (phase 9), simulated | — | Clearinghouse partner |
| Payments | Planned (phase 9), simulated | — | PCI-compliant processor (tokenized) |
| Telehealth video | Planned (phase 8) | — | Established WebRTC SDK with BAA |
| Telephony / AI receptionist | Planned (phase 10), sandbox | — | Telephony provider with BAA |
| FHIR R4 | Planned (phase 12) | — | Read API for Patient, Encounter, Condition, AllergyIntolerance, Observation |
