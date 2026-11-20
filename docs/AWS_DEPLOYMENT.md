# AWS EC2 deployment

Single-host deployment of Undeclared HMS for demonstration with **synthetic data only**. It runs as `ENVIRONMENT=staging`:
the application's production guard (`app/core/hardening.py`) deliberately refuses `production` without S3 document
storage, HTTPS and enforced MFA, and those are not provisioned here. Not HIPAA-compliant, not clinically certified.

| Item | Value |
|---|---|
| **URL** | **https://3-19-143-26.sslip.io** (Let's Encrypt certificate via Caddy, auto-renewed; HTTP → HTTPS 308) |
| Instance | `i-0a190b3478787307c` · `us-east-2` · t3.small (2 vCPU, 2 GB RAM) · Ubuntu 26.04 · x86_64 |
| Public IP | `3.19.143.26` (SSH user `ubuntu`, key pair `Unified_HMS`) |
| SSH host key | ED25519 `SHA256:/pmXdiEG8fd1byly2xmWmJNU3Ew9dGbCbSHnYphkxw4` (verified against the EC2 system log) |
| Repository | https://github.com/bobbydhir2003/Unified_HWS (branches `dev`, `main`) |
| App directory | `/opt/undeclared` (`docker-compose.yml`, `Caddyfile`, `.env` mode 600, `backups/`) |
| Deployment files | `deploy/ec2/` in the repository |

## Architecture

```
Internet ──443/80──▶ caddy (TLS, profile "https") ──▶ web (nginx: React build + /api proxy) ──▶ api (FastAPI, 1 uvicorn)
                                                                                              ├─▶ db (PostgreSQL 16, volume pgdata)
SSH tunnel ──▶ 127.0.0.1:8080 ──▶ web                                                         ├─▶ redis (broker, 64 MB)
                                                                                              └─ worker (Celery worker + beat, concurrency 1,
                                                                                                 queues default,engine,ai)
```

* Only Caddy publishes ports (80/443), and only when HTTPS is enabled. `web` is bound to `127.0.0.1:8080` for SSH-tunnel
  access. PostgreSQL, Redis, the API port and Celery are never published.
* Memory limits: db 384 MB, api 640 MB, worker 512 MB, redis 96 MB, caddy 128 MB, web 64 MB; 1 GB swap file.
* Images are built **off the instance** (`docker buildx --platform linux/amd64`) and loaded with `docker load`, so the
  2 GB host never runs `npm ci`/`uv sync`.
* Migrations (`alembic upgrade head`) run on every API start. Seeding is an explicit, one-time step.
* Restart policy `unless-stopped` + Docker enabled at boot; health checks on db, redis, api (`/api/health`) and worker
  (`celery inspect ping`).

## Initial setup (already done on this instance)

```bash
scp deploy/ec2/server-setup.sh ubuntu@3.19.143.26:/tmp/ && ssh ubuntu@3.19.143.26 bash /tmp/server-setup.sh
```
Installs `docker.io` + `docker-compose-v2` from Ubuntu's archive, adds 1 GB swap, enables `ufw` (OpenSSH, 80, 443), creates
`/opt/undeclared` and generates `/opt/undeclared/.env` with fresh random secrets (never overwritten on re-run).

### Environment variables (`/opt/undeclared/.env`, names only)

`RELEASE`, `ENVIRONMENT`, `POSTGRES_PASSWORD`, `DATABASE_URL`, `REDIS_URL`, `CELERY_EAGER`, `ENGINE_INPROCESS_SCHEDULER`,
`SECRET_KEY`, `CREDENTIALS_ENCRYPTION_KEY`, `COOKIE_SECURE`, `CORS_ORIGINS`, `FRONTEND_URL`, `STORAGE_BACKEND`,
`STORAGE_LOCAL_PATH`, `AI_PROVIDER`, `AI_PHI_ALLOWED`, `RATE_LIMIT_ENABLED`, `SEED_ON_START`, `SEED_DEMO_PASSWORD`,
`SITE_ADDRESS`, `ENABLE_HTTPS`.

* `CREDENTIALS_ENCRYPTION_KEY` encrypts the OpenAI key stored through Super Admin → AI settings. It persists in `.env`
  across restarts and deployments. **Back up `.env` securely**; losing this key makes the stored AI key unreadable (re-enter it).
* `SEED_DEMO_PASSWORD` is the password of every seeded demo account on this server (the repository's default is refused
  for staging/production). Read it on the server: `ssh ubuntu@3.19.143.26 "grep ^SEED_DEMO_PASSWORD /opt/undeclared/.env"`.
