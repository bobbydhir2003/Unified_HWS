"""UI E2E: AI scribe — mic recording fails honestly without STT; synthetic demo → draft → insert → attested sign → complete."""
import sys
from playwright.sync_api import sync_playwright, expect
OUT = sys.argv[1]; errors = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True,
                          args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
    ctx = b.new_context(viewport={"width": 1440, "height": 1000}, permissions=["microphone"])
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://localhost:5173/login")
    pg.fill("input[type=email]", "dr.chen@harborview.dev"); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
    pg.wait_for_url("http://localhost:5173/")
    # unscheduled visit for a fresh patient
    pg.goto("http://localhost:5173/patients/new")
    pg.get_by_label("First name").fill("Scribe"); pg.get_by_label("Last name").fill("Uiflow")
    pg.get_by_label("Date of birth").fill("1988-03-03"); pg.get_by_label("Sex assigned at birth").select_option("female")
    pg.get_by_role("button", name="Register patient").click()
    try: pg.get_by_role("button", name="Not a duplicate — create new record").click(timeout=2500)
    except Exception: pass
    pg.wait_for_selector("text=MRN")
    pg.get_by_role("button", name="Start visit").click(); pg.wait_for_url("**/encounters/*")
    pg.get_by_label("Chief complaint").fill("Cough for 5 days"); pg.get_by_label("Follow-up").click()
    pg.get_by_role("button", name="AI scribe").click()
    expect(pg.get_by_role("button", name="Start scribe session")).to_be_disabled()
    pg.get_by_text("was informed and agreed").click()
    pg.get_by_role("button", name="Start scribe session").click()
    # Real microphone path (fake device): record ~3s, stop → must fail honestly, not invent text
    pg.get_by_role("button", name="Start recording").click(); pg.wait_for_timeout(3200)
    pg.get_by_role("button", name="Pause").click(); pg.get_by_role("button", name="Resume").click()
    pg.get_by_role("button", name="Stop").click()
    expect(pg.get_by_role("alert").filter(has_text="speech-to-text")).to_be_visible(timeout=10000)
    print("recording → honest STT failure shown")
    pg.get_by_role("tab", name="Synthetic demo").click()
    pg.get_by_role("button", name="Use synthetic conversation").click()
    pg.wait_for_selector("text=Draft note", timeout=15000)
    expect(pg.get_by_text("Allergy discrepancy")).to_be_visible()
    pg.screenshot(path=f"{OUT}/scribe-01-draft.png", full_page=True)
    pg.get_by_role("button", name="Insert into note").click()
    pg.wait_for_selector("text=Contains AI-generated text", timeout=10000)
    expect(pg.locator("#sec-assessment")).to_contain_text("bronchitis")
    pg.get_by_placeholder("Add diagnosis (ICD-10)…").fill("bronch"); pg.get_by_role("option").first.click(); pg.wait_for_timeout(800)
    pg.get_by_role("button", name="Sign", exact=True).click()
    dlg = pg.get_by_role("dialog")
    expect(dlg.get_by_role("button", name="Sign note")).to_be_disabled()   # AI attestation required
    dlg.get_by_text("I have reviewed and").click()
    dlg.get_by_role("button", name="Sign note").click()
    pg.wait_for_selector("text=AI-assisted · clinician reviewed")
    pg.get_by_role("button", name="Complete visit").click(); pg.wait_for_selector("text=Visit completed")
    pg.screenshot(path=f"{OUT}/scribe-02-signed.png", full_page=True)
    print("demo → draft → insert → attested sign → completed")
    b.close()
print("page errors:", errors)
