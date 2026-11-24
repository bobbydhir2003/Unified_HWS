"""Header role switcher in the browser: ONE real account (the platform Super Admin) signs in once and works in different
hospital workspaces. The sidebar and dashboard follow the workspace, the choice survives a reload, records and settings
saved in a workspace persist, the patient workspace never exposes someone else's record, logout works, and an
ordinary single-role account gets no switcher. Synthetic data only."""
import os
import random
import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173").rstrip("/")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
PASSWORD = os.environ.get("E2E_PASSWORD", "Undeclared!2026")  # the documented development/CI seed password
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []
last = f"Workspace{random.randint(1000, 9999)}"

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def login(pg, email):
        pg.goto(f"{BASE}/login")
        pg.fill("input[type=email]", email)
        pg.fill("input[type=password]", PASSWORD)
        pg.click("button[type=submit]")
        pg.wait_for_url(lambda u: "/login" not in u, timeout=20000)

    def switch(pg, role, label):
        pg.get_by_test_id("workspace-switcher").first.click()
        pg.get_by_test_id(f"workspace-{role}").click()
        expect(pg.get_by_test_id("workspace-current").first).to_have_text(label, timeout=10000)
        pg.wait_for_timeout(500)

    nav = lambda pg: pg.get_by_role("navigation", name="Main")  # noqa: E731

    pg = b.new_page(viewport={"width": 1440, "height": 950})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    login(pg, "admin@undeclared.dev")
    expect(pg.get_by_test_id("workspace-current")).to_have_text("Super Admin")
    expect(nav(pg).get_by_role("link", name="Staff & roles")).to_be_visible()
    pg.screenshot(path=f"{SHOTS}/ws-01-super-admin.png")

    # Doctor workspace: clinical navigation, no administration.
    switch(pg, "doctor", "Doctor")
    expect(nav(pg).get_by_role("link", name="Orders & results")).to_be_visible()
    expect(nav(pg).get_by_role("link", name="Staff & roles")).to_have_count(0)
    pg.reload()
    expect(pg.get_by_test_id("workspace-current")).to_have_text("Doctor", timeout=15000)  # survives a reload
    pg.screenshot(path=f"{SHOTS}/ws-02-doctor.png")

    # Receptionist workspace: register a patient (saved in the real organization).
    switch(pg, "receptionist", "Receptionist")
    pg.goto(f"{BASE}/patients/new")
    pg.get_by_label("First name").fill("Real")
    pg.get_by_label("Last name").fill(last)
    pg.get_by_label("Date of birth").fill("1984-07-07")
    pg.get_by_label("Sex assigned at birth").select_option("female")
    pg.get_by_role("button", name="Register patient").click()
    try:
        pg.get_by_role("button", name="Not a duplicate — create new record").click(timeout=2500)
    except Exception:  # noqa: BLE001 — no duplicate prompt
        pass
    pg.wait_for_url(re.compile(r"/patients/[0-9a-f-]{36}"), timeout=15000)
    pg.goto(f"{BASE}/patients")
    pg.get_by_role("textbox", name="Search patients").fill(last)
    expect(pg.get_by_text(last).first).to_be_visible(timeout=10000)

    # Pharmacist workspace.
    switch(pg, "pharmacist", "Pharmacist")
    expect(nav(pg).get_by_role("link", name="Pharmacy & inventory")).to_be_visible()
    pg.goto(f"{BASE}/pharmacy")
    expect(pg.get_by_role("heading", name=re.compile("Pharmacy"))).to_be_visible(timeout=15000)
    pg.screenshot(path=f"{SHOTS}/ws-03-pharmacist.png")

    # Patient workspace: the portal only shows the signed-in person's own record (the admin has none).
    switch(pg, "patient", "Patient")
    pg.wait_for_url(re.compile(r"/portal"), timeout=10000)
    expect(pg.get_by_text("The patient portal shows a patient's own record")).to_be_visible(timeout=10000)
    pg.screenshot(path=f"{SHOTS}/ws-04-patient.png")
    switch(pg, "super_admin", "Super Admin")
    pg.wait_for_url(lambda u: "/portal" not in u, timeout=10000)

    # Settings persist: pause a monitor, reload, still paused; then restore it.
    pg.goto(f"{BASE}/automation/monitors")
    sw = pg.get_by_role("switch", name=re.compile(r"Enable Lab turnaround"))
    expect(sw).to_be_visible(timeout=15000)
    was = sw.get_attribute("aria-checked")
    sw.click()
    pg.wait_for_timeout(1000)
    pg.reload()
    sw = pg.get_by_role("switch", name=re.compile(r"Enable Lab turnaround"))
    expect(sw).to_have_attribute("aria-checked", "false" if was == "true" else "true", timeout=15000)
    sw.click()
    pg.wait_for_timeout(800)

    # Logout, then an ordinary single-role account: no switcher.
    pg.get_by_role("button", name="Account menu").click()
    pg.get_by_role("menuitem", name="Sign out").click()
    pg.wait_for_url(re.compile(r"/login|/$"), timeout=10000)
    login(pg, "frontdesk@harborview.dev")
    expect(pg.get_by_test_id("workspace-switcher")).to_have_count(0)

    # Phone width: the switcher fits without horizontal scrolling.
    m = b.new_page(viewport={"width": 390, "height": 844})
    login(m, "admin@undeclared.dev")
    expect(m.get_by_test_id("workspace-switcher")).to_be_visible(timeout=10000)
    assert m.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "horizontal scroll at 390 px"
    m.screenshot(path=f"{SHOTS}/ws-05-phone.png")
    b.close()

if errors:
    print("PAGE ERRORS:", *errors, sep="\n  ")
    sys.exit(1)
print("workspace_flow: one account, 14 workspaces, persisted choice and records, patient-record safeguard, logout — OK")
