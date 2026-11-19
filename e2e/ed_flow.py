"""ED flow (synthetic data, no reseed needed): unidentified arrival → nurse triage → room → physician assign + admit
(boarding) → identity reconciliation into a verified chart created for this run."""
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
COMPLAINT = f"Fall from ladder {TAG}"

# A verified chart to reconcile into (unique per run).
api = httpx.Client(base_url=f"{BASE}/api/v1")
tok = api.post("/auth/login", json={"email": "frontdesk@harborview.dev", "password": "Undeclared!2026"}).json()
api.headers.update({"Authorization": "Bearer " + tok["access_token"], "X-Organization-Id": tok["me"]["memberships"][0]["organization_id"]})
REAL = f"Verified{TAG}"
api.post("/patients", json={"first_name": "Jordan", "last_name": REAL, "date_of_birth": "1979-04-04", "sex_at_birth": "male",
                            "confirm_not_duplicate": True}).raise_for_status()

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def login(email):
        pg = b.new_page(viewport={"width": 1440, "height": 950})
        pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto(f"{BASE}/login")
        pg.fill("input[type=email]", email); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
        pg.wait_for_url(lambda u: "/login" not in u)
        return pg

    rn = login("nurse.kim@harborview.dev")
    rn.goto(f"{BASE}/ed")
    rn.get_by_role("button", name="New arrival").click()
    dlg = rn.get_by_role("dialog")
    dlg.get_by_text("Patient can't be identified yet").click()
    dlg.get_by_label("Approximate age").fill("45")
    dlg.get_by_label("Chief complaint").fill(COMPLAINT)
    dlg.get_by_role("button", name="Register").click()
    expect(rn.get_by_text("Patient registered in the ED")).to_be_visible(timeout=10000)
    row = rn.get_by_role("row", name=re.compile(COMPLAINT))
    row.get_by_role("button", name="Triage").click()
    dlg = rn.get_by_role("dialog")
    dlg.get_by_role("button", name="2", exact=True).click()
    dlg.get_by_label("HR").fill("112")
    dlg.get_by_role("button", name="Save triage").click()
    expect(rn.get_by_text("Triage recorded (ESI 2)")).to_be_visible(timeout=10000)
    row.get_by_role("button", name="Room").click()
    rn.get_by_role("dialog").locator("select").select_option(index=1)
    rn.get_by_role("dialog").get_by_role("button", name="Room").click()
    expect(rn.get_by_text("Patient roomed")).to_be_visible(timeout=10000)

    md = login("dr.santos@harborview.dev")
    md.goto(f"{BASE}/ed")
    row = md.get_by_role("row", name=re.compile(COMPLAINT))
    row.get_by_role("button", name="Assign me").click()
    expect(md.get_by_text("You're the provider for this patient")).to_be_visible(timeout=10000)
    row.get_by_role("button", name="Disposition").click()
    dlg = md.get_by_role("dialog")
    dlg.locator("select").first.select_option("admit")
    dlg.get_by_role("button", name="Confirm").click()
    expect(md.get_by_text("Admission requested — patient boarding")).to_be_visible(timeout=10000)
    md.screenshot(path=f"{SHOTS}/ed-01-board.png")

    rn.reload()
    row = rn.get_by_role("row", name=re.compile(COMPLAINT))
    row.get_by_role("button", name="Identify").click()
    dlg = rn.get_by_role("dialog")
    dlg.get_by_label("Find patient").fill(REAL)
    dlg.get_by_role("button", name=re.compile(REAL)).first.click()
    dlg.get_by_label("How was identity verified?").fill("Driver's license checked at bedside")
    dlg.get_by_role("checkbox").click()
    dlg.get_by_role("button", name="Merge records").click()
    expect(rn.get_by_text("Records merged into the verified chart")).to_be_visible(timeout=10000)
    expect(rn.get_by_role("row", name=re.compile(REAL))).to_be_visible(timeout=10000)
    b.close()

if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("ed_flow: OK")
