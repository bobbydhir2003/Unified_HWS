# Deployment

> Nothing has been deployed. This describes the intended production shape and how to stand it up. Applying the
> Terraform creates billable AWS resources; do it only with authorization, a BAA with AWS, and the
> [production readiness checklist](PRODUCTION_READINESS.md) complete.

## Topology (AWS reference — `infra/aws/`)

```
Internet ─TLS─▶ ALB (TLS 1.2+/1.3, ACM cert, drops invalid headers)
                 └─▶ web (ECS Fargate, nginx: SPA + CSP/HSTS, proxies /api) ─▶ api (ECS Fargate, FastAPI)
                                                                                 ├─▶ RDS PostgreSQL 16 (KMS, Multi-AZ, PITR 14 d, TLS forced)
                                                                                 ├─▶ ElastiCache Redis (KMS, TLS)  ◀── worker (Celery + beat)
                                                                                 └─▶ S3 documents (SSE-KMS, versioned, private, TLS-only)
Secrets Manager (SECRET_KEY, DATABASE_URL, REDIS_URL) · CloudWatch Logs (90 d, KMS) · AWS Backup (daily, 35 d) · VPC flow logs
```

All data stores sit in private subnets; only the ALB is public.

## Steps

1. **Prerequisites:** AWS account under BAA, Route 53/DNS for the domain, ACM certificate, remote Terraform state (S3 + DynamoDB lock; see the commented `backend` block).
2. **Infrastructure:** `cd infra/aws && terraform init && terraform plan -var domain=app.example.org -var acm_certificate_arn=... -var image_tag=<sha>` → review → `apply`.
   *The Terraform has not been validated in this environment (no terraform binary); run `terraform validate` first.*
3. **Images:** CI builds `backend/Dockerfile` and `frontend/Dockerfile`, tags with the git SHA, pushes to the two ECR repositories (immutable tags, scan on push).
4. **Service discovery:** enable ECS Service Connect (or Cloud Map) so the `web` container's nginx resolves `api:8000`.
5. **Migrations:** run `alembic upgrade head` as a one-off ECS task with the api image before shifting traffic (the api container also runs it on start; with multiple replicas prefer the one-off task).
6. **First admin:** create the platform super admin with a one-off task (do not run `app.seed` in production — it is synthetic demo data).
7. **Verify:** `GET /api/health/ready`, sign in, check System status (adapters = simulated, PHI-to-AI blocked).

## Production configuration

The API refuses to start with `ENVIRONMENT=production` unless: strong `SECRET_KEY` (≥32 chars, not a default), `COOKIE_SECURE=true`, `CELERY_EAGER=false`, `STORAGE_BACKEND=s3`, HTTPS `CORS_ORIGINS`, `ENFORCE_MFA=true` (see `app/core/hardening.py`).

| Variable | Production value |
|---|---|
| `ENVIRONMENT` | `production` |
| `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL` | from Secrets Manager |
| `STORAGE_BACKEND` / `S3_BUCKET` | `s3` / bucket output |
| `COOKIE_SECURE`, `ENFORCE_MFA` | `true` |
| `AI_PROVIDER` / `AI_PHI_ALLOWED` | `simulated` / `false` until an AI BAA + review |
| `*_ADAPTER` | `simulated`/`outbox` until certified vendors are integrated |
| `RATE_LIMIT_AUTH_PER_MINUTE` | `20` (plus WAF rate rules at the edge) |

## Local / single-host

`docker compose up --build` (web :8080, API :8011). See the README for running processes directly.
