"""Insights (synthetic data): cited daily briefing, shadow-mode forecasts, and the cross-department patient journey tab."""
import os
import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []


def login(pg, email):
    pg.goto(f"{BASE}/login")
    pg.fill("input[type=email]", email); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
    pg.wait_for_url(lambda u: "/login" not in u)


with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 950})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    login(pg, "hospitaladmin@harborview.dev")
    pg.goto(f"{BASE}/insights")
    expect(pg.get_by_role("heading", name="Insights")).to_be_visible()
    narrative = pg.get_by_test_id("briefing-narrative")
    expect(narrative).to_be_visible(timeout=15000)
    assert re.search(r"\[M\d+\]", narrative.inner_text()), "briefing must cite numbered metrics"
    expect(pg.get_by_test_id("forecast-label")).to_contain_text("not validated")
    expect(pg.get_by_text("Inpatient census")).to_be_visible(timeout=15000)
    pg.screenshot(path=f"{SHOTS}/insights-01.png", full_page=True)
    b.close()

    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 950})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    login(pg, "dr.chen@harborview.dev")
    pg.goto(f"{BASE}/patients")
    pg.locator("table tbody tr").first.click()
    pg.wait_for_url(re.compile(r"/patients/[0-9a-f-]{36}"))
    pg.get_by_role("link", name="Journey").click()
    expect(pg.get_by_text("across departments")).to_be_visible()
    expect(pg.get_by_test_id("journey").or_(pg.get_by_text("No events yet"))).to_be_visible(timeout=10000)
    pg.screenshot(path=f"{SHOTS}/insights-02-journey.png")
    b.close()

if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("insights_flow: OK")
