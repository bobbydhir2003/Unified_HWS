# End-to-end checks

Run against a running dev stack (API on :8010 behind Vite on :5173, seeded data). Uses the locally installed Chrome.

```bash
uv venv e2e/.venv && VIRTUAL_ENV=e2e/.venv uv pip install playwright httpx
e2e/.venv/bin/python e2e/api_smoke.py                 # every screen's API calls × every role, flags 4xx/5xx
mkdir -p /tmp/ud-shots && e2e/.venv/bin/python e2e/clinical_flow.py /tmp/ud-shots   # register → … → signed note → check-out
```
