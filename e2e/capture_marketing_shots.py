"""Capture product screenshots for the public website (repeatable; synthetic data only).

Signs in with a real account (CAPTURE_EMAIL; the password is asked without echo), switches workspaces from the header role
switcher, and writes WebP images to frontend/public/images/product/<name>.webp (1440 px) and <name>-720.webp (720 px).
The patient-portal shot needs a patient's own account (CAPTURE_PATIENT_EMAIL); it is skipped otherwise.

    CAPTURE_EMAIL=admin@undeclared.dev BASE=https://3-19-143-26.sslip.io e2e/.venv/bin/python e2e/capture_marketing_shots.py

Privacy: synthetic-data deployments only; AI settings, the outbox and the audit log are never captured, and the script
aborts if a page shows anything that looks like an API key or an email address.
"""
import base64
import getpass
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "https://3-19-143-26.sslip.io").rstrip("/")
OUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "images" / "product"
OUT.mkdir(parents=True, exist_ok=True)

# (file name, workspace role — "patient" means the patient's own account, path, viewport height, optional patient search)
SHOTS = [
    ("command-center", "super_admin", "/command", 1000, None),
    ("doctor-home", "doctor", "/", 900, None),
    ("patient-chart", "doctor", "/patients?q=Whitlock", 900, "Whitlock"),
    ("my-work", "nurse", "/worklist", 860, None),
    ("ed-board", "nurse", "/ed", 900, None),
    ("insurance-guardian", "receptionist", "/insurance", 900, None),
    ("agent-studio", "super_admin", "/agents", 900, None),
    ("patient-portal", "patient", "/portal", 900, None),
]
ACCOUNTS = {"staff": os.environ.get("CAPTURE_EMAIL"), "patient": os.environ.get("CAPTURE_PATIENT_EMAIL")}
SECRET = re.compile(r"sk-[A-Za-z0-9_-]{12,}|[\w.+-]+@[\w-]+\.(?:dev|com|org|net)")

PASSWORDS: dict[str, str] = {}

ENCODE = """async ([b64, width]) => {
  const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
  const h = Math.round(img.height * width / img.width);
  const c = document.createElement('canvas'); c.width = width; c.height = h;
  const g = c.getContext('2d'); g.imageSmoothingQuality = 'high'; g.drawImage(img, 0, 0, width, h);
  return c.toDataURL('image/webp', 0.86).split(',')[1];
}"""


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("E2E_BROWSER_CHANNEL", "chrome") or None, headless=True)
        sessions: dict[tuple[str, int], object] = {}
        for name, role, path, height, patient in SHOTS:
            key = (role, height)
            if key not in sessions:
                ctx = b.new_context(viewport={"width": 1440, "height": height}, color_scheme="light")
                ctx.add_init_script("try{localStorage.setItem('ud-theme','light');localStorage.removeItem('ud-density')}catch(e){}")
                pg = ctx.new_page()
                pg.on("pageerror", lambda e, n=name: errors.append(f"{n}: {e}"))
                who = "patient" if role == "patient" else "staff"
                if not ACCOUNTS[who]:
                    print(f"skip {name}: no {who} account given")
                    continue
                pg.goto(f"{BASE}/login")
                pg.fill("input[type=email]", ACCOUNTS[who])
                pg.fill("input[type=password]", PASSWORDS.setdefault(who, getpass.getpass(f"Password for {ACCOUNTS[who]}: ")))
                pg.click("button[type=submit]")
                pg.wait_for_url(lambda u: "/login" not in u, timeout=20000)
                sessions[key] = pg
            pg = sessions.get(key)
            if pg is None:
                continue
            if role != "patient" and pg.get_by_test_id("workspace-switcher").count():
                pg.get_by_test_id("workspace-switcher").click()
                pg.get_by_test_id(f"workspace-{role}").click()
                pg.wait_for_timeout(800)
            pg.goto(BASE + path)  # the app keeps a live-update stream open, so wait for content, not network idle
            pg.locator("main h1").first.wait_for(timeout=20000)
            if patient:
                pg.locator("tbody tr", has_text=patient).first.click()
                pg.wait_for_url("**/patients/*")
                pg.get_by_test_id("patient-banner").wait_for(timeout=20000)
            pg.wait_for_timeout(2500)
            text = pg.inner_text("body")
            if SECRET.search(text):
                print(f"ABORT {name}: page text looks like it contains a key or an email address"); return 1
            png = pg.screenshot(type="png")
            b64 = base64.b64encode(png).decode()
            for width, suffix in ((1440, ""), (720, "-720")):
                webp = base64.b64decode(pg.evaluate(ENCODE, [b64, width]))
                (OUT / f"{name}{suffix}.webp").write_bytes(webp)
            print(f"captured {name} ({role} {path})")
        b.close()
    if errors:
        print("PAGE ERRORS:", *errors, sep="\n"); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
