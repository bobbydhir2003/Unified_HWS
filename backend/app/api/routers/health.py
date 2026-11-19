import time

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine

router = APIRouter(tags=["health"])


def _timed(fn) -> dict:
    t = time.perf_counter()
    try:
        detail = fn()
        return {"ok": True, "latency_ms": round((time.perf_counter() - t) * 1000, 1), **({"detail": detail} if detail else {})}
    except Exception as e:  # noqa: BLE001 - health checks report, never raise
        return {"ok": False, "error": type(e).__name__}


def _db():
    with engine.connect() as c:
        c.execute(text("select 1"))


def _redis():
    if settings.celery_eager:
        return "skipped (eager mode)"
    import redis

    redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1).ping()


def _storage():
    from app.services.storage import storage

    storage.check()


def dependency_checks() -> dict:
    return {"database": _timed(_db), "redis": _timed(_redis), "storage": _timed(_storage)}


@router.get("/health")
def health():
    """Liveness: the process is up."""
    return {"status": "ok", "service": "undeclared-api"}


@router.get("/health/ready")
def ready(response: Response):
    """Readiness: dependencies reachable."""
    checks = dependency_checks()
    ok = all(c["ok"] for c in checks.values())
    response.status_code = 200 if ok else 503
    return {"status": "ok" if ok else "degraded", "checks": checks}
