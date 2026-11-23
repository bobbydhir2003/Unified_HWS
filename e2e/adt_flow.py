"""Hospital flow (synthetic data; re-runnable — creates a pending admission if none): pending admission → bed placement → transfer → discharge order →
checklist → discharge (audited override) → bed goes to cleaning."""
import os
import re
import sys

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []


def ensure_pending_admission() -> None:
    """Re-runnable on a long-lived dev database: if no patient awaits a bed, create one the real way
    (ED arrival → triage → physician admits) through the API. Additive synthetic data only."""
    import uuid

    import httpx

    def client(email):
        c = httpx.Client(base_url=f"{BASE}/api/v1", timeout=30)
        c.headers["Authorization"] = "Bearer " + c.post("/auth/login", json={"email": email, "password": "Undeclared!2026"}).json()["access_token"]
        return c

    bedm = client("bedmanager@harborview.dev")
    board = bedm.get("/adt/board").json()
    # The flow needs a few free inpatient beds: housekeeping finishes beds that are waiting for cleaning.
    free = [b for u in board["units"] if u.get("inpatient", True) for b in u["beds"] if b["status"] == "available"]
    cleaning = [b for u in board["units"] if u.get("inpatient", True) for b in u["beds"] if b["status"] == "cleaning"]
    for b in cleaning[: max(0, 4 - len(free))]:
        bedm.post(f"/beds/{b['id']}/status", json={"to": "available", "reason": "Cleaning complete"}).raise_for_status()
    if board["pending_admissions"]:
        return
    front, nurse, doc = client("frontdesk@harborview.dev"), client("nurse.kim@harborview.dev"), client("dr.santos@harborview.dev")
    pt = front.post("/patients", json={"first_name": "Avery", "last_name": f"Board{uuid.uuid4().hex[:5]}", "date_of_birth": "1972-02-02",
                                       "sex_at_birth": "female", "confirm_not_duplicate": True}).json()
    v = nurse.post("/ed/arrivals", json={"patient_id": pt["id"], "chief_complaint": "Cellulitis, needs IV antibiotics"}).json()
    nurse.post(f"/ed/visits/{v['id']}/triage", json={"esi_level": 3})
    r = doc.post(f"/ed/visits/{v['id']}/disposition", json={"disposition": "admit", "admit_reason": "Cellulitis", "level_of_care": "med_surg"})
    r.raise_for_status()


ensure_pending_admission()

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def login(email):
        pg = b.new_page(viewport={"width": 1440, "height": 950})
        pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto(f"{BASE}/login")
        pg.fill("input[type=email]", email); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
        pg.wait_for_url(lambda u: "/login" not in u)
        return pg

    bm = login("bedmanager@harborview.dev")
    bm.goto(f"{BASE}/beds")
    waiting = bm.locator("li", has=bm.get_by_role("button", name="Assign bed")).first
    expect(waiting).to_be_visible(timeout=15000)
    name = waiting.locator("p.font-medium").inner_text()
    bm.screenshot(path=f"{SHOTS}/adt-01-board.png")
    waiting.get_by_role("button", name="Assign bed").click()
    dlg = bm.get_by_role("dialog")
    dlg.locator("select").select_option(index=1)
    dlg.get_by_role("button", name="Assign & admit").click()
    expect(bm.get_by_text("Patient placed")).to_be_visible(timeout=10000)
    # Transfer from the board.
    tile = bm.get_by_role("button", name=re.compile(rf"Occupied, {re.escape(name)}"))
    expect(tile).to_be_visible(timeout=10000)
    tile.click()
    dlg = bm.get_by_role("dialog")
    dlg.locator("select").select_option(index=3)
    dlg.get_by_role("button", name="Transfer").click()
    expect(bm.get_by_text("Patient transferred")).to_be_visible(timeout=10000)

    doc = login("dr.santos@harborview.dev")
    doc.goto(f"{BASE}/inpatients")
    doc.get_by_role("row", name=re.compile(re.escape(name))).click()
    doc.get_by_role("button", name="Order discharge").click()
    doc.get_by_role("dialog").get_by_role("button", name="Order discharge").click()
    expect(doc.get_by_text("Discharge ordered — checklist created")).to_be_visible(timeout=10000)
    doc.get_by_role("tab", name=re.compile("Discharge")).click()
    expect(doc.get_by_text("Medication reconciliation completed").first).to_be_visible(timeout=10000)
    doc.screenshot(path=f"{SHOTS}/adt-02-checklist.png")
    stay_url = doc.url

    nurse = login("nurse.kim@harborview.dev")
    nurse.goto(f"{BASE}/nursing")
    expect(nurse.get_by_text(name)).to_be_visible(timeout=10000)
    nurse.screenshot(path=f"{SHOTS}/adt-03-nursing.png")
    nurse.goto(stay_url)
    expect(nurse.get_by_role("button", name="Complete discharge")).to_be_disabled()  # checklist open; nurses can't override
    doc.goto(stay_url)
    doc.get_by_role("button", name="Complete discharge").click()
    dlg = doc.get_by_role("dialog")
    expect(dlg.get_by_text("Discharge with open items")).to_be_visible()
    dlg.locator("textarea").fill("Family transporting patient to outside facility tonight")
    dlg.get_by_role("button", name="Discharge").click()
    expect(doc.get_by_text("Patient discharged")).to_be_visible(timeout=10000)
    b.close()

if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("adt_flow: OK")
