"""UI-driven E2E: register → book → check in → room → start visit → vitals → SOAP → sign → dx → complete → check out."""
import sys, time, random
from playwright.sync_api import sync_playwright, expect
OUT=sys.argv[1]; errors=[]
suffix=str(random.randint(1000,9999))
with sync_playwright() as p:
    b=p.chromium.launch(channel="chrome", headless=True)
    pg=b.new_page(viewport={"width":1440,"height":900})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://localhost:5173/login")
    pg.fill("input[type=email]","dr.chen@harborview.dev"); pg.fill("input[type=password]","Undeclared!2026"); pg.click("button[type=submit]")
    pg.wait_for_url("http://localhost:5173/")
    # Register
    pg.goto("http://localhost:5173/patients/new")
    pg.get_by_label("First name").fill("Uitest"); pg.get_by_label("Last name").fill("Patient"+suffix)
    pg.get_by_label("Date of birth").fill("1984-07-0"+str(random.randint(1,9)))
    pg.get_by_label("Sex assigned at birth").select_option("male")
    pg.get_by_label("Mobile phone").fill("(555) 301-"+suffix)
    pg.get_by_role("button", name="Register patient").click()
    try:  # earlier runs leave similar test patients behind → the duplicate check (correctly) asks
        pg.get_by_role("button", name="Not a duplicate — create new record").click(timeout=2500)
    except Exception:
        pass
    pg.wait_for_url("**/patients/*"); pg.wait_for_selector("text=MRN")
    print("registered", pg.url)
    # Book via banner (override hours so the run is time-independent)
    pg.get_by_role("button", name="Book").first.click()
    dlg=pg.get_by_role("dialog"); dlg.wait_for()
    dlg.get_by_label("Time").fill(f"18:{random.randint(10,49)}")  # after hours → exercises the override path
    dlg.get_by_label("Reason for visit").fill("Cough x 5 days")
    dlg.get_by_role("button", name="Book appointment").click()
    try:
        dlg.get_by_role("button", name="Book anyway (override hours)").click(timeout=3000)
    except Exception: pass
    pg.wait_for_timeout(1500)
    if dlg.is_visible():
        print("DIALOG ALERT:", dlg.get_by_role("alert").all_inner_texts()); pg.screenshot(path=f"{OUT}/e2e-fail.png"); sys.exit(1)
    print("booked")
    # Front desk: find card, check in, room
    pg.goto("http://localhost:5173/front-desk"); pg.get_by_label("Filter queue").fill("Patient"+suffix)
    card=pg.locator("li", has_text="Patient"+suffix).first
    card.get_by_role("button", name="Check in").click(); pg.wait_for_timeout(800)
    card=pg.locator("li", has_text="Patient"+suffix).first
    card.get_by_role("button", name="Room").click(); pg.get_by_role("button", name="Assign").click(); pg.wait_for_timeout(800)
    pg.screenshot(path=f"{OUT}/e2e-01-frontdesk.png")
    card=pg.locator("li", has_text="Patient"+suffix).first
    card.get_by_role("button", name="Start visit").click()
    pg.wait_for_url("**/encounters/*"); pg.wait_for_selector("text=Visit in progress")
    print("encounter", pg.url)
    # Vitals
    pg.get_by_role("button", name="Record").click()
    d=pg.get_by_role("dialog"); d.get_by_label("Systolic").fill("128"); d.get_by_label("Diastolic").fill("82"); d.get_by_label("Heart rate").fill("76"); d.get_by_label("Temperature").fill("99.1")
    d.get_by_role("button", name="Save vitals").click(); expect(d).to_be_hidden()
    # Note
    pg.get_by_role("button", name="Start note").click(); pg.wait_for_selector("#sec-assessment")
    pg.get_by_role("button", name="Insert vitals").click()
    pg.fill("#sec-subjective", "Cough for 5 days, non-productive. No fever.")
    pg.fill("#sec-assessment", "Acute bronchitis, likely viral.")
    pg.fill("#sec-plan", "Supportive care, fluids, return if dyspnea.")
    pg.keyboard.press("Meta+s"); pg.wait_for_selector("text=Draft saved")
    # Diagnosis
    pg.get_by_placeholder("Add diagnosis (ICD-10)…").fill("bronch"); pg.get_by_role("option").first.click(); pg.wait_for_timeout(800)
    pg.screenshot(path=f"{OUT}/e2e-02-draft.png")
    # Sign
    pg.get_by_role("button", name="Sign", exact=True).click()
    pg.get_by_role("dialog").get_by_role("button", name="Sign note").click(); pg.wait_for_selector("text=Signed by")
    # Complete
    pg.get_by_role("button", name="Complete visit").click(); pg.wait_for_selector("text=Visit completed")
    pg.screenshot(path=f"{OUT}/e2e-03-completed.png")
    # Check out
    pg.goto("http://localhost:5173/front-desk"); pg.get_by_label("Filter queue").fill("Patient"+suffix)
    pg.locator("li", has_text="Patient"+suffix).first.get_by_role("button", name="Check out").click(); pg.wait_for_timeout(800)
    expect(pg.locator("li", has_text="Patient"+suffix).first).to_contain_text("Checked out")
    print("checked out")
    b.close()
print("page errors:", errors)
