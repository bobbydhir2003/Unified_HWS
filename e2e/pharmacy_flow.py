"""Pharmacy expiry flow (synthetic, repeatable): near-expiry lot → Watchdog case → pharmacist requests waste →
second pharmacist approves in My work → monitor re-check → case resolved automatically."""
import os
import re
import sys
import uuid
from datetime import date, timedelta

import httpx
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("WEB", "http://localhost:5173")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SHOTS", "shots")
os.makedirs(SHOTS, exist_ok=True)
errors: list[str] = []
LOT = f"E2E-{uuid.uuid4().hex[:6].upper()}"


def client(email):
    c = httpx.Client(base_url=f"{BASE}/api/v1")
    t = c.post("/auth/login", json={"email": email, "password": "Undeclared!2026"}).json()
    c.headers.update({"Authorization": "Bearer " + t["access_token"], "X-Organization-Id": t["me"]["memberships"][0]["organization_id"]})
    return c


rx_api, admin_api = client("pharmacist@harborview.dev"), client("hospitaladmin@harborview.dev")
item = next(i for i in rx_api.get("/inventory/items").json() if i["name"] == "Ondansetron")
loc = next(x for x in rx_api.get("/inventory/locations").json() if x["code"] == "RX-ED")
rx_api.post("/inventory/receive", json={"item_id": item["id"], "location_id": loc["id"], "lot_number": LOT,
                                        "expiry_date": (date.today() + timedelta(days=3)).isoformat(), "quantity": 8}).raise_for_status()
admin_api.post("/monitors/pharmacy.expiring/run").raise_for_status()

with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)

    def login(email):
        pg = b.new_page(viewport={"width": 1440, "height": 950})
        pg.on("pageerror", lambda e: errors.append(f"{email}: {e}"))
        pg.goto(f"{BASE}/login")
        pg.fill("input[type=email]", email); pg.fill("input[type=password]", "Undeclared!2026"); pg.click("button[type=submit]")
        pg.wait_for_url(lambda u: "/login" not in u)
        return pg

    rx = login("pharmacist@harborview.dev")
    rx.goto(f"{BASE}/pharmacy?tab=watchdog")
    expect(rx.get_by_role("button", name=re.compile(f"lot {LOT} expires in 3 d"))).to_be_visible(timeout=10000)
    rx.screenshot(path=f"{SHOTS}/rx-01-watchdog.png")
    rx.goto(f"{BASE}/pharmacy?item={item['id']}")
    row = rx.get_by_role("row", name=re.compile(LOT))
    row.get_by_role("button", name="Waste").click()
    dlg = rx.get_by_role("dialog").last
    dlg.get_by_label("Quantity").fill("8")
    dlg.get_by_label("Reason").fill("Expires in 3 days; low use in ED")
    dlg.get_by_role("button", name="Confirm").click()
    expect(rx.get_by_text("Sent for a second person's approval")).to_be_visible(timeout=10000)

    rx2 = login("pharmacist2@harborview.dev")
    rx2.goto(f"{BASE}/worklist")
    tab = rx2.get_by_role("tab", name=re.compile("Approvals"))  # narrow screens: tabs; desktop: three panels side by side
    if tab.count():
        tab.click()
    li = rx2.locator("li", has_text=LOT)
    li.get_by_role("button", name="Approve").click()
    expect(rx2.get_by_text("Approved and executed")).to_be_visible(timeout=10000)

    admin_api.post("/monitors/pharmacy.expiring/run").raise_for_status()
    rx.goto(f"{BASE}/pharmacy?tab=watchdog")
    expect(rx.get_by_role("button", name=re.compile(f"lot {LOT}"))).to_have_count(0, timeout=10000)
    b.close()

case = next(c for c in rx_api.get("/cases", params={"status": "closed", "category": "pharmacy"}).json() if LOT in c["title"])
assert case["resolution_code"] == "verified_active", case
if errors:
    print("PAGE ERRORS:", *errors, sep="\n")
    sys.exit(1)
print("pharmacy_flow: OK")
