import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://undeclared:undeclared@localhost:5432/undeclared_test")
os.environ["CELERY_EAGER"] = "true"
os.environ["ENVIRONMENT"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "false"  # covered explicitly in test_hardening.py
os.environ["STORAGE_LOCAL_PATH"] = "./var/test-storage"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from alembic import command  # noqa: E402
from app.seed import DEV_PASSWORD  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    from app.seed import seed

    seed(reset=True)
    yield


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app

    return fastapi_app


class Api:
    """Thin client that logs in as a user and sends the org header."""

    def __init__(self, app, email: str, org_slug: str | None = "harborview"):
        self.c = TestClient(app)
        r = self.c.post("/api/auth/login", json={"email": email, "password": DEV_PASSWORD})
        assert r.status_code == 200, r.text
        data = r.json()
        self.me = data["me"]
        self.headers = {"Authorization": f"Bearer {data['access_token']}"}
        if org_slug:
            orgs = {m["organization_name"]: m for m in self.me["memberships"]}
            m = next(v for k, v in orgs.items() if k.lower().startswith(org_slug[:5]))
            self.membership = m
            self.headers["X-Organization-Id"] = m["organization_id"]

    def __getattr__(self, method):
        def call(path, **kw):
            return getattr(self.c, method)(f"/api{path}", headers={**self.headers, **kw.pop("headers", {})}, **kw)
        return call


@pytest.fixture(scope="session")
def as_user(app):
    cache: dict = {}

    def get(email: str, org: str | None = "harborview") -> Api:
        key = (email, org)
        if key not in cache:
            cache[key] = Api(app, email, org)
        return cache[key]

    return get
