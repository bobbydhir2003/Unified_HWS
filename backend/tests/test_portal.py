"""Portal: patient/staff separation, self-booking rules, intake, secure messaging, telehealth authorization + signaling."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

DOCTOR, FRONT, PATIENT = "dr.chen@harborview.dev", "frontdesk@harborview.dev", "patient@harborview.dev"

INTAKE = {"reason_details": "Follow-up on cough", "symptoms": ["cough"], "medications_confirmed": True, "allergies_confirmed": True,
          "phq2_interest": 0, "phq2_mood": 1}


def test_portal_and_staff_apis_are_separated(as_user):
    pat, doc = as_user(PATIENT), as_user(DOCTOR)
    assert pat.get("/portal/home").status_code == 200
    assert doc.get("/portal/home").status_code == 403
    for path in ("/messages", "/orders", "/appointments?start=2026-01-01T00:00:00Z&end=2026-01-02T00:00:00Z", "/documents", "/staff"):
        assert pat.get(path).status_code == 403, path


def _next_weekday(days=10):
    d = datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=days)
    while d.weekday() > 4:
        d += timedelta(days=1)
    return d


def test_self_booking_respects_availability_conflicts_and_cancel_window(as_user):
    pat = as_user(PATIENT)
    opts = pat.get("/portal/booking/options").json()
    t = next(x for x in opts["types"] if x["name"] == "Follow-up")
    chen = next(x for x in opts["providers"] if "Chen" in x["name"])
    clinic = next(x for x in opts["clinics"] if "Downtown" in x["name"])
    day = _next_weekday(12)
    slots = pat.get("/portal/booking/slots", params={"provider_id": chen["id"], "clinic_id": clinic["id"], "type_id": t["id"], "day": day.isoformat()}).json()["slots"]
    assert slots
    body = {"appointment_type_id": t["id"], "provider_id": chen["id"], "clinic_id": clinic["id"], "start_at": slots[-1], "reason": "Follow-up visit"}
    r = pat.post("/portal/appointments", json=body)
    assert r.status_code == 201
    appt = r.json()
    assert pat.post("/portal/appointments", json=body).status_code == 409  # same slot again
    late = datetime.combine(day, time(21, 0), ZoneInfo("America/New_York")).isoformat()
    assert pat.post("/portal/appointments", json={**body, "start_at": late}).status_code == 409
    # intake round-trip, visible to staff
    assert pat.post(f"/portal/appointments/{appt['id']}/intake", json=INTAKE).status_code == 201
    staff_view = as_user(DOCTOR).get(f"/appointments/{appt['id']}/intake").json()
    assert staff_view["answers"]["reason_details"] == "Follow-up on cough" and staff_view["reviewed_at"]
    assert pat.post(f"/portal/appointments/{appt['id']}/cancel").json()["status"] == "cancelled"


def test_cannot_cancel_within_24_hours(as_user):
    front, pat = as_user(FRONT), as_user(PATIENT)
    pid = pat.membership["patient_id"]
    clinic = next(c for c in front.membership["clinics"] if c["code"] == "HDT")
    chen = next(p for p in front.get("/providers").json() if "Chen" in p["name"])
    start = datetime.now(ZoneInfo("America/New_York")).replace(hour=23, minute=40, second=0, microsecond=0)
    for _ in range(10):
        r = front.post("/appointments", json={"patient_id": pid, "provider_id": chen["id"], "clinic_id": clinic["id"],
                                              "start_at": start.isoformat(), "end_at": (start + timedelta(minutes=10)).isoformat(),
                                              "override_availability": True})
        if r.status_code == 201:
            break
        start -= timedelta(minutes=11)
    assert r.status_code == 201, r.text
    assert pat.post(f"/portal/appointments/{r.json()['id']}/cancel").status_code == 400


def test_secure_messaging(as_user):
    pat, doc = as_user(PATIENT), as_user(DOCTOR)
    t = pat.post("/portal/messages", json={"subject": "Question about my medication", "category": "medication", "body": "Can I take it with food?"}).json()
    inbox = doc.get("/messages").json()
    assert any(x["id"] == t["id"] and x["unread"] >= 1 for x in inbox["items"])
    assert any("Message from" in n["title"] for n in doc.get("/notifications").json()["items"])
    doc.post(f"/messages/{t['id']}/reply", json={"body": "Yes, with food is fine."})
    mine = pat.get(f"/portal/messages/{t['id']}").json()
    assert mine["messages"][-1]["from_patient"] is False and len(mine["messages"]) == 2
    assert pat.get(f"/messages/{t['id']}").status_code == 403
    lake = as_user("dr.lake@lakeside.dev", "lakeside")
    assert lake.get(f"/messages/{t['id']}").status_code == 404


def test_telehealth_join_authorization_and_signaling(as_user):
    front, pat, doc = as_user(FRONT), as_user(PATIENT), as_user(DOCTOR)
    pid = pat.membership["patient_id"]
    clinic = next(c for c in front.membership["clinics"] if c["code"] == "HDT")
    tele = next(t for t in front.get("/appointment-types").json() if t["is_telehealth"])
    now_ny = datetime.now(ZoneInfo("America/New_York")).replace(second=0, microsecond=0)
    a = None
    # A dedicated provider with an empty calendar keeps this test independent of the seeded schedule.
    admin = as_user("clinicadmin@harborview.dev")
    nurse_m = next(x for x in admin.get("/staff").json() if x["email"] == "nurse.rivera@harborview.dev")
    admin.patch(f"/staff/{nurse_m['membership_id']}", json={"provider": {"specialty": "Telehealth", "color": "cyan", "is_active": True}})
    provs = [x for x in front.get("/providers").json() if "Rivera" in x["name"]]
    for prov in provs:  # find a free 5-minute window in the next ~25 minutes (join window is 30)
        for offset in range(3, 25, 3):
            s0 = now_ny + timedelta(minutes=offset)
            r = front.post("/appointments", json={"patient_id": pid, "provider_id": prov["id"], "clinic_id": clinic["id"],
                                                  "appointment_type_id": tele["id"], "start_at": s0.isoformat(),
                                                  "end_at": (s0 + timedelta(minutes=5)).isoformat(), "override_availability": True})
            if r.status_code == 201:
                a = r.json()
                break
        if a:
            break
    assert a, f"could not book a near-term telehealth slot: {r.status_code} {r.text}"
    assert front.post(f"/telehealth/appointments/{a['id']}/join").status_code == 403  # receptionist: no clinical access
    pj = pat.post(f"/telehealth/appointments/{a['id']}/join").json()
    assert pj["role"] == "patient" and pj["status"] == "waiting"
    dj = doc.post(f"/telehealth/appointments/{a['id']}/join").json()
    assert dj["role"] == "provider" and dj["status"] == "active" and dj["session_id"] == pj["session_id"]
    sid = pj["session_id"]
    pat.post(f"/telehealth/sessions/{sid}/signal", json={"kind": "offer", "payload": {"sdp": "v=0"}})
    got = doc.get(f"/telehealth/sessions/{sid}/signals").json()["signals"]
    assert [s["kind"] for s in got] == ["offer"]
    assert pat.get(f"/telehealth/sessions/{sid}/signals").json()["signals"] == []  # never echoes own signals
    lake = as_user("dr.lake@lakeside.dev", "lakeside")
    assert lake.post(f"/telehealth/appointments/{a['id']}/join").status_code == 404
    assert lake.get(f"/telehealth/sessions/{sid}/signals").status_code == 404
