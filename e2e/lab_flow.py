"""Lab flow (synthetic, repeatable): physician orders CBC (API) → lab collects + accessions + enters results →
a second technologist verifies → physician sees the verified result in the chart."""
import os
import re
import sys
import uuid

import httpx
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []
TAG = uuid.uuid4().hex[:5]


def client(email):
    c = httpx.Client(base_url=f"{BASE}/api/v1")
    t = c.post("/auth/login", json={"email": email, "password": "Undeclared!2026"}).json()
    c.headers.update({"Authorization": "Bearer " + t["access_token"], "X-Organization-Id": t["me"]["memberships"][0]["organization_id"]})
    return c


front, doc = client("frontdesk@harborview.dev"), client("dr.santos@harborview.dev")
pt = front.post("/patients", json={"first_name": "Lab", "last_name": f"Flow{TAG}", "date_of_birth": "1966-06-06", "sex_at_birth": "female",
                                   "confirm_not_duplicate": True}).json()
o = doc.post("/orders", json={"patient_id": pt["id"], "order_type": "lab", "priority": "stat", "details": {"code": "58410-2"}}).json()
doc.post(f"/orders/{o['id']}/sign", json={}).raise_for_status()
NAME = f"Lab Flow{TAG}"

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def login(email):
        pg = b.new_page(viewport={"width": 1440, "height": 950})
        pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto(f"{BASE}/login")
        pg.fill("input[type=email]", email); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
        pg.wait_for_url(lambda u: "/login" not in u)
        return pg

    lab = login("lab@harborview.dev")
    lab.goto(f"{BASE}/lab")
    lab.get_by_role("row", name=re.compile(NAME)).get_by_role("button", name="Collect").click()
    lab.get_by_role("dialog").get_by_role("button", name="Collect & label").click()
    expect(lab.get_by_text(re.compile("Collected — accession"))).to_be_visible(timeout=10000)
    lab.get_by_role("tab", name=re.compile("Bench")).click()
    card = lab.get_by_test_id("specimen-card").filter(has_text=NAME).first
    card.get_by_role("button", name="Receive").click()
    expect(lab.get_by_text("Accessioned")).to_be_visible(timeout=10000)
    card.get_by_role("button", name="Enter results").click()
    dlg = lab.get_by_role("dialog")
    for name, val in [("WBC", "7.2"), ("Hemoglobin", "13.4"), ("Platelets", "250")]:
        dlg.get_by_label(f"{name} value").fill(val)
    dlg.get_by_role("button", name="Save preliminary").click()
    expect(lab.get_by_text("Results saved (preliminary)")).to_be_visible(timeout=10000)
    expect(card.get_by_role("button", name="Verify")).to_be_disabled()  # same person can't verify
    lab2 = login("lab2@harborview.dev")
    lab2.goto(f"{BASE}/lab?tab=bench")
    lab2.get_by_test_id("specimen-card").filter(has_text=NAME).first.get_by_role("button", name="Verify").click()
    expect(lab2.get_by_text("Verified and sent to the clinician")).to_be_visible(timeout=10000)
    lab2.screenshot(path=f"{SHOTS}/lab-01-verified.png")
    b.close()

order = doc.get(f"/orders/{o['id']}").json()
assert order["status"] == "resulted" and {r["status"] for r in order["results"]} == {"final"}, order
if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("lab_flow: OK")
