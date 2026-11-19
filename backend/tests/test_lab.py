"""Laboratory: collect → accession → enter → independent verification → critical call-back → acknowledgment;
corrections keep history; unverified results never reach the patient portal."""


def _first_order(api, title=None):
    wl = api.get("/lab/worklist").json()
    return next(o for o in wl["to_collect"] if not title or o["title"] == title)


def test_lab_flow_with_critical_and_correction(as_user):
    lab, lab2, doc = as_user("lab@harborview.dev"), as_user("lab2@harborview.dev"), as_user("dr.santos@harborview.dev")
    o = _first_order(lab, "Basic metabolic panel")
    sp = lab.post("/lab/collect", json={"order_id": o["order_id"], "specimen_type": "blood", "container": "Green top"}).json()
    assert sp["accession_number"] > 2600000 and sp["template"]
    assert lab.post("/lab/collect", json={"order_id": o["order_id"]}).status_code == 400  # one active specimen
    assert lab.post(f"/lab/specimens/{sp['id']}/results", json=[{"name": "Potassium", "value": "6.9"}]).status_code == 400  # not received
    lab.post(f"/lab/specimens/{sp['id']}/receive")
    rows = [{"name": t["name"], "value": "5", "unit": t["unit"], "reference_range": t["reference_range"]} for t in sp["template"]]
    rows = [r if r["name"] != "Potassium" else {**r, "value": "6.9", "flag": "critical_high"} for r in rows]
    lab.post(f"/lab/specimens/{sp['id']}/results", json=rows)
    # Same person can't verify; doctors can't verify.
    assert lab.post(f"/lab/specimens/{sp['id']}/verify").status_code == 400
    assert doc.post(f"/lab/specimens/{sp['id']}/verify").status_code == 403
    v = lab2.post(f"/lab/specimens/{sp['id']}/verify").json()
    assert v["status"] == "resulted" and v["critical_alerts"] == 1
    # Critical call-back case assigned to the ordering clinician.
    alert = next(a for a in doc.get("/lab/critical").json() if a["order_id"] == o["order_id"])
    case = next(c for c in as_user("hospitaladmin@harborview.dev").get("/cases", params={"category": "lab"}).json()
                if c["subject_id"] == alert["id"])
    assert case["severity"] == "critical" and case["assigned_user_id"]
    assert lab.post(f"/lab/critical/{alert['id']}/acknowledge", json={"read_back": "K 6.9"}).status_code == 403
    assert doc.post(f"/lab/critical/{alert['id']}/acknowledge", json={"read_back": "Potassium 6.9 read back, treating"}).status_code == 200
    assert doc.get(f"/cases/{case['id']}").json()["case"]["status"] == "resolved"
    # Correction: preliminary until verified; old value kept as superseded.
    k = next(r for r in v["results"] if r["name"] == "Potassium")
    c = lab.post(f"/lab/results/{k['id']}/correct", json={"value": "4.1", "flag": "normal", "reason": "Hemolyzed sample; redrawn"}).json()
    assert any(r["status"] == "preliminary" and r["supersedes_id"] == k["id"] for r in c["results"])
    # Clinician review + release are blocked while a preliminary result exists.
    doc.post(f"/orders/{o['order_id']}/review")
    assert doc.post(f"/orders/{o['order_id']}/release").status_code == 400
    lab2.post(f"/lab/specimens/{sp['id']}/verify")
    final = lab.get("/lab/worklist").json()
    assert all(s["id"] != sp["id"] for s in final["specimens"])
    order = doc.get(f"/orders/{o['order_id']}").json()
    ks = [r for r in order["results"] if r["name"] == "Potassium"]
    assert {r["status"] for r in ks} == {"final", "superseded"}
    assert doc.post(f"/orders/{o['order_id']}/review").status_code == 200
    assert doc.post(f"/orders/{o['order_id']}/release").status_code == 200


def test_rejected_specimen_requests_recollection(as_user):
    lab = as_user("lab@harborview.dev")
    o = _first_order(lab)
    sp = lab.post("/lab/collect", json={"order_id": o["order_id"]}).json()
    assert lab.post(f"/lab/specimens/{sp['id']}/reject", json={"reason": "Clotted"}).json()["status"] == "rejected"
    assert any(x["order_id"] == o["order_id"] for x in lab.get("/lab/worklist").json()["to_collect"])
    assert any(t["kind"] == "lab.recollect" for t in as_user("nurse.kim@harborview.dev").get("/tasks", params={"scope": "all"}).json())
    assert as_user("pharmacist@harborview.dev").get("/lab/worklist").status_code == 403
