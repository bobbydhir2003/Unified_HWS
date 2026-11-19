# Database design

PostgreSQL 16. UUID primary keys, `timestamptz` everywhere, Alembic migrations in `backend/alembic/versions`.

## Conventions

- Every tenant-owned table has `organization_id → organizations.id` (indexed).
- Constraint names follow the `NAMING` convention in `models/base.py`.
- Enumerations are `varchar` + `CHECK` constraints (easy to evolve via migration).
- Soft-retire clinical list entries with `status = 'entered_in_error'` instead of deleting.

## Entities (phases 0–4)

| Area | Tables |
|---|---|
| Tenancy | `organizations`, `clinics` |
| Identity | `users`, `memberships`, `membership_roles`, `membership_clinics`, `provider_profiles`, `user_sessions`, `invitations`, `password_reset_tokens` |
| Messaging | `outbound_messages` (simulated outbox), `notifications` |
| Audit | `audit_events` |
| Patients | `patients`, `patient_insurances`, `patient_access_grants`, `patient_notes` |
| Scheduling | `appointment_types`, `provider_availability`, `appointments` |
| Documents & AI | `scribe_sessions`, `documents` (status, AI draft fields, match candidates, reviewer), `ai_jobs` (provider, model, PHI-sent flag, tokens, latency, error) |
| Clinical | `encounters`, `encounter_diagnoses`, `vital_signs`, `allergies`, `patient_medications`, `problems`, `history_entries`, `clinical_templates`, `clinical_notes`, `clinical_note_versions`, `note_addenda` |

## Integrity enforced by the database

| Rule | Mechanism (migration `0001`) |
|---|---|
| Audit log is append-only | `BEFORE UPDATE OR DELETE` trigger on `audit_events` raises |
| Note versions/addenda are immutable | same trigger on `clinical_note_versions`, `note_addenda` |
| Signed notes can't change | trigger `freeze_signed_note` on `clinical_notes` |
| No versions after signing | trigger `forbid_version_on_signed` |
| No provider double-booking | `EXCLUDE USING gist (provider_id WITH =, tstzrange(start_at,end_at) WITH &&) WHERE status NOT IN ('cancelled','no_show')` |
| One encounter per appointment | `UNIQUE (appointment_id)` on `encounters` |
| MRN unique per org | `UNIQUE (organization_id, mrn)`; allocated from a row-locked counter in `organizations.settings` |
| Vital sign ranges | `CHECK` constraints |

## Indexes worth knowing

- `ix_patients_name_trgm` (GIN trigram) for fuzzy name search and duplicate detection.
- `ix_patients_org_dob`, `ix_patients_org_name` for exact lookups.
- `ix_appointments_org_start`, `ix_appointments_provider_start` for calendar ranges.

## Note versioning model

`clinical_notes.content` mirrors the latest version for fast reads. Each explicit save inserts `clinical_note_versions(version = n+1)`. Optimistic concurrency: clients send `expected_version`; mismatches return 409. Signing inserts a final `source='sign'` version and flips `status` to `signed`, after which the row is frozen.

## Migrations

| Rev | Content |
|---|---|
| `0001` | Core schema (identity, patients, scheduling, clinical) + extensions + integrity triggers + exclusion constraint |
| `0002` | Notifications |
| `0004` | Scribe sessions (consent method/time, transcript, draft, applied note version, audio retention) |
| `0003` | Documents, AI jobs (`CHECK status <> 'filed' OR patient_id IS NOT NULL`) |

Objects managed by hand-written SQL (`ix_patients_name_trgm`, the exclusion constraint) are excluded from autogenerate in `alembic/env.py`.
