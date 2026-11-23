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
    """No visitor key: the owner-managed demo provider if enabled, else the operator's env demo key, else simulated."""
    from app.ai import owner_demo

    _, owner = owner_demo.load()
    if owner is not None:
        return owner
    if settings.demo_openai_api_key and not settings.demo_ai_disabled:
        return EffectiveAI(provider="openai", api_key=settings.demo_openai_api_key, key_hint=None, source="demo-project",
                           text_model=settings.demo_ai_text_model, vision_model=settings.demo_ai_text_model,
                           transcription_model=settings.ai_transcription_model, realtime_model=settings.demo_ai_realtime_model,
                           limits=dict(owner_demo.DEFAULT_POLICY["limits"]))
    return EffectiveAI(provider="simulated", source="demo",
                       reason="Public demo AI isn't enabled by the platform owner. Answers are rule-based simulations.")


def load_row(db, session_id: uuid.UUID):
    from sqlalchemy import select

    from app.core.security import now
    from app.models import DemoAISettings

    return db.scalar(select(DemoAISettings).where(DemoAISettings.session_id == session_id, DemoAISettings.expires_at > now()))


def from_row(row) -> EffectiveAI:
    """A visitor's session settings. Never silently substitutes another provider: an own key is used as-is; an unreadable
    own key → simulated (not the owner key); no own key → the owner-managed demo provider (models limited to its allow-list)."""
    import dataclasses

    from app.core.crypto import decrypt

    if row.provider != "openai":
        return EffectiveAI(provider="simulated", source="demo-session", reason="Simulated mode is selected in this session's AI settings.")
    if row.api_key_encrypted:
        try:
            key = decrypt(row.api_key_encrypted)
        except ValueError:
            return EffectiveAI(provider="simulated", source="visitor-key", reason="Your temporary API key couldn't be read. Enter it again in AI settings.")
        return EffectiveAI(provider="openai", api_key=key, key_hint=None, source="visitor-key",
                           text_model=row.text_model or "", vision_model=row.vision_model or row.text_model or "",
                           transcription_model=row.transcription_model or "", realtime_model=row.realtime_model or "",
                           agent_models=dict(row.agent_models or {}))
    base = _default()
    if base.provider != "openai":
        return base
    allowed = set(base.allowed_models or [base.text_model])

    def pick(m, d):
        return m if m and m in allowed else d

    return dataclasses.replace(base, text_model=pick(row.text_model, base.text_model), vision_model=pick(row.vision_model, base.vision_model),
                               agent_models={k: v for k, v in (row.agent_models or {}).items() if v in allowed})


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


class Ticket:
    """Filled by the caller inside `guard()` with what the call actually used (for accounting)."""

    def __init__(self) -> None:
        self.cost: float | None = None
        self.input_tokens = 0
        self.output_tokens = 0

    def record(self, model: str | None, input_tokens: int | None, output_tokens: int | None) -> None:
        from app.ai import usage

        self.input_tokens, self.output_tokens = input_tokens or 0, output_tokens or 0
        self.cost = usage.estimate(model, input_tokens, output_tokens)


def _take(key: str, limit: int, window: float = 3600.0) -> bool:
    t = time.monotonic()
    q = _hits[key]
    while q and q[0] <= t - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(t)
    return True


def shared(eff: EffectiveAI | None) -> bool:
    """True when the call spends the owner's (or operator's) money rather than the visitor's own key."""
    return bool(eff and eff.provider == "openai" and eff.source in ("owner-demo", "demo-project"))


@contextmanager
def guard(model: str | None = None, *, kind: str = "text"):
    """Wrap every outbound AI call. No-op outside a demo scope. Yields a Ticket the caller fills with usage."""
    ticket = Ticket()
    v = _scope.get()
    if not v:
        yield ticket
        return
    token, eff = v
    if shared(eff):
        with _shared_limits(token, eff, model, kind, ticket):
            yield ticket
        return
    # A visitor's own key: session-scoped limits (their spend, our server).
    with _lock:
        if _cost[token] >= settings.demo_ai_max_cost_usd:
            raise DemoLimitError(f"Demo AI spending limit reached for this session (${settings.demo_ai_max_cost_usd:.2f}). Sign out and back in to start a new demo session.")
        if not _take(token, settings.demo_ai_max_requests_per_hour):
            raise DemoLimitError(f"Demo AI request limit reached ({settings.demo_ai_max_requests_per_hour} per hour for this session). Try again later.")
        sem = _sems.setdefault(token, threading.BoundedSemaphore(settings.demo_ai_max_concurrency))
    if not sem.acquire(blocking=False):
        raise DemoLimitError(f"Only {settings.demo_ai_max_concurrency} AI requests can run at once in a demo session. Wait for the current one to finish.")
    try:
        yield ticket
    finally:
        sem.release()
        if ticket.cost:
            with _lock:
                _cost[token] += ticket.cost


