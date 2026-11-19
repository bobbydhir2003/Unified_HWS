"""Radiology flow (synthetic, repeatable): imaging order (API) → schedule → arrived → exam → complete → report → sign."""
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
pt = front.post("/patients", json={"first_name": "Rad", "last_name": f"Flow{TAG}", "date_of_birth": "1958-08-08", "sex_at_birth": "male",
                                   "confirm_not_duplicate": True}).json()
o = doc.post("/orders", json={"patient_id": pt["id"], "order_type": "imaging", "priority": "stat",
                              "details": {"code": "70450", "clinical_question": "Fall with confusion — rule out bleed"}}).json()
doc.post(f"/orders/{o['id']}/sign", json={}).raise_for_status()
NAME = f"Rad Flow{TAG}"

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 950})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{BASE}/login")
    pg.fill("input[type=email]", "radiology@harborview.dev"); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
    pg.wait_for_url(lambda u: "/login" not in u)
    pg.goto(f"{BASE}/radiology")
    pg.get_by_role("row", name=re.compile(NAME)).get_by_role("button", name="Schedule").click()
    expect(pg.get_by_text("Study scheduled")).to_be_visible(timeout=10000)
    row = pg.get_by_role("row", name=re.compile(NAME))
    for btn, msg in [("Arrived", "Patient arrived"), ("Start exam", "Exam started"), ("Complete", "Exam completed — ready to read")]:
        row.get_by_role("button", name=btn).click()
        expect(pg.get_by_text(msg)).to_be_visible(timeout=10000)
    row.get_by_role("button", name="Report").click()
    dlg = pg.get_by_role("dialog")
    dlg.get_by_label("Findings").fill("No acute intracranial hemorrhage, mass effect or midline shift.")
    dlg.get_by_label("Impression").fill("No acute intracranial abnormality.")
    dlg.get_by_role("button", name="Save draft").click()
    expect(pg.get_by_text("Draft saved")).to_be_visible(timeout=10000)
    row.get_by_role("button", name="Sign").click()
    expect(pg.get_by_text("Report signed and sent")).to_be_visible(timeout=10000)
    pg.screenshot(path=f"{SHOTS}/rad-01-signed.png")
    b.close()

order = doc.get(f"/orders/{o['id']}").json()
assert order["status"] == "resulted" and "No acute intracranial abnormality" in order["result_text"], order
if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("radiology_flow: OK")
