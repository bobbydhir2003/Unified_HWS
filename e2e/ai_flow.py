"""UI E2E (phase 10): chart assistant with citations + refusal; urgent message triage → task; AI receptionist booking; automation studio."""
import sys, uuid
import httpx
from playwright.sync_api import sync_playwright, expect

OUT = sys.argv[1]; errors = []
pat = httpx.Client(base_url="http://localhost:5173/api")
t = pat.post("/auth/login", json={"email": "patient@harborview.dev", "password": "Undeclared!2026"}).json()
pat.headers["Authorization"] = "Bearer " + t["access_token"]
tag = uuid.uuid4().hex[:5]
pat.post("/portal/messages", json={"subject": f"Help {tag}", "body": "I've had chest pain since this morning"})

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True)
    def login(email):
        pg = b.new_page(viewport={"width": 1440, "height": 950}); pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto("http://localhost:5173/login")
        pg.fill("input[type=email]", email); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
        pg.wait_for_function("!location.pathname.startsWith('/login')")
        return pg
    doc = login("dr.chen@harborview.dev")
    doc.goto("http://localhost:5173/patients?q=Elena%20Moreau"); doc.locator("tbody tr").first.click(); doc.wait_for_selector("text=MRN")
    doc.get_by_role("button", name="Ask AI").click()
    dlg = doc.get_by_role("dialog")
    dlg.get_by_role("button", name="Summarize this patient's history").click()
    expect(dlg.get_by_text("From the chart")).to_be_visible(timeout=10000)
    expect(dlg.locator("a", has_text="S1").first).to_be_visible()
    dlg.get_by_label("Question").fill("Should I prescribe amoxicillin?"); dlg.get_by_label("Question").press("Enter")
    expect(dlg.get_by_text("Can't help with that")).to_be_visible(timeout=10000)
    doc.screenshot(path=f"{OUT}/ai-01-assistant.png")
    print("assistant: cited summary + refusal")
    doc.keyboard.press("Escape")
    doc.goto("http://localhost:5173/tasks"); expect(doc.get_by_text(f"URGENT Patient message (urgent symptoms): Elena Moreau").first).to_be_visible(timeout=10000)
    print("urgent message → urgent task for doctor")
    front = login("frontdesk@harborview.dev")
    front.goto("http://localhost:5173/receptionist")
    front.get_by_role("button", name="Start call").click(); front.wait_for_selector("text=automated AI assistant")
    for said in ["Yes", "I'd like to book an appointment", "Elena Moreau", "04/12/1986", "option 1"]:
        front.get_by_label("Caller says").fill(said); front.get_by_label("Caller says").press("Enter"); front.wait_for_timeout(700)
    expect(front.get_by_text("You're booked for").first).to_be_visible()
    front.get_by_label("Caller says").fill("That's all, bye"); front.get_by_label("Caller says").press("Enter")
    expect(front.get_by_text("Call completed")).to_be_visible()
    front.screenshot(path=f"{OUT}/ai-02-receptionist.png")
    print("receptionist booked appointment after verification")
    admin = login("clinicadmin@harborview.dev")
    admin.goto("http://localhost:5173/automation"); expect(admin.get_by_text("Patient message triage")).to_be_visible()
    admin.get_by_role("button", name="Activity log").click(); admin.wait_for_timeout(800)
    admin.screenshot(path=f"{OUT}/ai-03-automation.png")
    admin.goto("http://localhost:5173/admin/ai"); expect(admin.get_by_text("PHI sent externally")).to_be_visible()
    print("automation studio + AI monitoring render")
    b.close()
print("page errors:", errors)
