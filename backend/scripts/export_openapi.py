"""Write the OpenAPI schema to frontend/openapi.json (input for `npm run gen:api`)."""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "development")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

out = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n")
print(f"wrote {out}")
