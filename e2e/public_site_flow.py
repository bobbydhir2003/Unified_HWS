"""Public website (product-first): homepage explains the product without a sign-in form, navigation works, legacy
/modules links redirect to /platform, /login keeps the form, there is no Demo Mode anywhere, and pages fit a 390 px phone."""
import os
import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173").rstrip("/")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []
NOTICE = "© 2026 Sidra Riaz Awan. All rights reserved."

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("pageerror", lambda e: errors.append(str(e)))

    pg.goto(f"{BASE}/")
    expect(pg.get_by_role("heading", level=1)).to_contain_text("Your Entire Hospital")
    expect(pg.locator("input[type=password]")).to_have_count(0)  # no sign-in form on the homepage
    expect(pg.get_by_text("Hospital work crosses departments")).to_be_visible()
    expect(pg.get_by_test_id("journey").locator("li").filter(has=pg.get_by_role("heading"))).to_have_count(8)
    expect(pg.locator("img[src*='/images/product/command-center']").first).to_be_visible()
    expect(pg.get_by_test_id("demo-roles")).to_have_count(0)                     # Demo Mode was retired
    expect(pg.get_by_role("link", name=re.compile("Explore the demo", re.I))).to_have_count(0)
    expect(pg.get_by_test_id("public-copyright")).to_have_text(NOTICE)
    pg.screenshot(path=f"{SHOTS}/public-01-home.png")

    nav = pg.get_by_role("navigation", name="Primary")
    for label, path, heading in [("Platform", "/platform", "One platform"), ("Solutions", "/solutions", "A workspace for every team"),
                                 ("AI & Automation", "/ai-automation", "Automation finds the problem"), ("About", "/about", "Why HMS Workflows exists")]:
        nav.get_by_role("link", name=label).click()
        pg.wait_for_url(f"**{path}")
        expect(pg.get_by_role("heading", level=1)).to_contain_text(heading)
    expect(pg.get_by_test_id("about-copyright")).to_have_text(NOTICE)

    pg.goto(f"{BASE}/modules#ehr")  # legacy link → matching capability area
    pg.wait_for_url(re.compile(r"/platform#clinical-care$"))
    expect(pg.locator("#clinical-care")).to_be_visible()

    pg.get_by_role("link", name="Sign in").first.click()
    pg.wait_for_url("**/login")
    expect(pg.locator("input[type=password]")).to_be_visible()
    expect(pg.get_by_role("link", name="Forgot password?")).to_be_visible()
    expect(pg.get_by_test_id("demo-access")).to_have_count(0)

    m = b.new_page(viewport={"width": 390, "height": 844})
    m.on("pageerror", lambda e: errors.append(f"mobile: {e}"))
    for path in ["/", "/platform", "/solutions", "/ai-automation", "/about", "/login"]:
        m.goto(BASE + path); m.wait_for_timeout(600)
        assert m.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"horizontal scroll at 390 px on {path}"
    m.goto(f"{BASE}/")
    m.get_by_role("button", name="Open menu").click()
    expect(m.get_by_role("navigation", name="Mobile").get_by_role("link", name="AI & Automation")).to_be_visible()
    m.screenshot(path=f"{SHOTS}/public-02-mobile-menu.png")
    b.close()

if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("public_site_flow: OK")
