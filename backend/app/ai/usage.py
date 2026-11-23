"""AI usage limits and accounting shared by every process.

* Durable counters (Postgres `ai_usage_counters`): daily/monthly request counts and estimated spend. Every increment is a
  single atomic `INSERT … ON CONFLICT … WHERE value < limit RETURNING`, so concurrent requests can't exceed a limit and
  counts survive restarts and deployments.
* Spend is enforced by *reserving* a conservative per-call estimate before the call and reconciling with the measured
  estimate afterwards, so in-flight calls can't overshoot the budget either.
* Concurrency slots live in Redis (INCR/DECR with a TTL). In staging/production an unreachable Redis FAILS CLOSED (the
  call is refused); development and tests fall back to an in-process counter.

Costs are ESTIMATES from a price table (USD per 1M tokens). They are not a billing cap — also set a spending limit on the
OpenAI project itself. Unknown models are priced conservatively high so budgets are never under-counted.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from sqlalchemy import text

from app.core.config import settings

log = logging.getLogger("undeclared.ai.usage")

# USD per 1M tokens [input, output] — estimates; override/extend with AI_PRICES. Matched by longest prefix.
DEFAULT_PRICES: dict[str, list[float]] = {
    "gpt-4.1-nano": [0.10, 0.40], "gpt-4.1-mini": [0.40, 1.60], "gpt-4.1": [2.00, 8.00],
    "gpt-4o-mini": [0.15, 0.60], "gpt-4o": [2.50, 10.00],
    "gpt-5-nano": [0.05, 0.40], "gpt-5-mini": [0.25, 2.00], "gpt-5": [1.25, 10.00],
}
UNKNOWN_PRICE = [10.0, 30.0]          # deliberately high: an unknown model can't slip under a budget
TRANSCRIPTION_PER_MINUTE = 0.006       # estimate (whisper-class models)
REALTIME_PER_MINUTE = 0.30             # conservative estimate for realtime audio sessions
RESERVE_PER_CALL_USD = 0.05            # reserved before each call, reconciled after


class LimitError(Exception):
    """A usage limit was reached, or limits can't be enforced right now (fail closed)."""


def price_for(model: str | None) -> list[float]:
    table = {**DEFAULT_PRICES, **(settings.ai_prices or {})}
    if not model:
        return UNKNOWN_PRICE
    best = max((k for k in table if model.startswith(k)), key=len, default=None)
    return table[best] if best else UNKNOWN_PRICE


def estimate(model: str | None, input_tokens: int | None, output_tokens: int | None) -> float:
    p = price_for(model)
    return round((input_tokens or 0) / 1e6 * p[0] + (output_tokens or 0) / 1e6 * p[1], 6)


def day_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def month_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


# ------------------------------------------------------------------------------------------------ durable counters

def _exec(sql: str, **params):
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        r = db.execute(text(sql), params).first()
        db.commit()
        return r
    finally:
        db.close()


def take_request(key: str, limit: int) -> bool:
    """Atomically count one request under `key` unless it is already at `limit`."""
    if limit <= 0:
        return False
    r = _exec("""INSERT INTO ai_usage_counters (key, requests, updated_at) VALUES (:k, 1, now())
                 ON CONFLICT (key) DO UPDATE SET requests = ai_usage_counters.requests + 1, updated_at = now()
                 WHERE ai_usage_counters.requests < :lim RETURNING requests""", k=key, lim=limit)
    return r is not None


def give_back_request(key: str) -> None:
    _exec("UPDATE ai_usage_counters SET requests = GREATEST(requests - 1, 0), updated_at = now() WHERE key = :k RETURNING requests", k=key)


def reserve_cost(key: str, amount: float, budget: float) -> bool:
    """Atomically add `amount` to spend under `key` only if the result stays within `budget`."""
    if budget <= 0:
        return False
    r = _exec("""INSERT INTO ai_usage_counters (key, cost_usd, updated_at)
                 SELECT :k, :a, now() WHERE :a <= :b
                 ON CONFLICT (key) DO UPDATE SET cost_usd = ai_usage_counters.cost_usd + :a, updated_at = now()
                 WHERE ai_usage_counters.cost_usd + :a <= :b RETURNING cost_usd""", k=key, a=amount, b=budget)
    return r is not None


def adjust(key: str, *, cost_delta: float = 0.0, input_tokens: int = 0, output_tokens: int = 0) -> None:
    _exec("""INSERT INTO ai_usage_counters (key, cost_usd, input_tokens, output_tokens, updated_at)
             VALUES (:k, GREATEST(:c, 0), :i, :o, now())
             ON CONFLICT (key) DO UPDATE SET cost_usd = GREATEST(ai_usage_counters.cost_usd + :c, 0),
               input_tokens = ai_usage_counters.input_tokens + :i, output_tokens = ai_usage_counters.output_tokens + :o, updated_at = now()
             RETURNING cost_usd""", k=key, c=cost_delta, i=input_tokens, o=output_tokens)


def read(key: str) -> dict:
    r = _exec("SELECT requests, cost_usd, input_tokens, output_tokens FROM ai_usage_counters WHERE key = :k", k=key)
    return {"requests": int(r[0]), "cost_usd": float(r[1]), "input_tokens": int(r[2]), "output_tokens": int(r[3])} if r else \
        {"requests": 0, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}


# ------------------------------------------------------------------------------------------------ concurrency (Redis)

_local_lock = threading.Lock()
_local: dict[str, int] = {}


def _strict() -> bool:
    return settings.environment in ("staging", "production")


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)


def acquire_slot(key: str, limit: int, ttl_seconds: int = 300) -> bool:
    try:
        r = _redis()
        n = r.incr(f"ai:conc:{key}")
        r.expire(f"ai:conc:{key}", ttl_seconds)
        if n > limit:
            r.decr(f"ai:conc:{key}")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        if _strict():
            log.error("AI concurrency limits unavailable (Redis): %s", type(e).__name__)
            raise LimitError("AI usage limits can't be enforced right now, so the request was refused. Try again shortly.") from None
        with _local_lock:
            if _local.get(key, 0) >= limit:
                return False
            _local[key] = _local.get(key, 0) + 1
            return True


def release_slot(key: str) -> None:
    try:
        r = _redis()
        if r.decr(f"ai:conc:{key}") < 0:
            r.set(f"ai:conc:{key}", 0)
    except Exception:  # noqa: BLE001
        with _local_lock:
            _local[key] = max(0, _local.get(key, 0) - 1)
