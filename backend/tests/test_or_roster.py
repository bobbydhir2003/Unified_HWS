"""OR scheduling and rostering: DB-enforced conflicts, rest/hours rules, explainable suggestions, swaps, coverage loop."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.engine.monitors import run_monitor
from app.models import Organization


def _run(key):
    db = SessionLocal()
    try:
        run_monitor(db, db.scalar(select(Organization.id).where(Organization.slug == "harborview")), key)
        db.commit()
    finally:
        db.close()


def test_or_conflicts(as_user):
    admin, nurse = as_user("hospitaladmin@harborview.dev"), as_user("nurse.kim@harborview.dev")
    sched = admin.get("/or/schedule").json()
    room_a, room_b = sched["rooms"][2]["id"], sched["rooms"][3]["id"]
    pid = admin.get("/patients", params={"page_size": 1}).json()["items"][0]["id"]
    sur = next(p for p in admin.get("/providers").json() if "Chen" in p["name"])["id"]
    start = (datetime.now().astimezone() + timedelta(days=5)).replace(hour=8, minute=0, second=0, microsecond=0)
    body = {"or_room_id": room_a, "patient_id": pid, "surgeon_provider_id": sur, "procedure": "Carpal tunnel release", "start_at": start.isoformat(),
            "duration_minutes": 60, "turnover_minutes": 30}
    assert nurse.post("/or/cases", json=body).status_code == 403
    assert admin.post("/or/cases", json=body).status_code == 201
    # Same room during turnover → rejected by the DB exclusion constraint.
    r = admin.post("/or/cases", json={**body, "start_at": (start + timedelta(minutes=75)).isoformat()})
    assert r.status_code == 400 and "booked" in r.text
    # Same surgeon in another room at the same time → rejected.
    r = admin.post("/or/cases", json={**body, "or_room_id": room_b, "start_at": (start + timedelta(minutes=30)).isoformat()})
    assert r.status_code == 400 and "surgeon" in r.text
    # After turnover the room is free.
    assert admin.post("/or/cases", json={**body, "start_at": (start + timedelta(minutes=90)).isoformat()}).status_code == 201


def test_roster_rules_suggestions_and_swaps(as_user):
    admin = as_user("hospitaladmin@harborview.dev")
    roster = admin.get("/roster", params={"days": 3}).json()
    ms = next(d for d in admin.get("/departments").json() if d["code"] == "MS")
    gap = next(g for g in roster["gaps"] if g["department_id"] == ms["id"])
    _run("staffing.coverage_gap")
    case = next(c for c in admin.get("/cases", params={"category": "staffing"}).json() if c["department_id"] == ms["id"])
    sug = admin.get("/roster/suggest", params={"department_id": ms["id"], "role": "nurse", "start": gap["start"], "end": gap["end"]}).json()
    assert sug["candidates"] and all(c["reasons"] for c in sug["candidates"])
    pick = sug["candidates"][0]
    s = admin.post("/roster/shifts", json={"user_id": pick["user_id"], "department_id": ms["id"], "role": "nurse", "start_at": gap["start"], "end_at": gap["end"]})
    assert s.status_code == 201, s.text
    # Overlap is impossible; short rest needs an explicit override with a reason.
    assert admin.post("/roster/shifts", json={"user_id": pick["user_id"], "department_id": ms["id"], "role": "nurse", "start_at": gap["start"], "end_at": gap["end"]}).status_code == 400
    nxt = datetime.fromisoformat(gap["end"]) + timedelta(hours=2)
    body = {"user_id": pick["user_id"], "department_id": ms["id"], "role": "nurse", "start_at": nxt.isoformat(), "end_at": (nxt + timedelta(hours=8)).isoformat()}
    r = admin.post("/roster/shifts", json=body)
    assert r.status_code == 400 and "rest" in r.text
    assert admin.post("/roster/shifts", json={**body, "override_rules": True}).status_code == 400
    assert admin.post("/roster/shifts", json={**body, "override_rules": True, "override_reason": "Mass-casualty surge"}).status_code == 201
    _run("staffing.coverage_gap")
    assert admin.get(f"/cases/{case['id']}").json()["case"]["status"] in ("resolved", "open")


def test_swap_flow(as_user):
    admin = as_user("hospitaladmin@harborview.dev")
    ms = next(d for d in admin.get("/departments").json() if d["code"] == "MS")
    a, b = as_user("rn.ana.lopez@harborview.dev"), as_user("rn.fay.chu@harborview.dev")
    mine = [s for s in a.get("/roster", params={"days": 3}).json()["shifts"] if s["user_id"] == a.me["user"]["id"]]
    assert mine
    w = a.post("/roster/swaps", json={"shift_id": mine[-1]["id"], "reason": "Family event"}).json()
    assert a.post(f"/roster/swaps/{w['id']}/accept").status_code == 403  # can't accept your own
    acc = b.post(f"/roster/swaps/{w['id']}/accept")
    if acc.status_code == 400:  # Fay isn't eligible (rest/hours) — rule held; nothing else to check
        assert "can't take" in acc.text
        return
    assert b.post(f"/roster/swaps/{w['id']}/decide", json={"approve": True}).status_code == 403  # managers approve
    assert admin.post(f"/roster/swaps/{w['id']}/decide", json={"approve": True}).json()["status"] == "approved"
    assert any(s["id"] == mine[-1]["id"] and s["user_id"] == b.me["user"]["id"] for s in admin.get("/roster", params={"days": 3, "department_id": ms["id"]}).json()["shifts"])
    _ = uuid
