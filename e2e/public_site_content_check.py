"""Public website accuracy guard (no database, no server): the monitors and AI assistants named on the public site match
the code. Parses source text only, so it never imports the backend.

  - frontend/src/features/public/content.ts MONITOR_GROUPS == every Monitor key registered under backend/app/monitors
  - "AI may assist" flags == backend/app/agents/case_assist.py RULES keys
  - ASSISTANTS == backend/app/agents/runner.py DEFAULTS, and "Launched by staff" == trigger "manual"

Run directly (python e2e/public_site_content_check.py) or via e2e/public_site_flow.py."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check() -> None:
    content = (ROOT / "frontend/src/features/public/content.ts").read_text()
    monitors_src = content[content.index("export const MONITOR_GROUPS"):content.index("export const MONITOR_COUNT")]
    assistants_src = content[content.index("export const ASSISTANTS"):content.index("// ---", content.index("export const ASSISTANTS"))]

    site_monitors = dict(re.findall(r'\{ key: "([a-z_.]+)", name: "[^"]+",.*?owner: "[^"]+"(, aiAssist: true)?', monitors_src))
    code_monitors = set()
    for f in (ROOT / "backend/app/monitors").glob("*.py"):
        code_monitors |= set(re.findall(r'^\s+key = "([a-z_.]+)"', f.read_text(), re.M))
    assert len(code_monitors) == 22, f"expected 22 registered monitors, code has {len(code_monitors)} — update the website copy"
    assert set(site_monitors) == code_monitors, f"monitor mismatch: site-only {set(site_monitors) - code_monitors}, code-only {code_monitors - set(site_monitors)}"

    rules_src = (ROOT / "backend/app/agents/case_assist.py").read_text()
    rules_src = rules_src[rules_src.index("RULES:"):]
    # A rule block runs from its key to the next key; rules marked "default": False are available but OFF by default,
    # so the website flags exactly the monitors where AI assistance is on out of the box.
    blocks = re.split(r'^    "(?=[a-z_.]+": \{"agent")', rules_src, flags=re.M)[1:]
    rules = {b.split('"', 1)[0] for b in blocks if '"default": False' not in b.split("\n    \"", 1)[0]}
    assert len(rules) == 6, f"expected 6 monitors with AI assistance on by default, found {sorted(rules)}"
    flagged = {k for k, v in site_monitors.items() if v}
    assert flagged == rules, f"'AI may assist' flags {sorted(flagged)} != default-on case_assist RULES {sorted(rules)}"

    runner = (ROOT / "backend/app/agents/runner.py").read_text()
    defaults = re.findall(r'^    \("([a-z_]+)", "([^"]+)",.*?, "(manual|feature)"\),$', runner, re.M | re.S)  # tuples may span lines
    site_assistants = re.findall(r'\{ (?:brand: "[^"]+", )?key: "([a-z_]+)", name: "([^"]+)",.*?start: "(Launched by staff|Runs inside a workflow)"', assistants_src, re.S)
    assert len(defaults) == 10, f"expected 10 default agents, code has {len(defaults)}"
    code = {k: (n, "Launched by staff" if t == "manual" else "Runs inside a workflow") for k, n, t in defaults}
    site = {k: (n, s) for k, n, s in site_assistants}
    assert site == code, f"assistant mismatch:\n site {site}\n code {code}"


if __name__ == "__main__":
    check()
    print("public_site_content_check: OK")
