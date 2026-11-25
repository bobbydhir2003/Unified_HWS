"""Role dashboards in the browser (synthetic data): live metrics and worklists open their workflows; the named AI agent opens
the real conversation panel with the right context; workspace switching changes the dashboard and agent; a disabled agent
shows its real status; mobile keeps the agent one tap away."""
import os
import re
import sys

import httpx
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
PW = "Undeclared!2026"
errors: list[str] = []


def client(email):
    c = httpx.Client(base_url=f"{BASE}/api/v1", timeout=60)
    t = c.post("/auth/login", json={"email": email, "password": PW}).json()
    c.headers.update({"Authorization": "Bearer " + t["access_token"], "X-Organization-Id": t["me"]["memberships"][0]["organization_id"]})
    return c


with sync_playwright() as pw:
    b = pw.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def login(email, w=1600, h=1000):
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto(f"{BASE}/login"); pg.fill("input[type=email]", email); pg.fill("input[type=password]", PW); pg.click("button[type=submit]")
        pg.wait_for_url(lambda u: "/login" not in u)
        expect(pg.get_by_test_id("home-metrics")).to_be_visible(timeout=20000)
        return pg

    # Doctor: metrics and schedule open their workflows; Aster opens on a chosen patient.
    doc = login("dr.chen@harborview.dev")
    expect(doc.get_by_role("heading", level=1)).to_have_text("Your Clinical Command Center")
    expect(doc.get_by_test_id("companion-name")).to_have_text("Aster")
    doc.locator("[data-metric=visits]").click(); doc.wait_for_url(re.compile("/schedule")); doc.go_back()
    q = doc.get_by_test_id("home-queue")
    if q.locator("a[href^='/patients/']").count():
        q.locator("a[href^='/patients/']").first.click(); doc.wait_for_url(re.compile(r"/patients/[0-9a-f-]{36}")); doc.go_back()
    expect(doc.get_by_test_id("companion-ask")).to_be_disabled()  # Aster needs a patient
    doc.get_by_label("Find a patient for Aster").fill("Moreau")
    sel = doc.get_by_test_id("companion-patient")
    expect(sel.locator("option", has_text="Moreau").first).to_be_attached(timeout=15000)
    sel.select_option(index=sel.locator("option").count() - 1)
    doc.get_by_test_id("companion-ask").click()
    panel = doc.get_by_test_id("assist-panel")
    expect(panel.get_by_role("heading", name="Aster")).to_be_visible()
    expect(panel.get_by_test_id("assist-context")).to_contain_text("Patient", timeout=15000)
    doc.screenshot(path=f"{SHOTS}/dash-01-doctor-aster.png")
    doc.keyboard.press("Escape")
    print("doctor: metrics/schedule navigate; Aster opened on a chosen patient")

    # Insurance specialist: Aurelia in a real workspace conversation; the AI team opens another agent.
    ins = login("insurance@harborview.dev")
    expect(ins.get_by_test_id("companion-name")).to_have_text("Aurelia")
    ins.get_by_test_id("companion-ask").click()
    panel = ins.get_by_test_id("assist-panel")
    expect(panel.get_by_test_id("assist-context")).to_contain_text("Your workspace", timeout=15000)
    panel.get_by_test_id("assist-input").fill("Summarize open coverage issues, most urgent first")
    panel.get_by_test_id("assist-send").click()
    expect(panel.locator("[data-role=assistant]").last).to_contain_text("insurance case", timeout=60000)
    ins.keyboard.press("Escape")
    ins.reload(); expect(ins.get_by_test_id("ai-recent")).to_contain_text("Aurelia", timeout=20000)
    ins.get_by_test_id("ai-team").locator("[data-agent=claims_review] button").click()
    expect(ins.get_by_test_id("assist-panel").get_by_role("heading", name="Valora")).to_be_visible(timeout=15000)
    ins.keyboard.press("Escape")
    print("insurance: Aurelia conversation answered; recent AI updated; Valora opens from the team")

    # Disabled agent: real status, no Ask.
    admin_api = client("hospitaladmin@harborview.dev")
    admin_api.put("/agents/pharmacy_watchdog", json={"enabled": False}).raise_for_status()
    try:
        rx = login("pharmacist@harborview.dev")
        expect(rx.get_by_test_id("companion-name")).to_have_text("Veyra")
        expect(rx.get_by_test_id("companion-status")).to_contain_text("Turned off", timeout=15000)
        expect(rx.get_by_test_id("companion-ask")).to_be_disabled()
    finally:
        admin_api.put("/agents/pharmacy_watchdog", json={"enabled": True}).raise_for_status()
    print("pharmacist: disabled Veyra shows its real status")

    # Workspace switching: content, agent and identity note follow the workspace.
    sa = login("admin@undeclared.dev")
    for role, title, agent in (("lab_tech", "Your Laboratory Worklist", "Aster"), ("billing", "Your Revenue Workspace", "Valora"),
                               ("bed_manager", "Your Patient Flow Center", "Elara"), ("doctor", "Your Clinical Command Center", "Aster")):
        sa.get_by_test_id("workspace-switcher").first.click(); sa.get_by_test_id(f"workspace-{role}").click()
        expect(sa.get_by_role("heading", level=1)).to_have_text(title, timeout=15000)
        expect(sa.get_by_test_id("companion-name")).to_have_text(agent)
        expect(sa.get_by_test_id("acting-note")).to_contain_text("as Platform Admin")
    print("super admin: four workspace switches — dashboard, agent and identity note follow")

    m = login("nurse.kim@harborview.dev", 390, 844)
    expect(m.get_by_test_id("companion-jump")).to_contain_text("Ask Elara")
    assert m.evaluate("document.documentElement.scrollWidth") <= 392
    m.get_by_test_id("companion-jump").click(); expect(m.get_by_test_id("ai-companion")).to_be_in_viewport()
    print("mobile: no horizontal scroll; agent one tap away")
    b.close()

print("page errors:", errors)
assert not errors, errors
print("dashboard_flow: OK")
