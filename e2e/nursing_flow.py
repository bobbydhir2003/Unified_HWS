"""Nursing documentation in the browser (synthetic): record intake/output on the flowsheet (totals update), then
start, complete and sign a fall-risk assessment; the signed record shows the signer."""
import os
import re
import sys

import httpx
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []
PW = "Undeclared!2026"

c = httpx.Client(base_url=f"{BASE}/api/v1", timeout=30)
t = c.post("/auth/login", json={"email": "bedmanager@harborview.dev", "password": PW}).json()
c.headers.update({"Authorization": "Bearer " + t["access_token"], "X-Organization-Id": t["me"]["memberships"][0]["organization_id"]})
stay = c.get("/adt/stays", params={"status": "admitted"}).json()[0]
pid = stay["patient"]["id"] if "patient" in stay else stay["patient_id"]

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 950})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{BASE}/login")
    pg.fill("input[type=email]", "nurse.kim@harborview.dev"); pg.fill("input[type=password]", PW); pg.click("button[type=submit]")
    pg.wait_for_url(lambda u: "/login" not in u)
    pg.goto(f"{BASE}/patients/{pid}/nursing")
    expect(pg.get_by_test_id("nursing-docs")).to_be_visible(timeout=10000)
    before = int(re.sub(r"[^\d-]", "", pg.get_by_test_id("io-intake").inner_text()))
    pg.get_by_role("button", name="Record observations").click()
    dlg = pg.get_by_role("dialog")
    dlg.get_by_label("Oral (mL)").fill("240")
    dlg.get_by_label("Urine (mL)").fill("180")
    dlg.get_by_label("Level of consciousness").select_option("Alert")
    dlg.get_by_role("button", name="Save observations").click()
    expect(pg.get_by_test_id("io-intake")).to_have_text(f"{before + 240} mL", timeout=10000)
    pg.screenshot(path=f"{SHOTS}/nursing-01-flowsheet.png")

    pg.get_by_role("button", name="Assessments").click()
    pg.get_by_label("Assessment template").select_option("fall_risk")
    pg.get_by_role("button", name="Start assessment").click()
    dlg = pg.get_by_role("dialog")
    dlg.get_by_label("History of falls").select_option("No")
    dlg.get_by_label("Gait").select_option("Unsteady")
    dlg.get_by_label("Walking aid").select_option("Cane / frame")
    dlg.get_by_label("Aware of own limitations").select_option("Yes")
    dlg.get_by_label("Precautions in place").fill("Bed in low position, call bell in reach")
    dlg.get_by_role("button", name="Sign assessment").click()
    expect(pg.get_by_text("Assessment signed")).to_be_visible(timeout=10000)
    expect(pg.get_by_text(re.compile("Signed by Grace Kim")).first).to_be_visible()
    pg.screenshot(path=f"{SHOTS}/nursing-02-assessment.png")
    b.close()

if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("nursing_flow: OK")
