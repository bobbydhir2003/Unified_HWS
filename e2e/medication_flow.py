"""Closed-loop medication in the browser (synthetic): doctor signs an inpatient order → it waits for the pharmacist →
pharmacist verifies (manual interaction review) and dispenses → nurse documents on the eMAR with simulated scanning:
a wrong wristband is blocked with the reason, the correct scan succeeds. Also checks the three-panel My Work layout."""
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


def client(email):
    c = httpx.Client(base_url=f"{BASE}/api/v1", timeout=30)
    t = c.post("/auth/login", json={"email": email, "password": PW}).json()
    c.headers.update({"Authorization": "Bearer " + t["access_token"], "X-Organization-Id": t["me"]["memberships"][0]["organization_id"]})
    return c


doc, bedm = client("dr.santos@harborview.dev"), client("bedmanager@harborview.dev")
stay = bedm.get("/adt/stays", params={"status": "admitted"}).json()[-1]
pid = stay["patient"]["id"] if "patient" in stay else stay["patient_id"]
# Repeatable: discontinue unfinished Ceftriaxone orders left by earlier runs, so this run's order is the only open one.
for r in doc.get(f"/mar/patients/{pid}").json()["orders"]:
    if r["name"] == "Ceftriaxone" and r["status"] in ("pending_verification", "clarification_needed", "active", "on_hold"):
        doc.post(f"/orders/{r['id']}/discontinue", json={"note": "Superseded by a new E2E run"}).raise_for_status()
o = doc.post("/orders", json={"patient_id": pid, "order_type": "medication", "details": {
    "name": "Ceftriaxone", "strength": "1 g", "dose": "1 g", "route": "intravenous", "sig": "1 g IV once", "quantity": 1, "refills": 0,
    "frequency": "once", "setting": "inpatient"}}).json()
signed = doc.post(f"/orders/{o['id']}/sign", json={"override_reason": "E2E reviewed"})
signed.raise_for_status()
assert signed.json()["status"] == "pending_verification", signed.json()
patient = doc.get(f"/patients/{pid}").json()
name = f"{patient['first_name']} {patient['last_name']}"

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def login(email, width=1440):
        pg = b.new_page(viewport={"width": width, "height": 950})
        pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto(f"{BASE}/login")
        pg.fill("input[type=email]", email); pg.fill("input[type=password]", PW); pg.click("button[type=submit]")
        pg.wait_for_url(lambda u: "/login" not in u)
        return pg

    # Pharmacist verifies (manual interaction review is required) and dispenses.
    rx = login("pharmacist@harborview.dev")
    rx.goto(f"{BASE}/pharmacy?tab=verify")
    rx.get_by_role("row", name=re.compile(re.escape(name))).filter(has_text="Ceftriaxone").first.click()
    sheet = rx.get_by_role("dialog")
    verify = sheet.get_by_role("button", name="Verify")
    expect(verify).to_be_disabled()
    sheet.get_by_role("checkbox").click()
    rx.screenshot(path=f"{SHOTS}/med-01-verify.png")
    verify.click()
    expect(rx.get_by_text("Order verified")).to_be_visible(timeout=10000)
    rx.get_by_role("button", name=re.compile("Verified · to dispense")).click()
    rx.get_by_role("row", name=re.compile(re.escape(name))).filter(has_text="Ceftriaxone").first.click()
    rx.get_by_role("button", name="Dispense dose").click()
    dlg = rx.get_by_role("dialog").last
    lot = dlg.get_by_label("Lot / location")
    expect(lot.locator("option")).not_to_have_count(1, timeout=10000)
    lot.select_option(index=1)
    dlg.get_by_role("button", name="Dispense").click()
    expect(dlg.get_by_test_id("dose-label")).to_contain_text("RXD-", timeout=10000)
    rx.screenshot(path=f"{SHOTS}/med-02-dispensed.png")

    # Nurse documents on the eMAR: wrong wristband blocked, correct scan succeeds.
    rn = login("nurse.kim@harborview.dev")
    rn.goto(f"{BASE}/patients/{pid}/mar")
    row = rn.get_by_test_id("mar-row").filter(has_text="Ceftriaxone").filter(has_text="Active · verified").first
    expect(row).to_be_visible(timeout=10000)
    row.get_by_role("button", name=re.compile("(Due now|Scheduled|Overdue) dose")).first.click()
    dlg = rn.get_by_role("dialog")
    dlg.get_by_label("Patient wristband barcode").fill("PT-WRONG-PATIENT")
    dlg.get_by_label("Simulate scanning a dispensed label").select_option(index=1)
    dlg.get_by_role("button", name="Document as given").click()
    expect(dlg.get_by_test_id("mar-blocked")).to_contain_text("Wrong patient", timeout=10000)
    rn.screenshot(path=f"{SHOTS}/med-03-blocked.png")
    dlg.get_by_role("button", name="Simulate scan").click()
    dlg.get_by_role("button", name="Document as given").click()
    expect(rn.get_by_text("Dose documented as given")).to_be_visible(timeout=10000)
    done = rn.get_by_test_id("mar-row").filter(has_text="Ceftriaxone").filter(has_text="Completed").first
    expect(done.get_by_text(re.compile("^Given$")).first).to_be_visible()
    rn.screenshot(path=f"{SHOTS}/med-04-mar.png")

    # My work: three panels side by side on desktop, one panel with tabs on a phone.
    rn.goto(f"{BASE}/worklist")
    expect(rn.get_by_test_id("work-console").locator(":scope > section")).to_have_count(3)
    rn.get_by_role("button", name="Expand Approvals").click()
    expect(rn.get_by_test_id("work-console").locator(":scope > section")).to_have_count(1)
    rn.screenshot(path=f"{SHOTS}/med-05-mywork-focus.png")
    rn.get_by_role("button", name="Restore Approvals").click()
    rn.screenshot(path=f"{SHOTS}/med-06-mywork.png")
    phone = login("nurse.kim@harborview.dev", width=390)
    phone.goto(f"{BASE}/worklist")
    expect(phone.get_by_role("tab", name=re.compile("Cases"))).to_be_visible()
    assert phone.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), "horizontal scroll on My work at 390 px"
    b.close()

final = doc.get(f"/mar/patients/{pid}").json()
row = next(r for r in final["orders"] if r["id"] == o["id"])
assert row["status"] == "completed" and [a["status"] for a in row["administrations"]] == ["given"], row
if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("medication_flow: OK")
