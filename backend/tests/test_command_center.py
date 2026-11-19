"""Command Center: numbers reconcile with source rows; access limited to operations roles."""


def test_tiles_reconcile_with_source_data(as_user):
    admin = as_user("hospitaladmin@harborview.dev")
    s = admin.get("/command/summary").json()
    tiles = {t["key"]: t for t in s["tiles"]}
    # Hospital admin is scoped to the hospital facility: insurance cases (clinic visits) must not leak in unless facility-less.
    ca = as_user("clinicadmin@harborview.dev")
    c = ca.get("/command/summary").json()
    ctiles = {t["key"]: t for t in c["tiles"]}
    open_ins = ca.get("/cases", params={"category": "insurance"}).json()
    assert ctiles["insurance"]["value"] == len(open_ins)
    assert ctiles["overdue"]["value"] == len(ca.get("/cases", params={"overdue": True}).json())
    assert sum(r["count"] for r in c["cases_by_category"]) == ca.get("/cases/summary").json()["total_open"]
    assert all(t["source"] for t in c["tiles"])  # every tile declares where its number comes from
    assert tiles["insurance"]["value"] <= ctiles["insurance"]["value"]


def test_access_limited(as_user):
    assert as_user("dr.chen@harborview.dev").get("/command/summary").status_code == 403
    assert as_user("patient@harborview.dev").get("/command/summary").status_code == 403
    assert as_user("bedmanager@harborview.dev").get("/command/summary").status_code == 200


def test_hospital_tiles_and_handoff(as_user):
    admin = as_user("hospitaladmin@harborview.dev")
    s = admin.get("/command/summary").json()
    h = s["hospital"]
    assert h["available"]
    tiles = {t["key"]: t for t in h["tiles"]}
    board = admin.get("/adt/board").json()
    assert tiles["beds"]["value"] == board["totals"]["available"]
    assert sum(d["occupied"] for d in h["occupancy_by_department"] if d["kind"] != "emergency") == board["totals"]["occupied"]
    assert all(t["source"] for t in h["tiles"])
    ho = admin.get("/command/handoff").json()
    refs = {i["ref"] for items in ho["sections"].values() for i in items}
    for line in ho["narrative"].splitlines()[1:]:
        assert "[C" in line
    import re

    assert set(re.findall(r"\[(C\d+)\]", ho["narrative"])) <= refs
    assert as_user("dr.chen@harborview.dev").get("/command/handoff").status_code == 403
