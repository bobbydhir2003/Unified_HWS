# Production readiness checklist

Status legend: ✅ done in code · 🟡 partially / needs configuration · ⬜ not done (blocks real-PHI use)

**Undeclared is not HIPAA-compliant or clinically certified today.** This list is what stands between the current build and real patients.

## Legal & compliance
- ⬜ HIPAA risk analysis, policies & procedures, workforce training, sanctions policy
- ⬜ BAAs: AWS, email/SMS, telehealth video, AI provider, telephony/ASR, fax, clearinghouse, eRx, labs, payment processor
- ⬜ ONC Health IT certification (if needed for the market / incentive programs); CEHRT criteria review
- ⬜ State-specific requirements (e.g. consent for recording, minors' records, 42 CFR Part 2 for SUD data)
- ⬜ Clinical safety review of AI features (scribe, document AI, assistant, receptionist) with sign-off
- ⬜ CPT license (AMA) and full ICD-10-CM import; licensed drug database for interaction checking

## Security
- ✅ Argon2id passwords, lockout, rotating revocable sessions, TOTP MFA (+ enforcement flag)
- ✅ Role permissions, tenant isolation, patient-level restriction + break-glass, all regression-tested
- ✅ Append-only audit log (DB trigger), immutable signed notes and versions
- ✅ Rate limiting on auth & webhooks (per process) · 🟡 add WAF/edge rate limits for multi-replica
- ✅ CSP (hash-pinned inline script, no eval), HSTS, frame denial, nosniff — verified with zero violations
- ✅ Production configuration guard (refuses unsafe settings at startup)
- ✅ Encrypted transport & storage in the AWS reference (KMS, TLS-only S3, forced SSL on RDS) · ⬜ not yet deployed
- ⬜ PostgreSQL row-level security as a second tenancy layer
- ⬜ Penetration test + remediation; dependency & container scanning in CI (ECR scan-on-push configured)
- ⬜ Session idle timeout UI and admin-configurable password policy
- ⬜ SSO (SAML/OIDC) for staff

## Reliability & operations
- ✅ Health/readiness endpoints, structured logs, Prometheus metrics, AI job monitoring
- ✅ Backup & restore scripts with a completed local drill · 🟡 automate restore drills in staging
- 🟡 AWS reference Terraform written — not validated or applied
- ⬜ Alerting wired to on-call; SLOs defined
- ⬜ Load test (scheduling, chart open, document pipeline)
- 🟡 Telehealth: production video vendor with TURN (current P2P/STUN works only on simple networks)
- 🟡 Signaling/notifications use polling; consider WebSockets/SSE at scale

## Integrations (all simulated today)
- ⬜ eRx (Surescripts-certified partner; EPCS for controlled substances)
- ⬜ Lab/imaging interfaces (HL7 v2 / FHIR), results ingestion → `lab_results(source='interface')`
- ⬜ Clearinghouse (837/835/277CA, 270/271 eligibility)
- ⬜ Payment processor with hosted fields (card data never touches our servers)
- ⬜ Email/SMS vendor; fax vendor; telephony + ASR for the receptionist; speech-to-text for the scribe
- 🟡 FHIR R4 read API implemented — ⬜ SMART on FHIR authorization, US Core conformance tests, bulk export

## Data
- ✅ Synthetic-only data; organizations flagged `synthetic_data` show a banner; simulators are disabled for non-synthetic orgs
- ⬜ Data migration tooling from the incumbent EHR
- ⬜ Record retention & legal hold policies implemented in code
