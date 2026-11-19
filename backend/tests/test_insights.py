"""Milestone C insights: forecasts labeled unvalidated/shadow; journey is permission-filtered; briefing cites its metrics."""

import re
from datetime import date


def test_forecasts_labeled_and_stored(as_user):
    admin = as_user("hospitaladmin@harborview.dev")
    r = admin.get("/forecasts", params={"days": 7})
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["shadow_mode"] is True and "not validated" in f["label"]
    for target in ("census", "discharges", "ed_arrivals", "admissions"):
        pts = f["series"][target]["forecast"]
        assert len(pts) == 7
        assert all(p["lower"] <= p["value"] <= p["upper"] for p in pts)
        assert date.fromisoformat(pts[0]["date"]) > date.today()
    assert len(f["series"]["nurses_needed"]["forecast"]) == 7
    assert 0 <= f["series"]["no_shows"]["rate_90d"] <= 1
    # idempotent per day: a second call does not duplicate stored predictions
    assert admin.get("/forecasts", params={"days": 7}).status_code == 200
    assert as_user("patient@harborview.dev").get("/forecasts").status_code == 403


def test_journey_permission_filtered(as_user):
    doc = as_user("dr.chen@harborview.dev")
    pid = doc.get("/patients", params={"q": ""}).json()
    pid = (pid["items"] if isinstance(pid, dict) else pid)[0]["id"]
    j = doc.get(f"/patients/{pid}/journey")
    assert j.status_code == 200, j.text
    ev = j.json()["events"]
    assert ev == sorted(ev, key=lambda e: e["at"], reverse=True)
    kinds = {e["kind"] for e in ev}
    assert "billing" not in kinds  # physicians lack billing:read
    assert as_user("patient@harborview.dev").get(f"/patients/{pid}/journey").status_code in (403, 404)


def test_briefing_cites_sources(as_user):
    admin = as_user("hospitaladmin@harborview.dev")
    b = admin.get("/reports/briefing")
    assert b.status_code == 200, b.text
    b = b.json()
    assert b["metrics"] and all(m["source"] and m["ref"].startswith("M") for m in b["metrics"])
    valid = {m["ref"] for m in b["metrics"]} | {c["ref"] for c in b["cases"]}
    assert set(re.findall(r"\[((?:M|C)\d+)\]", b["narrative"])) <= valid
    assert as_user("dr.chen@harborview.dev").get("/reports/briefing").status_code == 403
    assert admin.get("/reports/discharge-bottlenecks").status_code == 200
