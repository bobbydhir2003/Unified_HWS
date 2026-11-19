"""UI E2E: Rx with allergy warning → override sign → med list; lab order → simulated result → review & release → Results tab."""
import os
import sys, random
import httpx
from playwright.sync_api import sync_playwright, expect
OUT = sys.argv[1]; errors = []
# Setup via API: a patient with a penicillin allergy and an open encounter
c = httpx.Client(base_url="http://localhost:5173/api")
tok = c.post("/auth/login", json={"email": "dr.chen@harborview.dev", "password": "Undeclared!2026"}).json()
c.headers["Authorization"] = "Bearer " + tok["access_token"]
clinic = next(x for x in tok["me"]["memberships"][0]["clinics"] if x["code"] == "HDT")["id"]
p = c.post("/patients", json={"first_name": "Orderly", "last_name": f"Uitest{random.randint(100,999)}", "date_of_birth": "1966-06-06",
                              "sex_at_birth": "female", "confirm_not_duplicate": True}).json()
c.post(f"/patients/{p['id']}/allergies", json={"substance": "Penicillin", "severity": "severe", "reaction": "Anaphylaxis"})
enc = c.post("/encounters", json={"patient_id": p["id"], "clinic_id": clinic, "chief_complaint": "Sore throat"}).json()
with sync_playwright() as pw:
    b = pw.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 1000})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://localhost:5173/login")
    pg.fill("input[type=email]", "dr.chen@harborview.dev"); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
    pg.wait_for_url("http://localhost:5173/")
    pg.goto(f"http://localhost:5173/encounters/{enc['id']}"); pg.wait_for_selector("text=Visit in progress")
    # Medication order
    pg.get_by_role("button", name="New", exact=True).click()
    dlg = pg.get_by_role("dialog"); dlg.get_by_label("Search medications").fill("amox")
    dlg.get_by_role("button", name="Amoxicillin capsule").click()
    dlg.get_by_role("button", name="Save draft order").click(); expect(dlg).to_be_hidden()
    pg.get_by_role("button", name="Sign", exact=True).first.click()
    sd = pg.get_by_role("dialog")
    expect(sd).to_contain_text("allergy to Penicillin")
    expect(sd.get_by_role("button", name="Override & sign")).to_be_disabled()
    sd.get_by_label("Override reason").fill("Allergy history unclear; patient tolerated amoxicillin in 2024")
    pg.screenshot(path=f"{OUT}/orders-01-safety.png")
    sd.get_by_role("button", name="Override & sign").click(); expect(sd).to_be_hidden()
    print("Rx signed with override")
    # Lab order
    pg.get_by_role("button", name="New", exact=True).click()
    dlg = pg.get_by_role("dialog"); dlg.get_by_role("tab", name="Lab").click()
    dlg.get_by_role("button", name="Lipid panel").click(); dlg.get_by_role("button", name="Save draft order").click(); expect(dlg).to_be_hidden()
    pg.get_by_role("button", name="Sign", exact=True).first.click()
    pg.get_by_role("dialog").get_by_role("button", name="Sign & send").click(); pg.wait_for_timeout(800)
    pg.get_by_role("button", name="Lipid panel").click()
    pg.get_by_role("button", name="Simulate result").click(); pg.wait_for_selector("text=Results ·")
    pg.screenshot(path=f"{OUT}/orders-02-result.png")
    pg.get_by_role("button", name="Review & release to patient").click(); pg.wait_for_selector("text=released to patient portal")
    pg.keyboard.press("Escape")
    print("lab resulted, reviewed, released")
    pg.goto(f"http://localhost:5173/patients/{p['id']}/medications"); pg.wait_for_timeout(1000)
    expect(pg.locator("main")).to_contain_text("Amoxicillin")
    pg.goto(f"http://localhost:5173/patients/{p['id']}/results"); pg.wait_for_timeout(1000)
    expect(pg.locator("main")).to_contain_text("LDL cholesterol")
    expect(pg.locator("main")).to_contain_text("Released")
    pg.screenshot(path=f"{OUT}/orders-03-results-tab.png")
    pg.goto("http://localhost:5173/orders?queue=all"); pg.wait_for_timeout(1000)
    expect(pg.locator("main")).to_contain_text("Amoxicillin 250 mg")
    b.close()
print("page errors:", errors)
