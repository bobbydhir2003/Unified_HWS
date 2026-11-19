"""Command Center drill-down (synthetic data): tiles → filtered queue → case drawer → work area; AI workspace status."""
import os
import sys

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 950})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{BASE}/login")
    pg.fill("input[type=email]", "clinicadmin@harborview.dev"); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
    pg.wait_for_url(lambda u: "/login" not in u)
    pg.goto(f"{BASE}/command")
    expect(pg.get_by_role("heading", name="Command Center")).to_be_visible()
    expect(pg.get_by_text("Insurance issues")).to_be_visible(timeout=10000)
    expect(pg.get_by_text("Live", exact=True)).to_be_visible(timeout=10000)  # SSE connected
    pg.screenshot(path=f"{SHOTS}/cc-01-overview.png")
    # Drill: matrix cell → filtered queue → case drawer with evidence and timeline.
    pg.get_by_label("Category").select_option("insurance")
    first = pg.locator("ul.divide-y li button").first
    expect(first).to_be_visible(timeout=10000)
    first.click()
    drawer = pg.get_by_role("dialog")
    expect(drawer.get_by_text("Timeline")).to_be_visible()
    expect(drawer.get_by_text("Evidence (what the rule saw)")).to_be_visible()
    pg.screenshot(path=f"{SHOTS}/cc-02-drawer.png")
    drawer.get_by_role("link", name="Open work area").click()
    pg.wait_for_url("**/insurance**")
    # Tile drill-down.
    pg.goto(f"{BASE}/command")
    pg.get_by_role("button", name="Insurance issues").click()
    pg.wait_for_url("**/insurance")
    pg.goto(f"{BASE}/ai")
    expect(pg.get_by_text("Rule-based simulation").first).to_be_visible()
    pg.screenshot(path=f"{SHOTS}/cc-03-ai-workspace.png")
    b.close()

if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("command_center_flow: OK")
