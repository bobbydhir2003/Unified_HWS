"""C8 performance guards: hot read endpoints must not issue per-row queries (N+1) and must answer within a generous budget.

Statement counts are deterministic regardless of machine speed, so they're the primary guard; the time budget only
catches pathological regressions on the small seeded dataset."""

import time
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.core.db import engine


@contextmanager
def count_queries():
    n = [0]

    def before(*_a, **_k):
        n[0] += 1

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield n
    finally:
        event.remove(engine, "before_cursor_execute", before)


# (user, path, max SQL statements)
BUDGETS = [
    ("hospitaladmin@harborview.dev", "/cases", 15),
    ("hospitaladmin@harborview.dev", "/cases/summary", 15),
    ("hospitaladmin@harborview.dev", "/command/summary", 55),
    ("hospitaladmin@harborview.dev", "/adt/board", 22),
    ("hospitaladmin@harborview.dev", "/ed/board", 24),
    ("hospitaladmin@harborview.dev", "/forecasts", 30),
    ("hospitaladmin@harborview.dev", "/reports/briefing", 30),
    ("hospitaladmin@harborview.dev", "/ai/governance", 18),
    ("dr.chen@harborview.dev", "/patients", 18),
]


@pytest.mark.parametrize(("email", "path", "max_queries"), BUDGETS)
def test_endpoint_query_and_time_budget(as_user, email, path, max_queries):
    c = as_user(email)
    assert c.get(path).status_code == 200  # warm-up (agent defaults, caches)
    with count_queries() as n:
        t = time.perf_counter()
        r = c.get(path)
        ms = (time.perf_counter() - t) * 1000
    assert r.status_code == 200, r.text
    assert n[0] <= max_queries, f"{path}: {n[0]} SQL statements (budget {max_queries})"
    assert ms < 2000, f"{path}: {ms:.0f} ms"


def test_journey_does_not_scale_queries_with_events(as_user):
    doc = as_user("dr.chen@harborview.dev")
    pts = doc.get("/patients").json()
    pts = pts["items"] if isinstance(pts, dict) else pts
    counts = []
    for p in pts[:6]:
        with count_queries() as n:
            ev = doc.get(f"/patients/{p['id']}/journey").json()["events"]
        counts.append((len(ev), n[0]))
    # Query count must stay flat however many events a patient has.
    assert max(q for _, q in counts) <= 22, counts
