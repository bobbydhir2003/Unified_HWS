"""UI E2E (billing specialist): charge capture → claim → idempotent submit → simulated payer → appeal if denied → patient payment."""
import sys
from playwright.sync_api import sync_playwright, expect

OUT = sys.argv[1]; errors = []
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 950})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://localhost:5173/login")
    pg.fill("input[type=email]", "billing@harborview.dev"); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
    pg.wait_for_function("!location.pathname.startsWith('/login')")
    pg.goto("http://localhost:5173/billing?tab=capture"); pg.wait_for_selector("tbody tr")
    # Pick a visit with a payer (insured) from the queue
    row = pg.locator("tbody tr", has_not_text="Self-pay").first
    patient = row.locator("td").nth(1).locator("span").first.inner_text()
    row.click(); pg.wait_for_selector("text=Suggested codes")
    pg.screenshot(path=f"{OUT}/billing-01-capture.png")
    pg.get_by_role("button", name="Save & create claim").click()
    pg.wait_for_selector("text=created", timeout=10000)
    print("claim created for", patient)
    pg.goto("http://localhost:5173/billing?tab=claims"); pg.wait_for_selector("tbody tr")
    pg.locator("tbody tr", has_text=patient).first.click()
    drawer = pg.get_by_role("dialog")
    drawer.get_by_role("button", name="Submit").click(); expect(drawer).to_contain_text("Accepted", timeout=8000)
    drawer.get_by_role("button", name="Simulate payer response").click(); pg.wait_for_timeout(1200)
    if drawer.get_by_role("button", name="Appeal").count():
        drawer.get_by_role("button", name="Appeal").click()
        pg.get_by_label("Appeal letter").fill("Enclosed documentation supports the services billed on this date of service.")
        pg.get_by_role("button", name="Submit appeal").click(); pg.wait_for_timeout(800)
        drawer.get_by_role("button", name="Simulate appeal decision").click(); pg.wait_for_timeout(1000)
        print("denied → appealed")
    expect(drawer).to_contain_text("Patient responsibility")
    status = drawer.locator("h2").inner_text()
    pg.screenshot(path=f"{OUT}/billing-02-claim.png")
    print("claim outcome:", status.split()[-1])
    pg.keyboard.press("Escape")
    pg.goto("http://localhost:5173/billing?tab=balances"); pg.wait_for_selector("tbody tr")
    inv = pg.locator("tbody tr", has_text=patient).first
    inv.get_by_role("button", name="Payment").click()
    dlg = pg.get_by_role("dialog"); dlg.get_by_label("Amount (USD)").fill("5.00")
    dlg.get_by_role("button", name="Record").click(); expect(dlg).to_be_hidden()
    pg.wait_for_selector("text=Payment of $5.00 recorded")
    pg.goto("http://localhost:5173/billing?tab=overview"); pg.wait_for_selector("text=A/R aging"); pg.wait_for_timeout(800)
    pg.screenshot(path=f"{OUT}/billing-03-overview.png")
    print("payment recorded; overview rendered")
    b.close()
print("page errors:", errors)
