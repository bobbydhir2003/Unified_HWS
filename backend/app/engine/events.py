"""Transactional outbox + dispatcher.

`emit()` inserts a `domain_events` row inside the caller's transaction — if the business change rolls back, so does the
event; if it commits, the event will be processed even if the process dies right after (the beat dispatcher retries).
After a commit that emitted events we kick the dispatcher (inline in eager/dev mode, via Celery otherwise).

Handlers are registered with `@handler("name", "event.type", ...)`. Each (event, handler) pair completes at most once,
guarded by the unique row in `event_handlings`; failures retry with exponential backoff and go `dead` after MAX_ATTEMPTS.
"""

import logging
import threading
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import now
from app.models import DomainEvent, EventHandling

log = logging.getLogger("undeclared.engine")
MAX_ATTEMPTS = 6
_PENDING_KEY = "engine_events_emitted"

Handler = Callable[[Session, DomainEvent], None]
_HANDLERS: dict[str, list[tuple[str, Handler]]] = {}
_WILDCARD: list[tuple[str, Handler]] = []


def handler(name: str, *event_types: str):
    """Register an idempotent handler. Use "*" to receive every event."""

    def deco(fn: Handler) -> Handler:
        for et in event_types:
            (_WILDCARD if et == "*" else _HANDLERS.setdefault(et, [])).append((name, fn))
        return fn

    return deco


def handlers_for(event_type: str) -> list[tuple[str, Handler]]:
    return [*_HANDLERS.get(event_type, []), *_WILDCARD]


def emit(db: Session, org_id: uuid.UUID, event_type: str, payload: dict[str, Any] | None = None, *,
         actor_id: uuid.UUID | None = None, facility_id: uuid.UUID | None = None) -> DomainEvent:
    payload = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in (payload or {}).items()}
    pid = payload.get("patient_id")
    ev = DomainEvent(organization_id=org_id, event_type=event_type, subject_type=payload.get("subject_type"),
                     subject_id=str(payload["subject_id"]) if payload.get("subject_id") else None,
                     patient_id=uuid.UUID(str(pid)) if pid else None, facility_id=facility_id, actor_id=actor_id, payload=payload)
    db.add(ev)
    db.info[_PENDING_KEY] = True
    return ev


_local = threading.local()


@sa_event.listens_for(Session, "after_commit")
def _kick_after_commit(session: Session) -> None:
    if not session.info.pop(_PENDING_KEY, False):
        return
    if getattr(_local, "dispatching", False):
        _local.again = True  # the running dispatch loop will pick these up
        return
    from app.core.config import settings

    if settings.celery_eager:
        try:
            dispatch_pending()
        except Exception:  # noqa: BLE001 — never break the caller's request; beat retries
            log.exception("inline dispatch failed")
    else:
        try:
            from app.tasks import dispatch_events_task

            dispatch_events_task.delay()
        except Exception:  # noqa: BLE001 — broker down: the beat schedule picks the event up
            log.warning("could not enqueue dispatch; beat will retry")


def _process(db: Session, ev: DomainEvent) -> bool:
    """Run every handler not yet completed for this event. Returns True when all handlers are done."""
    done = set(db.scalars(select(EventHandling.handler).where(EventHandling.event_id == ev.id, EventHandling.status == "done")))
    ok = True
    for name, fn in handlers_for(ev.event_type):
        if name in done:
            continue
        sp = db.begin_nested()
        try:
            fn(db, ev)
            db.add(EventHandling(event_id=ev.id, handler=name, status="done", attempts=ev.attempts + 1))
            db.flush()
            sp.commit()
        except IntegrityError:
            sp.rollback()  # another worker completed this handler concurrently — treat as done
        except Exception as e:  # noqa: BLE001
            sp.rollback()
            ok = False
            ev.last_error = f"{name}: {type(e).__name__}: {str(e)[:300]}"
            log.exception("event handler failed", extra={"handler": name, "event_type": ev.event_type})
    return ok


def dispatch_pending(limit: int = 200, max_rounds: int = 10) -> int:
    """Process due pending events. Safe to run concurrently (SKIP LOCKED) and repeatedly (idempotent)."""
    import app.engine.handlers  # noqa: F401 — registers handlers
    import app.monitors  # noqa: F401 — monitors may register event handlers too
    from app.core.db import SessionLocal

    if getattr(_local, "dispatching", False):
        _local.again = True
        return 0
    _local.dispatching = True
    total = 0
    try:
        for _ in range(max_rounds):
            _local.again = False
            db = SessionLocal()
            try:
                events = db.scalars(select(DomainEvent).where(DomainEvent.status == "pending", DomainEvent.next_attempt_at <= now())
                                    .order_by(DomainEvent.occurred_at).limit(limit).with_for_update(skip_locked=True)).all()
                for ev in events:
                    if _process(db, ev):
                        ev.status, ev.dispatched_at, ev.last_error = "done", now(), None
                    else:
                        ev.attempts += 1
                        if ev.attempts >= MAX_ATTEMPTS:
                            ev.status = "dead"
                        else:
                            ev.next_attempt_at = now() + timedelta(seconds=min(2 ** ev.attempts * 5, 3600))
                db.commit()
                total += len(events)
            finally:
                db.close()
            if not _local.again and len(events) < limit:
                break
    finally:
        _local.dispatching = False
    return total


def retry_dead(db: Session, event_id: uuid.UUID) -> None:
    ev = db.get(DomainEvent, event_id)
    if ev and ev.status == "dead":
        ev.status, ev.attempts, ev.next_attempt_at = "pending", 0, now()
        db.info[_PENDING_KEY] = True
