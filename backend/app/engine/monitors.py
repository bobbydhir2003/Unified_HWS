"""Condition monitors: scheduled reconciliation of *current state* against open cases.

Each run: evaluate → for every finding, open a case (deduplicated) or refresh the open one → `on_tick` (e.g. reminder
steps, each delivered once) → cases whose condition is no longer detected are closed by `clear()` (the Verify step).
Because monitors look at state rather than events, they self-heal after missed events, restarts, or bugs.
"""

import logging
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import now
from app.engine import cases as C
from app.engine.cases import Finding
from app.models import Case, MonitorConfig, MonitorRun, Organization
from app.models.engine import CASE_OPEN

log = logging.getLogger("undeclared.engine.monitors")


class Monitor:
    key: str = ""
    name: str = ""
    description: str = ""
    category: str = "operations"
    default_config: dict[str, Any] = {}
    config_help: dict[str, str] = {}
    auto_resolve: bool = True

    def evaluate(self, db: Session, org_id: uuid.UUID, cfg: dict) -> list[Finding]:
        raise NotImplementedError

    def on_open(self, db: Session, case: Case, f: Finding, cfg: dict) -> None:
        """Called once when a case is created (create tasks, first notifications)."""

    def on_tick(self, db: Session, case: Case, f: Finding, cfg: dict) -> None:
        """Called every run while the condition persists (time-based reminder steps — deliver() dedupes them)."""

    def clear(self, db: Session, case: Case, cfg: dict) -> tuple[str, str]:
        """Condition no longer detected → (resolution_code, note)."""
        return "condition_cleared", "Condition no longer detected by the monitor (verified automatically)."


REGISTRY: dict[str, Monitor] = {}


def register(m: Monitor) -> Monitor:
    REGISTRY[m.key] = m
    return m


def get_config(db: Session, org_id: uuid.UUID, key: str) -> tuple[bool, dict, int]:
    m = REGISTRY[key]
    row = db.scalar(select(MonitorConfig).where(MonitorConfig.organization_id == org_id, MonitorConfig.monitor_key == key,
                                                MonitorConfig.facility_id.is_(None)))
    if not row:
        return True, dict(m.default_config), 0
    return row.is_enabled, {**m.default_config, **(row.config or {})}, row.version


def run_monitor(db: Session, org_id: uuid.UUID, key: str, *, force: bool = False) -> MonitorRun | None:
    m = REGISTRY[key]
    enabled, cfg, version = get_config(db, org_id, key)
    if not enabled and not force:
        return None
    run = MonitorRun(organization_id=org_id, monitor_key=key)
    db.add(run)
    db.flush()
    t0 = time.perf_counter()
    sp = db.begin_nested()
    try:
        findings = m.evaluate(db, org_id, cfg)
        seen: set[str] = set()
        for f in findings:
            if f.dedupe_key in seen:
                continue
            seen.add(f.dedupe_key)
            case, created = C.open_case(db, org_id, f, source="monitor", rule_key=key, rule_version=version)
            if created:
                run.opened += 1
                m.on_open(db, case, f, cfg)
            else:
                if C.refresh_case(db, case, f):
                    run.updated += 1
            if case.status != "snoozed":
                m.on_tick(db, case, f, cfg)
        if m.auto_resolve:
            for case in db.scalars(select(Case).where(Case.organization_id == org_id, Case.rule_key == key,
                                                      Case.status.in_(CASE_OPEN))).all():
                if case.dedupe_key not in seen:
                    code, note = m.clear(db, case, cfg)
                    C.resolve(db, case, note, code=code)
                    run.closed += 1
        run.found = len(seen)
        run.status = "succeeded"
        sp.commit()
    except Exception as e:  # noqa: BLE001
        sp.rollback()
        log.exception("monitor failed", extra={"monitor": key})
        run.status, run.error = "failed", f"{type(e).__name__}: {str(e)[:400]}"
    run.finished_at = now()
    run.duration_ms = int((time.perf_counter() - t0) * 1000)
    return run


def run_all(db: Session, org_ids: list[uuid.UUID] | None = None) -> list[MonitorRun]:
    import app.monitors  # noqa: F401 — registers built-in monitors

    if org_ids is None:
        org_ids = list(db.scalars(select(Organization.id).where(Organization.status == "active")))
    runs = []
    for org_id in org_ids:
        for key in REGISTRY:
            r = run_monitor(db, org_id, key)
            if r:
                runs.append(r)
            db.commit()
    return runs
