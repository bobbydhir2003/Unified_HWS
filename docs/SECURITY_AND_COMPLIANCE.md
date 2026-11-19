# Security & compliance

**Status: development prototype with synthetic data.** Undeclared is not HIPAA-compliant, not ONC-certified, and not validated for clinical use. Do not load real PHI until the "Before real PHI" checklist below is complete.

## Implemented controls

| Control | Implementation |
|---|---|
| Authentication | Argon2id hashes; 10+ char passwords with 3 character classes; lockout after 5 failures/15 min |
| Sessions | 15-min JWT in memory; rotating refresh token (hashed at rest, httpOnly SameSite=Strict cookie); server-side revocation; "sign out other sessions" on password change; all sessions revoked on reset |
| MFA | TOTP enrollment/verification; `ENFORCE_MFA=true` blocks privileged roles until enrolled |
| Authorization | Role → permission map; every endpoint checks permissions server-side; denials audited |
| Tenant isolation | `organization_id` on all tenant rows; enforced in `TenantContext`; cross-tenant ids return 404; regression-tested |
| Patient-level access | Restricted charts need primary-provider status, a grant, or time-limited break-the-glass with mandatory reason (audited) |
| Portal patients | Can read only the record linked to their user |
| Audit | Append-only `audit_events` (DB trigger) for sign-in, chart view, every clinical/admin write, denials |
| Clinical integrity | Versioned notes; signed notes frozen by trigger; addenda only; AI content requires attestation before signing |
| Logging | JSON logs with request id, method, path (no query string), status, latency — no bodies or PHI |
| Transport headers | `nosniff`, `no-referrer`, `no-store`; nginx adds `X-Frame-Options: DENY` |
| Account enumeration | Forgot-password returns identical responses |
| Storage | Documents (phase 5) in object storage, served only through authorized API; S3 adapter uses SSE |
| Simulation | Email/SMS go to an outbox; eligibility checks are deterministic simulations, labeled in UI |

## Regression tests (backend/tests)

Authentication, lockout, refresh rotation/revocation, MFA, reset non-enumeration, role authorization, tenant isolation (data + header spoofing), restricted chart/break-glass, portal scoping, audit immutability, appointment conflicts (app + DB), note signing rules, AI attestation, encounter completion.

## Known gaps / planned hardening

- PostgreSQL row-level security as a second isolation layer.
- Rate limiting at the edge (login, search) — currently only lockout.
- CSRF: refresh endpoint relies on SameSite=Strict; add an origin check before cross-site deployments.
- Field-level encryption for especially sensitive fields; KMS-managed keys.
- Automated dependency/container scanning in CI; SAST.
- Session idle timeout UI; configurable password policy per org.
- Formal audit-log export and retention policy.

## Before real PHI (non-exhaustive)

1. Business Associate Agreements with hosting, email/SMS, AI, telehealth vendors.
2. HIPAA risk analysis, policies, workforce training, incident response plan.
3. Encryption at rest (RDS/S3 with KMS), TLS everywhere, secrets in a manager.
4. Backups with tested restore; documented RPO/RTO.
5. Penetration test and remediation.
6. `AI_PHI_ALLOWED` stays false unless a BAA covers the AI provider and data-flow review is complete.
7. Clinical safety review for AI features; ONC certification if required for the intended market.