* No OpenAI key is configured by deployment. Enter it in the UI after HTTPS works.

### Seed synthetic demo data (once)
```bash
cd /opt/undeclared && sudo docker compose run --rm api python -m app.seed      # no-op if already seeded; --reset is refused here
```

## Deploy / update

From the repository root on a machine with Docker (clean working tree):
```bash
EC2_HOST=3.19.143.26 EC2_KEY=~/Downloads/Unified_HMS.pem EC2_KNOWN_HOSTS=~/.ssh/known_hosts deploy/ec2/deploy.sh
```
Builds `undeclared-api:<commit>` / `undeclared-web:<commit>`, ships them, copies compose/Caddyfile/backup script, sets
`RELEASE`, runs `docker compose up -d` (migrations run on API start), keeps the current and previous images.

**Rollback:** `cd /opt/undeclared && sed -i "s/^RELEASE=.*/RELEASE=$(cat .previous_release)/" .env && sudo docker compose up -d`.
(Only roll back across releases without new migrations, or restore the pre-deploy backup.) Take a backup before every deploy.

### Everyday commands (on the server, in `/opt/undeclared`)
```bash
sudo docker compose ps                      # status + health
sudo docker compose logs -f --tail=100 api  # logs (api|worker|web|db|redis|caddy)
sudo docker compose restart api worker      # restart services
sudo docker compose exec api alembic current
sudo docker stats --no-stream               # memory use
```

## Access

**Public:** https://3-19-143-26.sslip.io. `sslip.io` is a free wildcard DNS service: `3-19-143-26.sslip.io` resolves to
`3.19.143.26`. No domain was purchased. If the instance's public IP changes (stop/start without an Elastic IP), the hostname
changes too: update `SITE_ADDRESS`, `CORS_ORIGINS` and `FRONTEND_URL`, then run `sudo docker compose --profile https up -d`.

Demo accounts (synthetic data): the same emails as local development (`admin@undeclared.dev`, `hospitaladmin@harborview.dev`,
`dr.chen@harborview.dev`, …). The password is **not** the repository default; it is `SEED_DEMO_PASSWORD` in the server's `.env`.

### Admin access without the public site: SSH tunnel
```bash
ssh -i ~/Downloads/Unified_HMS.pem -N -L 8080:127.0.0.1:8080 ubuntu@3.19.143.26
# then open http://localhost:8080   (localhost is a secure context: secure cookies and the microphone work)
```

### Enable public HTTPS (done 2026-11-20 for 3-19-143-26.sslip.io)
1. Security group: allow inbound **TCP 80 and 443** from `0.0.0.0/0` (80 is needed for the Let's Encrypt challenge and
   redirects). Restrict **TCP 22** to your own IP. Never open 5432, 6379, 8000.
2. Pick a hostname that resolves to `3.19.143.26`: your own domain's A record, or (free, no account)
   `3-19-143-26.sslip.io`.
3. In `/opt/undeclared/.env`: `SITE_ADDRESS=<hostname>`, `ENABLE_HTTPS=true`,
   `CORS_ORIGINS=["https://<hostname>","http://localhost:8080"]`, `FRONTEND_URL=https://<hostname>`.
4. `sudo docker compose --profile https up -d` — Caddy obtains the certificate and redirects HTTP→HTTPS.
5. Only then enter the OpenAI key (Super Admin → AI settings → Test connection) and try Realtime Voice from the browser.

## Demo mode — one-click role sign-in (enabled on this deployment for product demonstrations)

`DEMO_MODE=true` in `/opt/undeclared/.env` shows a **Demo Access** box under the Sign In button. Each button signs in to
that role's synthetic account with one click (`POST /api/v1/auth/demo-login`), creating a normal session; role
permissions and the audit log are unchanged. Every demo sign-in is recorded as `auth.demo_login`.

Buttons (compact box under Sign In): Doctor, Nurse, Front Desk, Clinic Admin, Billing, Patient, Super Admin. The other
roles (hospital admin, pharmacist, laboratory, radiology, bed manager, insurance) remain in the application with normal
password sign-in; they aren't on the one-click list.

**Safeguards:**
* **Production guard:** the app refuses to start with `DEMO_MODE` on when `ENVIRONMENT=production`.
* **Allowlist:** only the server-side list in `backend/app/core/demo.py` can be used, and only when every organization the
  account belongs to is flagged `synthetic_data`. Accounts with MFA enabled are refused.
* **Super Admin button:** uses a dedicated `superadmin.demo@harborview.dev` account with the super_admin role inside the
  demo organization. It is not a platform administrator and sees only its own organization. The real platform
  administrator (`admin@undeclared.dev`) is never on the list and keeps normal password sign-in, for real administration.
