"""UI E2E: simulated fax → review queue → identity check → file to chart → visible in chart Documents tab."""
import os
import sys
from playwright.sync_api import sync_playwright, expect
OUT = sys.argv[1]; errors = []
with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://localhost:5173/login")
    pg.fill("input[type=email]", "nurse.rivera@harborview.dev"); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
    pg.wait_for_url("http://localhost:5173/")
    pg.goto("http://localhost:5173/documents")
    pg.get_by_role("button", name="Synthetic test data").click()
    pg.get_by_role("menuitem", name="Referral (clear match)").click()
    pg.get_by_role("button", name="Review").click()
    pg.wait_for_url("**/documents/*"); pg.wait_for_selector("text=AI extraction", timeout=15000)
    pg.wait_for_timeout(1500); pg.screenshot(path=f"{OUT}/doc-01-review.png", full_page=False)
    expect(pg.get_by_role("button", name="File to chart")).to_be_disabled()   # identity not yet confirmed
    pg.get_by_text("I verified the name and date of birth").click()
    patient = pg.locator("text=I verified").locator("strong").inner_text()
    pg.get_by_role("button", name="File to chart").click()
    pg.wait_for_selector(f"text=Filed to {patient}")
    print("filed to", patient)
    pg.goto("http://localhost:5173/documents?status=filed"); pg.wait_for_timeout(1000)
    expect(pg.locator("tbody tr").first).to_contain_text(patient)
    pg.locator("tbody tr").first.click(); pg.wait_for_selector("text=Filed to")
    pg.get_by_role("link", name=patient).click(); pg.wait_for_url("**/documents"); pg.wait_for_timeout(1200)
    expect(pg.locator("main")).to_contain_text("Referral")
    pg.screenshot(path=f"{OUT}/doc-02-chart.png")
    # Ambiguous case: no confident suggestion → filing blocked until a patient is chosen
    pg.goto("http://localhost:5173/documents")
    pg.get_by_role("button", name="Synthetic test data").click()
    pg.get_by_role("menuitem", name="Lab report (unknown patient)").click()
    pg.get_by_role("button", name="Review").click(); pg.wait_for_selector("text=AI extraction", timeout=15000)
    expect(pg.get_by_text("No confident match")).to_be_visible()
    expect(pg.get_by_role("button", name="File to chart")).to_be_disabled()
    pg.screenshot(path=f"{OUT}/doc-03-unknown.png")
    print("unknown patient correctly blocked")
    b.close()
print("page errors:", errors)
