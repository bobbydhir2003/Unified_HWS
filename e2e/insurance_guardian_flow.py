"""Insurance Guardian browser flow (synthetic data; run against a freshly seeded dev DB).

Staff sees the detected case → patient uploads a card in the portal → staff reviews the AI draft against the typed values,
attests and confirms → payer re-check (simulated) → the monitor verifies and closes the case.
"""
import os
import sys

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def login(email):
        pg = b.new_page(viewport={"width": 1440, "height": 950})
        pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto(f"{BASE}/login")
        pg.fill("input[type=email]", email); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
        pg.wait_for_url(lambda u: "/login" not in u)
        return pg

    staff = login("insurance@harborview.dev")
    staff.goto(f"{BASE}/worklist")
    row = staff.get_by_role("button", name="Payer reports coverage inactive — Elena Moreau").first
    expect(row).to_be_visible(timeout=10000)
    row.click()
    drawer = staff.get_by_role("dialog")
    expect(drawer.get_by_text("Evidence (what the rule saw)")).to_be_visible()
    expect(drawer.get_by_text("Asked the patient to confirm or update insurance in the portal")).to_be_visible()
    staff.screenshot(path=f"{SHOTS}/ig-01-case-drawer.png")
    staff.keyboard.press("Escape")

    pt = login("patient@harborview.dev")
    prompt = pt.get_by_role("link", name="Please confirm your insurance")
    expect(prompt).to_be_visible(timeout=10000)
    prompt.click()
    pt.wait_for_url("**/portal/insurance")
    pt.get_by_label("Member ID").fill("TYPO-12345")
    pt.get_by_role("button", name="Use a synthetic demo card").click()
    expect(pt.get_by_text("Thanks — your care team is reviewing your card")).to_be_visible(timeout=15000)
    pt.screenshot(path=f"{SHOTS}/ig-02-portal-submitted.png")

    staff.goto(f"{BASE}/insurance?tab=review")
    staff.get_by_role("button", name="Elena Moreau").first.click()
    expect(staff.get_by_text("Read from card")).to_be_visible()
    expect(staff.get_by_label("Mismatch").first).to_be_visible()  # typed member id differs from the card
    staff.screenshot(path=f"{SHOTS}/ig-03-card-review.png")
    confirm = staff.get_by_role("button", name="Confirm & re-verify")
    expect(confirm).to_be_disabled()
    staff.get_by_role("checkbox").click()
    confirm.click()
    expect(staff.get_by_text("Coverage confirmed — re-verified with the payer")).to_be_visible(timeout=10000)

    staff.goto(f"{BASE}/insurance")
    expect(staff.get_by_text("Visits ready (next 7 days)")).to_be_visible()
    expect(staff.get_by_role("button", name="Payer reports coverage inactive — Elena Moreau")).to_have_count(0, timeout=10000)
    staff.screenshot(path=f"{SHOTS}/ig-04-dashboard.png")

    b.close()

if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("insurance_guardian_flow: OK")