@contextmanager
def _shared_limits(token: str, eff: EffectiveAI, model: str | None, kind: str, ticket: Ticket):
    """Owner/operator-funded demo AI: model allow-list, per-visitor and global daily requests, monthly budget (durable,
    atomic — app/ai/usage.py) and per-visitor/global concurrency (Redis; fails closed in staging/production)."""
    from app.ai import usage

    if settings.demo_ai_disabled:
        raise DemoLimitError("Public demo AI is turned off by the operator.")
    lim = eff.limits or {}
    if model and eff.allowed_models and model not in eff.allowed_models:
        raise DemoLimitError(f"The model '{model}' isn't enabled for the public demo.")
    day, mon = usage.day_key(), usage.month_key()
    vk, gk, mk = f"demo:visitor:{token}:day:{day}", f"demo:global:day:{day}", f"demo:global:month:{mon}"
    reserve = (usage.REALTIME_PER_MINUTE * max(1, int(lim.get("realtime_max_seconds", 120))) / 60) if kind == "realtime" else usage.RESERVE_PER_CALL_USD
    taken: list[str] = []
    slots: list[str] = []
    reserved = [0.0]
    try:
        if kind == "realtime":
            if not lim.get("realtime_enabled"):
                raise DemoLimitError("Realtime voice isn't enabled for the public demo.")
            rk = f"demo:global:realtime:day:{day}"
            if not usage.take_request(rk, int(lim.get("realtime_daily_sessions", 0))):
                raise DemoLimitError("Today's public demo voice sessions are used up. Try again tomorrow.")
            taken.append(rk)
        if not usage.take_request(vk, int(lim.get("visitor_daily_requests", 0))):
            raise DemoLimitError(f"This demo session has used its AI allowance for today ({lim.get('visitor_daily_requests')} requests).")
        taken.append(vk)
        if not usage.take_request(gk, int(lim.get("global_daily_requests", 0))):
            raise DemoLimitError("The public demo's AI allowance for today is used up. AI features show simulated results until tomorrow.")
        taken.append(gk)
        if not usage.reserve_cost(mk, reserve, float(lim.get("monthly_budget_usd", 0))):
            raise DemoLimitError("The public demo's estimated monthly AI budget is used up. AI features show simulated results.")
        reserved[0] = reserve
        for k, n in ((f"demo:{token}", int(lim.get("visitor_concurrency", 1))), ("demo:global", int(lim.get("global_concurrency", 1)))):
            if not usage.acquire_slot(k, n):
                raise DemoLimitError("Too many AI requests are running at once in the public demo. Try again in a moment.")
            slots.append(k)
    except usage.LimitError as e:
        _undo(taken, slots, mk, reserved[0])
        raise DemoLimitError(str(e)) from None
    except DemoLimitError:
        _undo(taken, slots, mk, reserved[0])
        raise
    try:
        yield
    finally:
        for k in slots:
            usage.release_slot(k)
        actual = ticket.cost if ticket.cost is not None else (reserve if kind == "realtime" else 0.0)
        usage.adjust(mk, cost_delta=actual - reserve, input_tokens=ticket.input_tokens, output_tokens=ticket.output_tokens)
        usage.adjust(gk, cost_delta=actual, input_tokens=ticket.input_tokens, output_tokens=ticket.output_tokens)


def _undo(taken: list[str], slots: list[str], mk: str, refund: float) -> None:
    from app.ai import usage

    for k in slots:
        usage.release_slot(k)
    for k in taken:  # a refused request doesn't count against an allowance
        usage.give_back_request(k)
    if refund:
        usage.adjust(mk, cost_delta=-refund)


def usage_for(token: str) -> dict:
    """What a demo visitor may see about their AI allowance (never keys)."""
    from app.ai import usage

    eff = current()
    if shared(eff):
        lim = eff.limits or {}
        day = usage.day_key()
        return {"kind": "owner-demo", "requests_today": usage.read(f"demo:visitor:{token}:day:{day}")["requests"],
                "limits": {"requests_per_day": lim.get("visitor_daily_requests"), "concurrency": lim.get("visitor_concurrency")}}
    with _lock:
        t = time.monotonic()
        recent = sum(1 for x in _hits.get(token, ()) if x > t - 3600)
        return {"kind": "visitor-key", "requests_last_hour": recent, "cost_usd": round(_cost.get(token, 0.0), 4),
                "limits": {"requests_per_hour": settings.demo_ai_max_requests_per_hour, "concurrency": settings.demo_ai_max_concurrency,
                           "cost_usd": settings.demo_ai_max_cost_usd}}


def usage(token: str) -> dict:  # backwards-compatible name
    return usage_for(token)
