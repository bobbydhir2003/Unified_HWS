"""Private demo hospitals in the browser (needs an API with DEMO_MODE=true).

Two visitors (separate browser contexts) each start a demo: they get different hospitals. Visitor A, as Super Admin,
pauses a monitor (persists after reload), registers a patient, switches roles from the demo bar; visitor B can't find
A's patient; A resets the hospital and the patient is gone. Platform-only actions aren't offered.
"""
import os
import random
import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []
suffix = str(random.randint(1000, 9999))
last = f"Sandbox{suffix}"

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def visitor(role_label: str):
        ctx = b.new_context(viewport={"width": 1440, "height": 950})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"{role_label}: {e}"))
        pg.goto(f"{BASE}/login")
        pg.get_by_role("button", name=f"Sign in as demo {role_label}").click()
        for _ in range(120):  # may build a hospital on demand (a few seconds)
            if "/login" not in pg.url:
                break
            alert = pg.get_by_test_id("demo-access").get_by_role("alert")
            if alert.count():
                raise SystemExit(f"demo sign-in refused: {alert.inner_text()}")
            pg.wait_for_timeout(500)
        expect(pg.get_by_test_id("demo-bar")).to_be_visible(timeout=15000)
        return pg

    def switch(pg, value: str):
        pg.get_by_test_id("demo-role-switch").select_option(value)
        expect(pg.get_by_test_id("demo-role-switch")).to_have_value(value, timeout=15000)
        pg.wait_for_timeout(600)

    def find_patient(pg) -> bool:
        pg.goto(f"{BASE}/patients")
        pg.get_by_role("textbox", name="Search patients").fill(last)
        pg.wait_for_timeout(1200)
        return pg.get_by_text(last).count() > 0

    a = visitor("Super Admin")
    expect(a.get_by_test_id("demo-role-switch")).to_have_value("super_admin")
    expect(a.get_by_test_id("demo-expiry")).to_contain_text("Ends in")
    a.screenshot(path=f"{SHOTS}/demo-01-super-admin.png")

    # Settings persist: pause a monitor, reload, still paused.
    a.goto(f"{BASE}/automation/monitors")
    sw = a.get_by_role("switch", name=re.compile(r"Enable Lab turnaround"))
    expect(sw).to_be_visible(timeout=15000)
    was = sw.get_attribute("aria-checked")
    sw.click()
    a.wait_for_timeout(1000)
    a.reload()
    sw = a.get_by_role("switch", name=re.compile(r"Enable Lab turnaround"))
    expect(sw).to_have_attribute("aria-checked", "false" if was == "true" else "true", timeout=15000)
    a.screenshot(path=f"{SHOTS}/demo-02-monitor-saved.png")

    # Platform-only action isn't offered in a demo hospital.
    a.goto(f"{BASE}/admin/organizations")
    expect(a.get_by_text("Creating organizations is a platform-owner action")).to_be_visible(timeout=10000)
    expect(a.get_by_role("button", name="New organization")).to_have_count(0)

    # Register a patient (as Front desk, switched from the demo bar).
    switch(a, "front_desk")
    a.goto(f"{BASE}/patients/new")
    a.get_by_label("First name").fill("Demo")
    a.get_by_label("Last name").fill(last)
    a.get_by_label("Date of birth").fill("1984-07-07")
    a.get_by_label("Sex assigned at birth").select_option("female")
    a.get_by_role("button", name="Register patient").click()
    try:
        a.get_by_role("button", name="Not a duplicate — create new record").click(timeout=2500)
    except Exception:  # noqa: BLE001 — no duplicate prompt
        pass
    a.wait_for_url(re.compile(r"/patients/[0-9a-f-]{36}"), timeout=15000)
    assert find_patient(a), "visitor A can't find the patient they registered"
    a.screenshot(path=f"{SHOTS}/demo-03-patient-registered.png")

    # Every role is available; a patient lands in the portal (with the same demo bar).
    switch(a, "patient")
    a.wait_for_url(re.compile(r"/portal"), timeout=15000)
    expect(a.get_by_test_id("demo-bar")).to_be_visible()
    switch(a, "pharmacist")
    a.goto(f"{BASE}/pharmacy")
    expect(a.get_by_role("heading", name=re.compile("Pharmacy"))).to_be_visible(timeout=15000)
    switch(a, "super_admin")

    # Another visitor has a different hospital and can't see A's patient.
    bpg = visitor("Doctor")
    assert not find_patient(bpg), "visitor B can see visitor A's patient"
    bpg.screenshot(path=f"{SHOTS}/demo-04-other-visitor.png")

    # Reset: confirmation, a fresh hospital, and A's patient is gone.
    a.goto(f"{BASE}/")
    a.get_by_test_id("demo-reset").click()
    a.get_by_test_id("demo-reset-confirm").click()
    expect(a.get_by_test_id("demo-reset-confirm")).to_be_hidden(timeout=60000)  # closes once the new hospital is ready
    expect(a.get_by_test_id("demo-bar")).to_be_visible(timeout=60000)
    assert not find_patient(a), "patient still present after reset"
    a.screenshot(path=f"{SHOTS}/demo-05-after-reset.png")

    # Phone width: the demo bar wraps without horizontal scrolling.
    m = b.new_context(viewport={"width": 390, "height": 844}).new_page()
    m.goto(f"{BASE}/login")
    m.get_by_role("button", name="Sign in as demo Nurse / MA").click()
    m.wait_for_url(lambda u: "/login" not in u, timeout=60000)
    expect(m.get_by_test_id("demo-bar")).to_be_visible(timeout=15000)
    assert m.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "horizontal scroll at 390 px"
    m.screenshot(path=f"{SHOTS}/demo-06-phone.png")
    b.close()

if errors:
    print("PAGE ERRORS:", *errors, sep="\n  ")
    sys.exit(1)
print("demo hospitals: two isolated visitors, role switching, persisted settings, reset — OK")
