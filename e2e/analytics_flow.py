"""UI E2E (phase 11): analytics tabs render from live data; care-gap outreach; CSV export download."""
import sys
from playwright.sync_api import sync_playwright, expect

OUT = sys.argv[1]; errors = []
with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://localhost:5173/login")
    pg.fill("input[type=email]", "dr.okafor@harborview.dev"); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
    pg.wait_for_function("!location.pathname.startsWith('/login')")
    pg.goto("http://localhost:5173/analytics?days=90"); pg.wait_for_selector("text=Daily volume")
    pg.get_by_role("button", name="All locations").click(); pg.wait_for_timeout(1200)
    pg.screenshot(path=f"{OUT}/an-01-ops.png")
    for tab, marker in [("Providers", "Provider productivity"), ("Population health", "Chronic disease registries"), ("Quality", "Quality measures")]:
        pg.get_by_role("button", name=tab, exact=True).click(); expect(pg.get_by_text(marker)).to_be_visible()
    pg.screenshot(path=f"{OUT}/an-02-quality.png")
    pg.get_by_role("button", name="Care gaps", exact=True).click(); pg.wait_for_selector("text=Diabetes — no HbA1c in 6 months")
    pg.wait_for_timeout(800)
    pg.get_by_role("checkbox", name="Select all").click()
    if pg.get_by_role("button", name="Create").count():
        pg.get_by_role("button", name="Create").click()
        expect(pg.get_by_text("outreach task(s) created")).to_be_visible()
    # Either way, every patient in this gap now has an open outreach task (outreach is idempotent).
    expect(pg.get_by_text("Task open").first).to_be_visible()
    assert pg.get_by_role("button", name="Create").count() == 0
    with pg.expect_download() as dl:
        pg.get_by_role("button", name="CSV").click()
    path = dl.value.path(); first = open(path).readline()
    assert first.startswith("measure,patient"), first
    pg.screenshot(path=f"{OUT}/an-03-gaps.png")
    print("analytics tabs, outreach and CSV export OK")
    b.close()
print("page errors:", errors)
