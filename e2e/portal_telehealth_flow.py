"""UI E2E (two browsers): patient portal ↔ clinician. Video visit connects over WebRTC; secure messaging; self-booking + intake."""
import sys, random
from datetime import datetime, timedelta, timezone
import httpx
from playwright.sync_api import sync_playwright, expect

OUT = sys.argv[1]; errors = []
API = "http://localhost:5173/api"


def api_login(email):
    c = httpx.Client(base_url=API)
    t = c.post("/auth/login", json={"email": email, "password": "Undeclared!2026"}).json()
    c.headers["Authorization"] = "Bearer " + t["access_token"]
    return c, t["me"]["memberships"][0]


# Setup: telehealth appointment for the portal patient, starting in a few minutes, with a free provider calendar.
admin, _ = api_login("clinicadmin@harborview.dev")
nurse_m = next(x for x in admin.get("/staff").json() if x["email"] == "nurse.rivera@harborview.dev")
admin.patch(f"/staff/{nurse_m['membership_id']}", json={"provider": {"specialty": "Telehealth", "color": "cyan", "is_active": True}})
front, fm = api_login("frontdesk@harborview.dev")
pat_api, pm = api_login("patient@harborview.dev")
clinic = next(c for c in fm["clinics"] if c["code"] == "HDT")["id"]
prov = next(p for p in front.get("/providers").json() if "Rivera" in p["name"])
tele = next(t for t in front.get("/appointment-types").json() if t["is_telehealth"])
appt = None
for off in range(1, 28):
    s0 = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=off)
    r = front.post("/appointments", json={"patient_id": pm["patient_id"], "provider_id": prov["id"], "clinic_id": clinic, "appointment_type_id": tele["id"],
                                          "start_at": s0.isoformat(), "end_at": (s0 + timedelta(minutes=1)).isoformat(), "override_availability": True})
    if r.status_code == 201:
        appt = r.json(); break
assert appt, r.text

ARGS = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--disable-features=WebRtcHideLocalIpsWithMdns"]
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True, args=ARGS)
    def login(email):
        ctx = b.new_context(viewport={"width": 1366, "height": 900}, permissions=["camera", "microphone"])
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto("http://localhost:5173/login")
        pg.fill("input[type=email]", email); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
        pg.wait_for_function("!location.pathname.startsWith('/login')")
        return pg
    pat = login("patient@harborview.dev")
    doc = login("dr.chen@harborview.dev")
    pat.wait_for_url("**/portal"); pat.wait_for_selector("text=Upcoming appointments")
    # --- Video visit ---
    expect(pat.get_by_role("button", name="Join video visit").first).to_be_visible()
    pat.goto(f"http://localhost:5173/portal/visit/{appt['id']}")  # earlier runs may leave other joinable visits
    pat.wait_for_selector("text=virtual waiting room")
    doc.goto(f"http://localhost:5173/telehealth/{appt['id']}")
    for pg in (pat, doc):
        expect(pg.get_by_text("Connected", exact=True)).to_be_visible(timeout=25000)
    def remote_ok(pg):
        return pg.evaluate("""() => { const v = [...document.querySelectorAll('video')].find(v => v.getAttribute('aria-label') !== 'Your video');
                               return !!v && !!v.srcObject && v.videoWidth > 0; }""")
    pat.wait_for_timeout(2500)
    assert remote_ok(pat) and remote_ok(doc), "remote video not flowing"
    doc.screenshot(path=f"{OUT}/tele-01-doctor.png"); pat.screenshot(path=f"{OUT}/tele-02-patient.png")
    doc.get_by_role("button", name="Mute microphone").click(); expect(doc.get_by_role("button", name="Unmute microphone")).to_be_visible()
    doc.get_by_role("button", name="End visit for everyone").click()
    expect(pat.get_by_text("The video visit has ended")).to_be_visible(timeout=10000)
    print("video visit connected both ways, ended by clinician")
    # --- Secure messaging ---
    subject = f"Refill question {random.randint(100, 999)}"
    pat.goto("http://localhost:5173/portal/messages/new")
    pat.get_by_label("Subject").fill(subject); pat.get_by_label("Message").fill("Can I get a refill of my inhaler?")
    pat.get_by_role("button", name="Send", exact=True).click(); pat.wait_for_selector(f"text={subject}")
    doc.goto("http://localhost:5173/messages"); doc.get_by_role("button", name=subject).click()
    doc.get_by_label("Reply").fill("Yes — I've sent it to your pharmacy."); doc.get_by_role("button", name="Send", exact=True).click()
    doc.wait_for_timeout(800)
    pat.reload(); expect(pat.get_by_text("I've sent it to your pharmacy").first).to_be_visible()
    print("secure message round-trip")
    # --- Self-booking + intake ---
    pat.goto("http://localhost:5173/portal/book"); pat.wait_for_selector("text=Choose a time")
    for i in range(14):
        tabs = pat.get_by_role("tab")
        tabs.nth(i).click(); pat.wait_for_timeout(500)
        slot = pat.locator("button.tabular").first
        if slot.count(): slot.click(); break
    pat.get_by_label("Reason for visit").fill("Annual check-in")
    pat.get_by_role("button", name="Confirm booking").click(); pat.wait_for_url("**/portal/appointments")
    pat.get_by_role("link", name="Complete pre-visit form").first.click()
    pat.get_by_label("What would you like to discuss?").fill("Routine check-in and inhaler refill")
    pat.get_by_text("Cough", exact=True).click()
    pat.get_by_text("This list is correct").first.click(); pat.get_by_text("This list is correct").nth(1).click()
    pat.get_by_role("button", name="Submit").click(); pat.wait_for_url("**/portal")
    pat.screenshot(path=f"{OUT}/portal-01-home.png")
    print("booked online and submitted intake")
    b.close()
print("page errors:", errors)
