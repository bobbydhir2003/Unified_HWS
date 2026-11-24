"""In-process engine scheduler for local development without Celery beat (ENGINE_INPROCESS_SCHEDULER=true).

Production runs the same jobs from Celery beat (app/worker.py). Never enable both.
"""

import logging
import threading
import time

log = logging.getLogger("undeclared.engine.scheduler")
_started = False


def _loop(stop: threading.Event) -> None:
    from app.core.db import SessionLocal
    from app.engine.cases import escalate_due
    from app.engine.events import dispatch_pending
    from app.engine.monitors import run_all

    last = {"esc": 0.0, "mon": 0.0}
    while not stop.wait(10):
        try:
            dispatch_pending()
            t = time.monotonic()
            if t - last["esc"] >= 60:
                db = SessionLocal()
                try:
                    if escalate_due(db).get("escalated"):
                        db.commit()
                        _sweep(db)
                    db.commit()
                finally:
                    db.close()
                last["esc"] = t
            if t - last["mon"] >= 300:
                db = SessionLocal()
                try:
                    run_all(db)
                    db.commit()
                    _sweep(db)
                finally:
                    db.close()
                last["mon"] = t
        except Exception:  # noqa: BLE001
            log.exception("engine scheduler tick failed")


def _sweep(db) -> None:
    from app.tasks import _assist_sweep

    _assist_sweep(db)


def start() -> threading.Event:
    global _started
    stop = threading.Event()
    if not _started:
        _started = True
        threading.Thread(target=_loop, args=(stop,), name="engine-scheduler", daemon=True).start()
        log.info("in-process engine scheduler started")
    return stop
