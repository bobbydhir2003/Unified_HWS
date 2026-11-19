import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routers import (
    admin,
    adt,
    ai,
    analytics,
    auth,
    billing,
    clinical,
    command,
    documents,
    facilities,
    health,
    insurance,
    live,
    messages,
    operations,
    orders,
    patients,
    portal,
    scheduling,
    scribe,
    telehealth,
    workspace,
)
from app.core.config import settings
from app.core.hardening import (
    Metrics,
    RateLimiter,
    production_problems,
    rate_limit_bucket,
    route_template,
    too_many,
)
from app.core.logging import configure_logging
from app.integrations import fhir
from app.services.audit import client_ip

configure_logging()
log = logging.getLogger("undeclared.api")

_problems = production_problems(settings)
if _problems:  # fail fast: never boot production with unsafe configuration
    raise RuntimeError("Unsafe production configuration: " + "; ".join(_problems))

limiter = RateLimiter()
if settings.engine_inprocess_scheduler and not settings.is_production:
    from app.engine.scheduler import start as _start_scheduler

    _start_scheduler()
metrics = Metrics()

app = FastAPI(
    title="Undeclared API",
    version="1.0.0",
    docs_url="/api/v1/docs" if not settings.is_production else None,
    openapi_url="/api/v1/openapi.json" if not settings.is_production else None,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    start = time.perf_counter()
    bucket = rate_limit_bucket(request.url.path) if settings.rate_limit_enabled and request.method == "POST" else None
    if bucket:
        ip = client_ip(request) or "unknown"
        ok, retry = limiter.allow((ip, bucket), settings.rate_limit_auth_per_minute)
        if not ok:
            log.warning("rate limited", extra={"request_id": rid, "path": request.url.path, "status": 429})
            return too_many(retry)
    response = await call_next(request)
    metrics.observe(request.method, route_template(request), response.status_code, time.perf_counter() - start)
    response.headers["x-request-id"] = rid
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["referrer-policy"] = "no-referrer"
    response.headers["cache-control"] = response.headers.get("cache-control", "no-store")
    # Path only (no query string) — query params may contain identifiers or search terms.
    log.info("request", extra={"request_id": rid, "method": request.method, "path": request.url.path,
                               "status": response.status_code,
                               "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    """FHIR clients expect OperationOutcome resources; everyone else gets the standard {"detail": ...}."""
    if request.url.path.startswith(("/api/fhir/", "/api/v1/fhir/")):
        msg = exc.detail if isinstance(exc.detail, str) else (exc.detail or {}).get("message", "Error")
        code = {401: "login", 403: "forbidden", 404: "not-found"}.get(exc.status_code, "processing")
        return JSONResponse(status_code=exc.status_code, media_type="application/fhir+json",
                            content={"resourceType": "OperationOutcome", "issue": [{"severity": "error", "code": code, "diagnostics": msg}]})
    return await http_exception_handler(request, exc)


@app.exception_handler(IntegrityError)
async def integrity_handler(request: Request, exc: IntegrityError):
    msg = str(exc.orig).split("\n")[0] if exc.orig else "constraint violation"
    if "appointments_no_provider_overlap" in msg:
        msg = "This provider already has an appointment in that time slot."
    elif "signed clinical note" in msg or "append-only" in msg or "signed note" in msg:
        msg = "Signed clinical records cannot be modified."
    else:
        log.warning("integrity error", extra={"path": request.url.path})
        msg = "The request conflicts with existing data."
    return JSONResponse(status_code=409, content={"detail": msg})


@app.get("/api/metrics", include_in_schema=False)
async def prometheus_metrics(request: Request):
    """Prometheus scrape endpoint. Restrict at the network layer (internal only) in production."""
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")


ROUTERS = [health, auth, admin, facilities, live, operations, insurance, command, adt, patients, scheduling, clinical, workspace, documents, scribe, orders, portal, messages,
           telehealth, billing, ai, analytics]

# Versioned API (documented). The unversioned /api prefix remains as a hidden compatibility alias so existing
# clients, webhooks and bookmarks keep working; new clients must use /api/v1.
for r in ROUTERS:
    app.include_router(r.router, prefix="/api/v1")
app.include_router(fhir.router, prefix="/api/v1")
for r in ROUTERS:
    app.include_router(r.router, prefix="/api", include_in_schema=False)
app.include_router(fhir.router, prefix="/api", include_in_schema=False)
