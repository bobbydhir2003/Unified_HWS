"""Public website (vision redesign): the homepage explains the problem and the product without a sign-in form, navigation
works (Home · How It Works · Solutions · AI & Automation · About · Sign in), no public CTA points to Demo Mode, the patient
pathways are separate, the AI page lists all 22 monitors and 10 assistants, legacy links still land on the right section,
/login keeps the form, pages fit a 390 px phone, and the tabbed pathway is keyboard operable.
Needs only the web server; the public pages work signed out with or without the API."""
import os
import re
import sys

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from public_site_content_check import check as content_check  # noqa: E402

content_check()  # site copy matches the 22 monitors and 10 assistants in the code

BASE = os.environ.get("WEB", "http://localhost:5173").rstrip("/")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []
NOTICE = "© 2026 Sidra Riaz Awan. All rights reserved."
PAGES = ["/", "/platform", "/solutions", "/ai-automation", "/about", "/login"]
KNOWN_ROUTES = {"/", "/platform", "/solutions", "/ai-automation", "/about", "/login", "/forgot-password"}


def no_demo_links(pg, path):
    hrefs = pg.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    bad = [h for h in hrefs if "#demo" in h or "demo-login" in h]
    assert not bad, f"demo links on {path}: {bad}"
    text = pg.locator("main").inner_text().lower() + pg.locator("header").inner_text().lower()
    assert "explore the demo" not in text and "try as " not in text, f"demo CTA text on {path}"


def no_broken_internal_links(pg, path):
    hrefs = set(pg.eval_on_selector_all("header a[href], main a[href], footer a[href]", "els => els.map(e => e.getAttribute('href'))"))
    for h in hrefs:
        assert h.startswith(("/", "#")), f"external or relative link {h} on {path}"
        route, _, frag = h.partition("#")
        route = route or path
        assert route in KNOWN_ROUTES, f"unknown route {h} on {path}"
        if frag and route == path:
            assert pg.locator(f"[id='{frag}']").count() == 1, f"missing anchor #{frag} on {path}"
    return hrefs


