"""Help & About (synthetic data): every role can open it; role-appropriate guides; search jumps to a topic; links work;
mobile layout has no horizontal scroll; copyright notice shown. Patients get the portal guide."""
import os
import sys

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []
NOTICE = "© 2026 Sidra Riaz Awan. All rights reserved."

# email → (role guide title expected, a module that must have instructions, a module that must be locked or absent)
STAFF = {
    "admin@undeclared.dev": ("Super Admin", "Administration", None),
    "hospitaladmin@harborview.dev": ("Hospital administrator", "Command Center & My work", None),
    "dr.chen@harborview.dev": ("Doctor", "AI Medical Scribe", "Pharmacy & inventory"),
    "nurse.kim@harborview.dev": ("Nurse", "Nursing", "Billing, claims & prior authorization"),
    "frontdesk@harborview.dev": ("Receptionist", "Appointments & front desk", "Laboratory"),
    "billing@harborview.dev": ("Billing & insurance specialist", "Billing, claims & prior authorization", "Nursing"),
    "pharmacist@harborview.dev": ("Pharmacist", "Pharmacy & inventory", "Billing, claims & prior authorization"),
    "lab@harborview.dev": ("Laboratory staff", "Laboratory", "Billing, claims & prior authorization"),
    "radiology@harborview.dev": ("Radiology staff", "Radiology", "Pharmacy & inventory"),
    "bedmanager@harborview.dev": ("Bed manager", "Admissions, beds & discharge", "Pharmacy & inventory"),
}

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def login(email, viewport=(1440, 950)):
        ctx = b.new_context(viewport={"width": viewport[0], "height": viewport[1]})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto(f"{BASE}/login")
        pg.fill("input[type=email]", email); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
        pg.wait_for_url(lambda u: "/login" not in u)
        return pg

    for email, (guide, allowed, locked) in STAFF.items():
        pg = login(email)
        # Reachable from the sidebar for every staff role.
        pg.get_by_role("navigation", name="Main").get_by_role("link", name="Help & About").click()
        pg.wait_for_url("**/help**")
        expect(pg.get_by_role("heading", name="Help & About Undeclared HMS")).to_be_visible()
        pg.get_by_role("tab", name="Role guides").click()
        expect(pg.get_by_test_id("help-role-guide")).to_contain_text(guide)
        pg.get_by_role("tab", name="Features").click()
        feats = pg.get_by_test_id("help-features")
        item = feats.locator("details", has=pg.locator("summary", has_text=allowed)).first
        item.locator("summary").click()
        expect(item.get_by_text("How to use it")).to_be_visible()
        if locked:
            expect(feats.get_by_text(locked, exact=True)).to_have_count(0)  # not in "your areas"
        pg.close()

    # Search → jump to the topic, then follow its link to the real screen.
    pg = login("pharmacist@harborview.dev")
    pg.goto(f"{BASE}/help")
    pg.get_by_label("Search help").fill("expired heparin")
    res = pg.get_by_test_id("help-search-results")
    expect(res).to_be_visible()
    res.get_by_role("button").first.click()
    expect(pg.get_by_role("link", name="Pharmacy & inventory").last).to_be_visible()
    pg.get_by_test_id("help-features").get_by_role("link", name="Pharmacy & inventory").click()
    pg.wait_for_url("**/pharmacy")
    # About: version + copyright.
    pg.goto(f"{BASE}/help?section=about")
    expect(pg.get_by_test_id("help-copyright")).to_have_text(NOTICE)
    expect(pg.get_by_test_id("help-version")).not_to_be_empty()
    pg.close()

    # Mobile layout: no horizontal page scroll; journey readable.
    pg = login("nurse.kim@harborview.dev", (390, 844))
    pg.goto(f"{BASE}/help")
    expect(pg.get_by_test_id("help-journey")).to_be_visible()
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "horizontal scroll on mobile"
    pg.screenshot(path=f"{SHOTS}/help-mobile.png", full_page=True)
    pg.close()

    # Patient: portal guide, not staff documentation.
    pg = login("patient@harborview.dev")
    pg.goto(f"{BASE}/portal")
    pg.get_by_role("navigation", name="Portal").get_by_role("link", name="Help & About").click()
    expect(pg.get_by_test_id("patient-help")).to_be_visible()
    expect(pg.get_by_text("Command Center")).to_have_count(0)
    pg.get_by_label("Search help").fill("video")
    pg.get_by_test_id("help-search-results").get_by_role("button").first.click()
    expect(pg.get_by_text("Join video visit").first).to_be_visible()
    expect(pg.get_by_test_id("help-copyright")).to_have_text(NOTICE)
    pg.screenshot(path=f"{SHOTS}/help-patient.png", full_page=True)
    pg.close()
    b.close()

if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("help_flow: OK")
