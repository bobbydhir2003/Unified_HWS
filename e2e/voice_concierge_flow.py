"""HMS Voice Concierge in the browser (synthetic data): the redesigned console, a natural booking with portal-code verification,
a change of date, explicit confirmation and a real appointment; facility questions; callback and staff handoff tasks; the
call log and a persisted call reopened from its URL; mobile layout; and no access for roles without front-desk scheduling."""
import os
import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
PW = "Undeclared!2026"
errors: list[str] = []

with sync_playwright() as pw:
    b = pw.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def login(email, w=1600, h=1000):
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto(f"{BASE}/login"); pg.fill("input[type=email]", email); pg.fill("input[type=password]", PW); pg.click("button[type=submit]")
        pg.wait_for_url(lambda u: "/login" not in u)
        return pg

    fd = login("frontdesk@harborview.dev")
    fd.get_by_role("navigation", name="Main").get_by_role("link", name="HMS Voice Concierge").click()
    fd.wait_for_url(re.compile("/receptionist"))
    expect(fd.get_by_role("heading", level=1)).to_have_text("HMS Voice Concierge")
    expect(fd.get_by_text("Intelligent assistance for administrative calls, appointments, callbacks, and staff handoffs.")).to_be_visible()
    expect(fd.get_by_test_id("concierge-engine")).to_contain_text("Phone line: Not connected")
    expect(fd.get_by_test_id("concierge-stats").locator("li")).to_have_count(4)
    expect(fd.get_by_test_id("live-call")).to_contain_text("No call open")

    def caller(said):
        n = fd.locator("[data-role=assistant]").count()
        fd.get_by_label("Caller says").fill(said); fd.get_by_label("Caller says").press("Enter")
        expect(fd.locator("[data-role=assistant]")).to_have_count(n + 1, timeout=20000)
        return fd.locator("[data-role=assistant]").last

    fd.get_by_test_id("start-call").click()
    expect(fd.locator("[data-role=assistant]").first).to_contain_text("automated AI assistant")
    expect(caller("Where is your radiology department?")).to_contain_text("Radiology")
    expect(fd.get_by_test_id("tool-activity")).to_contain_text("Facility information looked up")
    expect(caller("Can I come tomorrow?")).to_contain_text("verify your identity")
    expect(fd.get_by_test_id("caller-intent")).to_have_text("Book")
    caller("It's Elena Moreau, April 12, 1986")
    expect(fd.get_by_test_id("caller-verification")).to_have_text("Code sent")
    code = fd.get_by_test_id("test-code").locator("span.font-mono").inner_text()
    expect(caller(code)).to_contain_text("you're verified")
    expect(fd.get_by_test_id("caller-verification")).to_have_text("Verified")
    expect(fd.get_by_test_id("caller-name")).to_have_text("Elena Moreau")
    caller("option 1")
    expect(fd.get_by_test_id("pending-action")).to_be_visible()
    expect(fd.locator("[data-step=confirmation]")).to_have_attribute("data-status", "in_progress")
    expect(caller("Actually, make that Friday")).to_contain_text("haven't booked anything")
    expect(fd.get_by_test_id("pending-action")).to_have_count(0)
    caller("option 1")
    expect(caller("Yes, please book it")).to_contain_text("You're all set")
    expect(fd.locator("[data-step=execution]")).to_have_attribute("data-status", "done")
    expect(fd.get_by_test_id("call-outcome").locator("[data-outcome=booked]")).to_have_attribute("data-active", "true")
    expect(fd.get_by_test_id("call-records").locator("a")).to_have_count(1)
    fd.screenshot(path=f"{SHOTS}/voice-01-booked.png")
    expect(caller("Can someone call me back?")).to_contain_text("reference")
    fd.get_by_test_id("action-handoff").click()
    fd.get_by_label("Reason").fill("Caller wants to discuss parking for a wheelchair")
    fd.get_by_role("button", name="Create task").click()
    expect(fd.locator("[data-step=handoff]")).to_have_attribute("data-status", "done", timeout=10000)
    expect(fd.get_by_test_id("call-records").locator("a")).to_have_count(3)
    url = fd.url
    fd.get_by_test_id("end-call").click()
    expect(fd.get_by_test_id("call-ended")).to_be_visible()
    print("concierge: natural booking with verification, date change, confirmation; callback + staff handoff; call ended")

    # Persistence: the call reopens from its URL; the log lists it without exposing the transcript in the list.
    fd.goto(url)
    expect(fd.get_by_test_id("call-transcript")).to_contain_text("You're all set", timeout=15000)
    row = fd.get_by_test_id("call-log").locator("tbody tr").first
    expect(row).to_contain_text("Elena Moreau")
    expect(row).to_contain_text("Booked")
    fd.get_by_test_id("call-records").locator("a").first.click(); fd.wait_for_url(re.compile("/schedule"))
    print("persistence: call reopens from URL; log row shows the booked outcome; record link opens the schedule")

    m = login("frontdesk@harborview.dev", 390, 844)
    m.goto(f"{BASE}/receptionist")
    expect(m.get_by_role("heading", level=1)).to_have_text("HMS Voice Concierge")
    assert m.evaluate("document.documentElement.scrollWidth") <= 392
    print("mobile: no horizontal scroll")

    bl = login("billing@harborview.dev")
    expect(bl.get_by_role("navigation", name="Main").get_by_role("link", name="HMS Voice Concierge")).to_have_count(0)
    print("billing: no Voice Concierge access")
    b.close()

print("page errors:", errors)
assert not errors, errors
print("voice_concierge_flow: OK")
