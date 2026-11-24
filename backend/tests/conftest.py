import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://undeclared:undeclared@localhost:5432/undeclared_test")
os.environ["CELERY_EAGER"] = "true"
os.environ["ENVIRONMENT"] = "test"
os.environ["ENGINE_INPROCESS_SCHEDULER"] = "false"  # tests drive the engine explicitly
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
            return getattr(self.c, method)(f"/api/v1{path}", headers={**self.headers, **kw.pop("headers", {})}, **kw)
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


# ---------------------------------------------------------------------------------------------- private demo hospitals

@pytest.fixture
def demo(monkeypatch):
    """DEMO_MODE with private demo hospitals; every hospital created by the test is removed afterwards."""
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.db import SessionLocal
    from app.demo import sandbox
    from app.models import DemoSandbox

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_sandbox_enabled", True)
    monkeypatch.setattr(settings, "demo_sandbox_pool_size", 0)  # tests build on demand; no background pool
    monkeypatch.setattr(settings, "demo_sandbox_per_visitor", 5)
    sandbox.invalidate_cache()
    yield
    db = SessionLocal()
    for sb in db.scalars(select(DemoSandbox).where(DemoSandbox.status.in_(("leased", "ready", "building", "failed")))):
        sandbox.release(db, sb, "test")
    db.commit()
    ids = list(db.scalars(select(DemoSandbox.id).where(DemoSandbox.status.in_(("releasing", "purging", "failed")))))
    db.close()
    for i in ids:
        sandbox.purge(i)
    sandbox.invalidate_cache()


class Visitor:
    """A demo visitor's browser: its own cookie jar and client address; switches roles inside one demo hospital."""

    def __init__(self, app, ip: str):
        self.c = TestClient(app, client=(ip, 50000))
        self.h: dict = {}
        self.me: dict = {}

    def enter(self, key: str):
        r = self.c.post("/api/v1/auth/demo-login", json={"key": key})
        assert r.status_code == 200, r.text
        self._accept(r.json())
        return self

    def _accept(self, data):
        self.me = data["me"]
        self.h = {"Authorization": f"Bearer {data['access_token']}", "X-Organization-Id": self.me["memberships"][0]["organization_id"]}

    @property
    def org(self) -> str:
        return self.h["X-Organization-Id"]

    @property
    def membership(self) -> dict:
        return self.me["memberships"][0]

    def switch(self, **body):
        r = self.c.post("/api/v1/auth/demo/switch", headers=self.h, json=body)
        assert r.status_code == 200, r.text
        old = dict(self.h)
        self._accept(r.json())
        return old

    def as_person(self, name: str):
        """Switch to a specific staff member of this hospital (e.g. a second lab technologist)."""
        people = self.get("/auth/demo/session").json()["people"]
        return self.switch(user_id=next(p["user_id"] for p in people if p["name"] == name))

    def _call(self, method, path, **kw):
        return getattr(self.c, method)(f"/api/v1{path}", headers={**self.h, **kw.pop("headers", {})}, **kw)

    def get(self, path, **kw):
        return self._call("get", path, **kw)

    def post(self, path, **kw):
        return self._call("post", path, **kw)

    def patch(self, path, **kw):
        return self._call("patch", path, **kw)

    def put(self, path, **kw):
        return self._call("put", path, **kw)

    def delete(self, path, **kw):
        return self._call("delete", path, **kw)
