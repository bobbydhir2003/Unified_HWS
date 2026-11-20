"""Post-deployment smoke test against a deployed URL, synthetic data only. Read-only except one rule-based agent run.
Usage:  BASE=https://3-19-143-26.sslip.io DEMO_PASSWORD=… python e2e/deploy_smoke.py
The password is read from the environment and never printed."""
import os
import sys
import time

import httpx

BASE = os.environ.get("BASE", "https://3-19-143-26.sslip.io").rstrip("/")
PW = os.environ["DEMO_PASSWORD"]
API = f"{BASE}/api/v1"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{f' — {detail}' if detail else ''}")


def login(email: str) -> httpx.Client:
    c = httpx.Client(base_url=API, timeout=30)
    r = c.post("/auth/login", json={"email": email, "password": PW})
    r.raise_for_status()
    c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return c


r = httpx.get(f"{BASE}/api/health/ready", timeout=30)
deps = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
check("readiness (db, redis, storage)", r.status_code == 200, str({k: v.get("ok") if isinstance(v, dict) else v for k, v in deps.get("checks", deps).items()}) if deps else str(r.status_code))
check("SPA route served", httpx.get(f"{BASE}/command", timeout=30).status_code == 200)

# Auth: login, cookie flags, refresh, logout.
c = httpx.Client(base_url=API, timeout=30)
r = c.post("/auth/login", json={"email": "admin@undeclared.dev", "password": PW})
check("super admin login", r.status_code == 200, f"status {r.status_code}")
cookie = r.headers.get("set-cookie", "")
check("refresh cookie Secure + HttpOnly", "secure" in cookie.lower() and "httponly" in cookie.lower())
c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
check("token refresh via cookie", c.post("/auth/refresh").status_code == 200)
check("logout", c.post("/auth/logout").status_code == 200)
check("wrong password refused", httpx.post(f"{API}/auth/login", json={"email": "admin@undeclared.dev", "password": "wrong-password"}, timeout=30).status_code == 401)

sa, ha, doc, front, pt, rx = (login(e) for e in ("admin@undeclared.dev", "hospitaladmin@harborview.dev", "dr.chen@harborview.dev",
                                                  "frontdesk@harborview.dev", "patient@harborview.dev", "pharmacist@harborview.dev"))
# Roles.
check("doctor blocked from Command Center", doc.get("/command/summary").status_code == 403)
check("patient blocked from staff patient list", pt.get("/patients").status_code == 403)
check("doctor blocked from AI settings", doc.get("/admin/ai-settings").status_code == 403)
# Patients & hospital.
pts = front.get("/patients").json()
pts = pts["items"] if isinstance(pts, dict) else pts
check("patient search", len(pts) > 0, f"{len(pts)} patients")
board = ha.get("/adt/board")
check("bed board", board.status_code == 200, f"{board.json()['totals']['occupied']} occupied / {board.json()['totals']['available']} free")
check("ED board", ha.get("/ed/board").status_code == 200)
cs = ha.get("/command/summary").json()
tiles = {t["key"]: t["value"] for t in cs["hospital"]["tiles"]}
check("Command Center tiles", cs["hospital"]["available"] and tiles["beds"] == board.json()["totals"]["available"], f"inpatients {tiles['inpatients']}, ED {tiles['ed']}")
check("pharmacy inventory", rx.get("/inventory/items").status_code == 200)
g = front.get("/insurance/guardian/summary")
check("Insurance Guardian summary", g.status_code == 200)
check("Insurance cases", front.get("/cases", params={"category": "insurance"}).status_code == 200)
check("portal home (patient)", pt.get("/portal/home").status_code == 200 if pt.get("/portal/home").status_code != 404 else pt.get("/portal/appointments").status_code == 200)
# Automation engine (worker + beat): events are being dispatched, monitors have run.
eh = ha.get("/engine/health").json()
check("automation engine", eh["status"] in ("healthy", "degraded") and eh["oldest_pending_seconds"] < 120, f"status {eh['status']}, pending {eh['pending_events']}, last monitor run {eh['last_monitor_run']}")
# AI configuration.
s = sa.get("/admin/ai-settings")
body = s.json()
key = body.get("key") or {}
check("AI settings (super admin)", s.status_code == 200 and set(key) <= {"configured", "hint", "source", "updated_at"} and "encryption" in body,
      f"provider {body.get('provider')}, key configured {key.get('configured')}, encryption {body.get('encryption')}")
st = sa.get("/ai/provider").json()
check("AI provider status reported", "active" in st, f"active={st.get('active')}, live={st.get('live')}, live_validation={st.get('live_validation')}")
rt = front.get("/ai/realtime/status").json()
check("Realtime Voice status", rt["mode"] in ("openai", "simulated"), f"mode={rt['mode']}")
rs = front.post("/ai/realtime/session", json={})
check("Realtime session endpoint", rs.status_code == 200 and (rs.json()["mode"] == "simulated" or rs.json().get("value")), f"mode={rs.json().get('mode')}")
run = ha.post("/agents/hospital_operations/run", json={"input": "Shift summary for the bed meeting"})
check("Hospital Operations agent", run.status_code == 200 and run.json()["status"] == "succeeded", f"mode={run.json().get('mode')}, tools={[t['tool'] for t in run.json().get('tool_calls', [])]}")
# Live updates (SSE) through Caddy + nginx: first frame must arrive promptly (no proxy buffering).
t0 = time.monotonic()
with httpx.stream("GET", f"{API}/stream", headers={"Authorization": ha.headers["Authorization"]}, timeout=15) as sresp:
    first = next(sresp.iter_text(), "")
check("Server-Sent Events stream", sresp.status_code == 200 and "retry" in first and time.monotonic() - t0 < 5, f"first frame in {time.monotonic() - t0:.1f}s")
# Security headers on the API through the edge.
h = httpx.get(f"{BASE}/api/health", timeout=30).headers
check("security headers", "strict-transport-security" in h and "content-security-policy" in h)

failed = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