with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("pageerror", lambda e: errors.append(str(e)))

    # Home: problem-first story, no sign-in form, sign-in CTA, tagline preserved.
    pg.goto(f"{BASE}/")
    expect(pg.get_by_role("heading", level=1)).to_contain_text("One Patient. One Connected Hospital.")
    expect(pg.get_by_test_id("hero-tagline")).to_have_text("Your Entire Hospital. Working as One.")
    expect(pg.locator("input[type=password]")).to_have_count(0)
    expect(pg.get_by_text("A hospital has many teams. The patient journey is one connected process.")).to_be_visible()
    expect(pg.get_by_test_id("problems").locator(":scope > li")).to_have_count(4)
    expect(pg.get_by_test_id("pillars").locator(":scope > li")).to_have_count(4)
    expect(pg.get_by_test_id("guardian-steps").locator(":scope > li")).to_have_count(7)
    expect(pg.get_by_test_id("team-cards").locator(":scope > li")).to_have_count(6)
    expect(pg.locator("img[src*='/images/product/command-center']").first).to_be_visible()
    expect(pg.get_by_test_id("public-copyright")).to_have_text(NOTICE)
    expect(pg.get_by_test_id("demo-roles")).to_have_count(0)

    # Pathways: outpatient / emergency / inpatient are separate tabs (mouse and keyboard).
    expect(pg.get_by_role("tab")).to_have_count(3)
    journey = pg.get_by_test_id("journey")
    expect(journey.locator("ol > li")).to_have_count(8)
    pg.get_by_role("tab", name="Emergency visit").click()
    expect(journey.locator("ol > li")).to_have_count(6)
    expect(journey).to_contain_text("Triage")
    pg.get_by_role("tab", name="Emergency visit").press("ArrowRight")
    expect(pg.get_by_role("tab", name="Inpatient stay")).to_be_focused()
    expect(pg.get_by_role("tab", name="Inpatient stay")).to_have_attribute("aria-selected", "true")
    expect(journey).to_contain_text("Bed assignment")
    pg.screenshot(path=f"{SHOTS}/public-01-home.png", full_page=True)

    # Primary navigation.
    nav = pg.get_by_role("navigation", name="Primary")
    for label, path, heading in [("How It Works", "/platform", "Five connected layers"), ("Solutions", "/solutions", "Built around the work"),
                                 ("AI & Automation", "/ai-automation", "Rules find the problem"), ("About", "/about", "Why HMS Workflows exists"),
                                 ("Home", "/", "One Patient")]:
        nav.get_by_role("link", name=label, exact=True).click()
        pg.wait_for_url(re.compile(re.escape(BASE + path) + "$"))
        expect(pg.get_by_role("heading", level=1)).to_contain_text(heading)

    # AI & Automation: exactly 22 monitors in 10 groups and 10 assistants (7 launched by staff, 3 inside workflows).
    pg.goto(f"{BASE}/ai-automation")
    expect(pg.locator("[data-monitor]")).to_have_count(22)
    expect(pg.get_by_test_id("monitor-groups").locator(":scope > section")).to_have_count(10)
    expect(pg.get_by_test_id("assistants-launched").locator("[data-assistant]")).to_have_count(7)
    expect(pg.get_by_test_id("assistants-embedded").locator("[data-assistant]")).to_have_count(3)
    expect(pg.get_by_test_id("automation-flow").locator(":scope > li")).to_have_count(7)
    expect(pg.get_by_test_id("automation-flow")).to_contain_text("optional")

    pg.goto(f"{BASE}/about")
    expect(pg.get_by_test_id("about-copyright")).to_have_text(NOTICE)
    expect(pg.get_by_test_id("product-status")).to_contain_text("Not certified")

    # Every page: no demo CTAs, internal links and same-page anchors resolve, all images load; desktop screenshots.
    for i, path in enumerate(PAGES):
        pg.goto(BASE + path)
        expect(pg.get_by_role("heading", level=1).first).to_be_attached(timeout=15000)
        pg.wait_for_timeout(500)
        no_demo_links(pg, path)
        no_broken_internal_links(pg, path)
        pg.evaluate("Promise.all([...document.images].map(i => { i.loading = 'eager'; return i.decode().catch(() => {}); }))")
        pg.wait_for_timeout(400)
        broken = pg.evaluate("[...document.images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.src)")
        assert not broken, f"broken images on {path}: {broken}"
        pg.screenshot(path=f"{SHOTS}/public-desktop-{i + 1}-{path.strip('/') or 'home'}.png", full_page=True)

    # Cross-page anchors used by the site exist on their target pages.
    for target in ["/platform#records", "/platform#workspaces", "/platform#workflows", "/platform#automation", "/platform#visibility",
                   "/solutions#front-desk", "/solutions#leadership", "/ai-automation#monitors", "/ai-automation#assistants", "/about#status", "/about#legal"]:
        route, frag = target.split("#")
        pg.goto(BASE + target)
        expect(pg.locator(f"[id='{frag}']")).to_have_count(1)

    # Legacy links land on the matching section.
    pg.goto(f"{BASE}/modules#ehr")
    pg.wait_for_url(re.compile(r"/platform#clinical-care$"))
    pg.wait_for_timeout(400)
    expect(pg.locator("#records")).to_be_in_viewport()

    # Sign in opens the existing authentication page.
    pg.goto(f"{BASE}/")
    pg.get_by_role("banner").get_by_role("link", name="Sign in").click()
    pg.wait_for_url("**/login")
    expect(pg.locator("input[type=password]")).to_be_visible()
    expect(pg.get_by_role("link", name="Forgot password?")).to_be_visible()
    expect(pg.get_by_test_id("demo-access")).to_have_count(0)                     # Demo Mode was retired

    # Keyboard: the skip link is the first focusable element.
    pg.goto(f"{BASE}/platform")
    expect(pg.get_by_role("heading", level=1)).to_be_visible()
    pg.keyboard.press("Tab")
    expect(pg.get_by_role("link", name="Skip to content")).to_be_focused()

    # Phone width: no horizontal scroll anywhere; mobile menu works.
    m = b.new_page(viewport={"width": 390, "height": 844})
    m.on("pageerror", lambda e: errors.append(f"mobile: {e}"))
    for i, path in enumerate(PAGES):
        m.goto(BASE + path); m.wait_for_timeout(600)
        assert m.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), f"horizontal scroll at 390 px on {path}"
        m.screenshot(path=f"{SHOTS}/public-mobile-{i + 1}-{path.strip('/') or 'home'}.png", full_page=True)
    m.goto(f"{BASE}/")
    m.get_by_role("button", name="Open menu").click()
    mobile_nav = m.get_by_role("navigation", name="Mobile")
    for label in ["Home", "How It Works", "Solutions", "AI & Automation", "About"]:
        expect(mobile_nav.get_by_role("link", name=label, exact=True)).to_be_visible()
    m.screenshot(path=f"{SHOTS}/public-02-mobile-menu.png")
    b.close()

if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("public_site_flow: OK")
