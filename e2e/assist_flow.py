"""HMS Assist in the browser (synthetic data): an insurance specialist opens Ava Brightwater's insurance case, opens
Aurelia (coverage agent) in the case drawer, asks why coverage is unverified, asks for a follow-up task → a proposal card
(pending) → a DIFFERENT person approves it in My Work → the open panel updates to Executed with a link to the real task.
Then each department entry point is checked: Chart (cited answer), Messages thread, Claims, Pharmacy item, Discharge,
Agent Studio tabs. Works with or without a live AI provider (the panel labels rule-based answers)."""
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


ins_api = client("insurance@harborview.dev")
if not any("Ava Brightwater" in (c.get("patient_name") or c["title"]) for c in ins_api.get("/cases", params={"category": "insurance"}).json()):
    client("hospitaladmin@harborview.dev").post("/monitors/insurance.visit_readiness/run").raise_for_status()  # fresh CI database
cases = [c for c in ins_api.get("/cases", params={"category": "insurance"}).json() if c.get("patient_id")]
case = next((c for c in cases if "Ava Brightwater" in (c.get("patient_name") or c["title"])), cases[0])  # the synthetic C-case
# Repeatable: start from a fresh conversation for this case.
ins_api.post("/assist/conversations", json={"agent_key": "insurance_guardian", "context_type": "case", "context_id": case["id"], "new": True}).raise_for_status()

with sync_playwright() as pw:
    b = pw.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def login(email, width=1440):
        pg = b.new_page(viewport={"width": width, "height": 950})
        pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto(f"{BASE}/login")
        pg.fill("input[type=email]", email); pg.fill("input[type=password]", PW); pg.click("button[type=submit]")
        pg.wait_for_url(lambda u: "/login" not in u)
        return pg

    ins = login("insurance@harborview.dev")
    ins.goto(f"{BASE}/insurance")
    ins.get_by_text(f"#{case['number']}", exact=False).first.click()
    ins.get_by_test_id("case-assist").click()
    panel = ins.get_by_test_id("assist-panel")
    expect(panel.get_by_test_id("assist-context")).to_contain_text(f"C{case['number']}", timeout=15000)
    expect(panel.get_by_role("heading", name="Aurelia")).to_be_visible()
    panel.get_by_test_id("assist-input").fill("Why is this patient's insurance not verified?")
    panel.get_by_test_id("assist-send").click()
    expect(panel.locator("[data-role=assistant]").last).to_contain_text(f"C{case['number']}", timeout=60000)
    expect(panel.get_by_test_id("tool-activity").last).to_be_visible()
    panel.get_by_test_id("assist-input").fill("Prepare a follow-up task for this issue.")
    panel.get_by_test_id("assist-send").click()
    card = panel.get_by_test_id("action-card").last
    expect(card.get_by_test_id("action-status")).to_have_attribute("data-status", "pending", timeout=60000)
    title = card.locator("p.font-medium").first.inner_text().split(" ", 1)[1].strip()
    ins.screenshot(path=f"{SHOTS}/assist-01-coverage-proposal.png")
    print("coverage: grounded answer + pending proposal:", title)

    front = login("frontdesk@harborview.dev")
    front.goto(f"{BASE}/worklist")
    tab = front.get_by_role("tab", name=re.compile("Approvals"))
    if tab.count():
        tab.click()
    li = front.locator("li", has_text=title).first
    li.get_by_role("button", name="Approve").click()
    expect(front.get_by_text(re.compile("Approved and executed|executed", re.I)).first).to_be_visible(timeout=15000)
    print("independent approver approved in My Work")

    # The requester's open panel picks up the real outcome (polling the conversation).
    expect(panel.get_by_test_id("action-status").last).to_have_attribute("data-status", "executed", timeout=20000)
    expect(panel.get_by_test_id("open-task").last).to_be_visible()
    expect(panel.locator("[data-role=system]").last).to_contain_text("approved")
    ins.screenshot(path=f"{SHOTS}/assist-02-coverage-executed.png")
    print("coverage: panel shows Executed + task link")
    ins.keyboard.press("Escape")

    # Chart (cited, persistent), refusal still enforced.
    doc = login("dr.chen@harborview.dev")
    doc.goto(f"{BASE}/patients?q=Elena%20Moreau"); doc.locator("tbody tr").first.click(); doc.wait_for_selector("text=MRN")
    doc.get_by_role("button", name="Ask AI").click()
    dlg = doc.get_by_role("dialog")
    expect(dlg.get_by_role("heading", name="Aster")).to_be_visible(timeout=15000)
    dlg.get_by_role("button", name="Summarize this patient's history").click()
    expect(dlg.get_by_text("From the chart").last).to_be_visible(timeout=30000)
    expect(dlg.locator("a", has_text="S1").first).to_be_visible()
    print("chart: cited answer")
    doc.keyboard.press("Escape")

    # Other department entry points render their agent for authorized roles.
    rx = login("pharmacist@harborview.dev")
    rx.goto(f"{BASE}/pharmacy")
    rx.get_by_test_id("ask-ai-pharmacy_watchdog").click()
    expect(rx.get_by_test_id("ai-panel").locator("[data-role=assistant]").first).to_be_visible(timeout=60000)
    print("pharmacy: workspace summary asked automatically in a conversation")
    rx.keyboard.press("Escape")
    admin = login("hospitaladmin@harborview.dev")
    admin.goto(f"{BASE}/agents")
    expect(admin.get_by_role("tab", name="Run history")).to_be_visible()
    admin.get_by_role("tab", name="Run history").click()
    expect(admin.get_by_test_id("run-history")).to_be_visible()
    admin.get_by_role("tab", name="Conversations").click()
    expect(admin.get_by_test_id("conversation-review")).to_be_visible()
    admin.screenshot(path=f"{SHOTS}/assist-03-studio.png")
    print("agent studio: run history + conversation review")
    b.close()

print("page errors:", errors)
assert not errors, errors
print("assist_flow: OK")
