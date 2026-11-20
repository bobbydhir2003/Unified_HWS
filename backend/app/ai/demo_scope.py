"""Session-scoped AI configuration for demo accounts (DEMO_MODE only).

A demo request (signed in through a one-click demo account) resolves AI settings from its OWN scope, never from the
platform configuration:
  1. the session's DemoAISettings row (visitor-entered key/models; expires with the session, max DEMO_AI_TTL_HOURS);
  2. otherwise DEMO_OPENAI_API_KEY, if the operator configured a dedicated demo project;
  3. otherwise the labeled simulation.
The scope is held in a context variable for the request (set by middleware) and passed explicitly to Celery tasks.
Every OpenAI call made under a demo scope goes through `guard()` — per-session hourly request cap, concurrency cap and
cost cap, plus a global cap on the shared demo key. Keys are Fernet-encrypted at rest and never returned or logged.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta

from app.ai.config import EffectiveAI
from app.core.config import settings

SHARED = "shared"
_scope: ContextVar[tuple[str, EffectiveAI] | None] = ContextVar("demo_ai_scope", default=None)


from app.ai.provider import AIError  # noqa: E402


class DemoLimitError(AIError):
    pass


# ---------------------------------------------------------------------------------------------- resolution

def _default() -> EffectiveAI:
    if settings.demo_openai_api_key:
        return EffectiveAI(provider="openai", api_key=settings.demo_openai_api_key, key_hint=None, source="demo-project",
                           text_model=settings.demo_ai_text_model, vision_model=settings.demo_ai_text_model,
                           transcription_model=settings.ai_transcription_model, realtime_model=settings.demo_ai_realtime_model)
    return EffectiveAI(provider="simulated", source="demo")


def load_row(db, session_id: uuid.UUID):
    from sqlalchemy import select

    from app.core.security import now
    from app.models import DemoAISettings

    return db.scalar(select(DemoAISettings).where(DemoAISettings.session_id == session_id, DemoAISettings.expires_at > now()))


def from_row(row) -> EffectiveAI:
    from app.core.crypto import decrypt

    key = None
    if row.api_key_encrypted:
        try:
            key = decrypt(row.api_key_encrypted)
        except ValueError:
            key = None
    if row.provider == "openai" and not key:  # no own key: fall back to the demo project key, never the platform key
        key = settings.demo_openai_api_key
    return EffectiveAI(provider=row.provider, api_key=key, key_hint=None, source="demo-session",
                       text_model=row.text_model or "", vision_model=row.vision_model or row.text_model or "",
                       transcription_model=row.transcription_model or "", realtime_model=row.realtime_model or "",
                       agent_models=dict(row.agent_models or {}))


def resolve(token: str | None) -> EffectiveAI | None:
    """token: 'sess:<session uuid>' for a demo session; None for non-demo work (→ platform settings)."""
    if not token:
        return None
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        row = load_row(db, uuid.UUID(token.split(":", 1)[1])) if token.startswith("sess:") else None
    finally:
        db.close()
    return from_row(row) if row else _default()


def current() -> EffectiveAI | None:
    v = _scope.get()
    return v[1] if v else None


def current_token() -> str | None:
    v = _scope.get()
    return v[0] if v else None


@contextmanager
def use(token: str | None, eff: EffectiveAI | None = None):
    """Run a block under a demo scope (no-op for None)."""
    if not token:
        yield
        return
    t = _scope.set((token, eff or resolve(token)))
    try:
        yield
    finally:
        _scope.reset(t)


def set_for_request(token: str, eff: EffectiveAI) -> None:
    _scope.set((token, eff))


def expiry(session_expires_at):
    from app.core.security import now

    cap = now() + timedelta(hours=settings.demo_ai_ttl_hours)
    return min(cap, session_expires_at) if session_expires_at else cap


def cleanup(db) -> int:
    """Delete expired demo AI settings (and with them any visitor key). Run by the beat scheduler."""
    from sqlalchemy import delete

    from app.core.security import now
    from app.models import DemoAISettings

    n = db.execute(delete(DemoAISettings).where(DemoAISettings.expires_at <= now())).rowcount or 0
    db.commit()
    return n


# ---------------------------------------------------------------------------------------------- limits

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)
_cost: dict[str, float] = defaultdict(float)
_sems: dict[str, threading.BoundedSemaphore] = {}


def _take(key: str, limit: int, window: float = 3600.0) -> bool:
    t = time.monotonic()
    q = _hits[key]
    while q and q[0] <= t - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(t)
    return True


@contextmanager
def guard():
    """Wrap every outbound AI call. No-op outside a demo scope."""
    v = _scope.get()
    if not v:
        yield
        return
    token, eff = v
    shared = eff.source == "demo-project" or (eff.api_key and eff.api_key == settings.demo_openai_api_key)
    with _lock:
        if _cost[token] >= settings.demo_ai_max_cost_usd:
            raise DemoLimitError(f"Demo AI spending limit reached for this session (${settings.demo_ai_max_cost_usd:.2f}). Sign out and back in to start a new demo session.")
        if not _take(token, settings.demo_ai_max_requests_per_hour):
            raise DemoLimitError(f"Demo AI request limit reached ({settings.demo_ai_max_requests_per_hour} per hour for this session). Try again later.")
        if shared and not _take(SHARED, settings.demo_ai_shared_max_requests_per_hour):
            raise DemoLimitError("The shared demo AI quota is used up for this hour. Enter your own API key in AI settings, or try again later.")
        sem = _sems.setdefault(token, threading.BoundedSemaphore(settings.demo_ai_max_concurrency))
    if not sem.acquire(blocking=False):
        raise DemoLimitError(f"Only {settings.demo_ai_max_concurrency} AI requests can run at once in a demo session. Wait for the current one to finish.")
    try:
        yield
    finally:
        sem.release()


def record_cost(usd: float | None) -> None:
    v = _scope.get()
    if v and usd:
        with _lock:
            _cost[v[0]] += float(usd)


def usage(token: str) -> dict:
    with _lock:
        t = time.monotonic()
        recent = sum(1 for x in _hits.get(token, ()) if x > t - 3600)
        return {"requests_last_hour": recent, "cost_usd": round(_cost.get(token, 0.0), 4),
                "limits": {"requests_per_hour": settings.demo_ai_max_requests_per_hour, "concurrency": settings.demo_ai_max_concurrency,
                           "cost_usd": settings.demo_ai_max_cost_usd}}