* **Blocked for demo accounts:** AI settings and key changes, connection tests, organization, facility, staff, invitation
  and scheduling-setup changes, agent, monitor and workflow configuration, password and MFA changes, and profile edits.
  They get "This action is disabled in the demonstration environment."
* **Hidden from demo accounts:** the message outbox (it can contain password-reset links); password resets for demo
  accounts are also suppressed. The stored AI key's hint is never shown to them.
* **Allowed:** clinical and operational workflows on synthetic data (register patients, document, order, admit, discharge,
  bill, run agents), so the demo is realistic.

**Turn off:** set `DEMO_MODE=false` and run `sudo docker compose --profile https up -d`.

**Caution:** if an OpenAI key is configured while demo mode is on, any visitor can use AI features, and that usage is
billed to your OpenAI account. Turn demo mode off, or monitor usage under AI governance.

Local development: the dev server's own quick-login box (fills in the dev password) is still shown when the server's demo
mode is off.

## Verification (2026-11-20)

`e2e/deploy_smoke.py` against the public URL (`BASE=https://3-19-143-26.sslip.io DEMO_PASSWORD=… python e2e/deploy_smoke.py`):
26/26 passed.
* **Platform:** readiness (database, Redis, storage).
* **Authentication:** login and logout, Secure + HttpOnly refresh cookie, token refresh, wrong password refused.
* **Role checks:** doctor → Command Center 403; patient → staff patients 403; doctor → AI settings 403.
* **Hospital features:** patient search, bed board, ED board, Command Center tiles matching the bed board, pharmacy
  inventory, Insurance Guardian summary and cases, patient portal.
* **Automation:** healthy (worker + beat dispatching).
* **AI:** AI settings (key not configured, dedicated encryption key, no key material in the response); provider status
  `simulated`; Realtime Voice status and session endpoint in `simulated` mode; Hospital Operations agent (rule-based).
* **Edge:** live-update stream delivers its first frame in 0.2 s through Caddy and nginx; HSTS and CSP headers present.

Other checks:
* **Certificate:** CN `3-19-143-26.sslip.io`, issuer Let's Encrypt.
* **Closed ports:** 5432/6379/8000/8080 are unreachable from the internet.
* **Restart:** full stack restart keeps all data; every service comes back healthy.
* **Memory:** about 330 MB across containers at idle; 1 GB of swap unused.

## Backups

`/opt/undeclared/backup.sh` (cron, daily 03:15 UTC): `pg_dump` custom format + document-storage tarball + SHA-256
checksums in `/opt/undeclared/backups`, 7-day retention. Copy them off the instance (`scp ubuntu@3.19.143.26:/opt/undeclared/backups/* .`).

**Restore** into an empty database:
```bash
cd /opt/undeclared && sudo docker compose stop api worker
sudo docker compose exec -T db psql -U undeclared -d postgres -c "create database undeclared_restore"
sudo docker compose exec -T db pg_restore -U undeclared -d undeclared_restore --no-owner < backups/undeclared-<stamp>.dump
# verify, then point DATABASE_URL at undeclared_restore (or rename databases) and start api/worker again
```
Never restore over the live database without a fresh backup.

## Troubleshooting

| Symptom | Check |
|---|---|
| API unhealthy | `docker compose logs api` — migrations run first; "Unsafe production configuration" means `ENVIRONMENT=production` without its prerequisites |
| Worker unhealthy | `docker compose logs worker`; Redis healthy? |
| Out of memory | `docker stats`, `free -m`; containers restart automatically; consider t3.medium (4 GB) |
| Disk full | `df -h /`, `docker system df`; `docker image prune`; old backups |
| Certificate not issued | ports 80/443 open in the security group? `SITE_ADDRESS` resolves to the IP? `docker compose logs caddy` |
| Login cookie missing over plain HTTP | expected — `COOKIE_SECURE=true`; use HTTPS or the SSH tunnel (localhost) |

## Known limitations

* t3.small: 2 GB RAM is enough for one API process and a single-concurrency worker at demo load. Root disk is 6.7 GB
  (≈4 GB free after images); grow the EBS volume to 20 GB before storing many documents or backups.
* Single instance, single disk: no high availability; backups are local until copied off.
* Documents are stored on a local Docker volume (S3 is required for `production`).
* Payers, clearinghouse, PACS, e-prescribing, SMS/email and card payments are simulated (labeled in the UI).
* Live OpenAI (text and Realtime Voice) not validated until a key is entered over HTTPS.
