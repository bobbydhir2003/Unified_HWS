import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.routers import (
    admin,
    auth,
    clinical,
    documents,
    health,
    messages,
    orders,
    patients,
    portal,
    scheduling,
    scribe,
    telehealth,
    workspace,
)
from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()
log = logging.getLogger("undeclared.api")

app = FastAPI(
    title="Undeclared API",
    version="0.1.0",
    docs_url="/api/docs" if not settings.is_production else None,
    openapi_url="/api/openapi.json" if not settings.is_production else None,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["referrer-policy"] = "no-referrer"
    response.headers["cache-control"] = response.headers.get("cache-control", "no-store")
    # Path only (no query string) — query params may contain identifiers or search terms.
    log.info("request", extra={"request_id": rid, "method": request.method, "path": request.url.path,
                               "status": response.status_code,
                               "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
    return response


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


API = "/api"
app.include_router(health.router, prefix=API)
app.include_router(auth.router, prefix=API)
app.include_router(admin.router, prefix=API)
app.include_router(patients.router, prefix=API)
app.include_router(scheduling.router, prefix=API)
app.include_router(clinical.router, prefix=API)
app.include_router(workspace.router, prefix=API)
app.include_router(documents.router, prefix=API)
app.include_router(scribe.router, prefix=API)
app.include_router(orders.router, prefix=API)
app.include_router(portal.router, prefix=API)
app.include_router(messages.router, prefix=API)
app.include_router(telehealth.router, prefix=API)
