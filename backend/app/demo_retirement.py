"""One-time retirement of the former Demo Mode (private demo hospitals + one-click shared demo accounts).

Run once on a server that had Demo Mode:  python -m app.cli retire-demo   (asks for typed confirmation)

What it removes or ends — only things that are exclusively demo-owned:
  * every private demo hospital registered in `demo_sandboxes` (organization slug `demo-<tag>`, flagged synthetic):
    all of its rows (one cascading delete — migration 0031's triggers allow it only for a registered hospital in status
    'purging'), its sign-in-less identities, their sessions, and its stored files;
  * every session that belonged to a demo-hospital lease;
  * sessions of the seven shared one-click demo accounts (they are signed out, not changed or deleted);
  * the demo-only Super Admin account behind the old "Super Admin" demo button is DEACTIVATED (not deleted, reversible).
Real organizations (Harborview included), real accounts, AI settings and audit history are never touched. The schema
added for demo hospitals is kept (migration history is preserved; the tables simply stay empty).
"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select, text, update

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.core.security import now
from app.models import DemoSandbox, Document, Organization, ScribeSession, User, UserSession
from app.services import audit

log = logging.getLogger("undeclared.demo_retirement")

# The former one-click demo accounts (all in the synthetic Harborview organization).
LEGACY_DEMO_EMAILS = ("dr.chen@harborview.dev", "nurse.kim@harborview.dev", "frontdesk@harborview.dev", "clinicadmin@harborview.dev",
                      "billing@harborview.dev", "patient@harborview.dev", "superadmin.demo@harborview.dev")
DEMO_ONLY_ACCOUNT = "superadmin.demo@harborview.dev"  # existed only for the demo "Super Admin" button


def _purge(sb_id: uuid.UUID) -> bool:
    db = SessionLocal()
    try:
        sb = db.get(DemoSandbox, sb_id)
        if not sb or sb.status == "purged":
            return False
        org_id = sb.organization_id
        keys: list[str] = []
        if org_id:
            org = db.get(Organization, org_id)
            if org and not (org.slug == f"demo-{sb.tag}" and (org.settings or {}).get("synthetic_data")):
                log.error("refusing to remove an organization that does not look like a demo hospital", extra={"tag": sb.tag})
                return False
            keys = [k for k in db.scalars(select(Document.storage_key).where(Document.organization_id == org_id)) if k]
            keys += [k for k in db.scalars(select(ScribeSession.audio_storage_key).where(ScribeSession.organization_id == org_id)) if k]
    finally:
        db.close()
    with engine.begin() as c:
        c.execute(update(DemoSandbox).where(DemoSandbox.id == sb_id).values(status="purging"))
        if org_id:
            c.exec_driver_sql("SELECT set_config('app.sandbox_purge', %s, true)", (str(org_id),))
            c.execute(text("DELETE FROM audit_events WHERE organization_id = :o OR actor_user_id IN "
                           "(SELECT id FROM users WHERE sandbox_org_id = :o)"), {"o": org_id})
            c.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
            c.execute(text("DELETE FROM users WHERE sandbox_org_id = :o"), {"o": org_id})
            c.exec_driver_sql("SELECT set_config('app.sandbox_purge', '', true)")
            c.execute(text("DELETE FROM ai_usage_counters WHERE key LIKE :k"), {"k": f"%{org_id}%"})
        c.execute(update(DemoSandbox).where(DemoSandbox.id == sb_id).values(status="purged", purged_at=now(), release_reason="retired"))
    from app.services.storage import storage

    for k in keys:
        try:
            storage.delete(k)
        except Exception:  # noqa: BLE001 — a missing file must not stop the retirement
            log.warning("file delete failed", exc_info=True)
    if org_id and settings.storage_backend == "local":
        root = Path(settings.storage_local_path).resolve()
        d = root / str(org_id)
        if d.is_dir() and d.parent == root:
            shutil.rmtree(d, ignore_errors=True)
    return True


def retire() -> dict:
    out = {"hospitals_removed": 0, "sessions_ended": 0, "accounts_deactivated": 0}
    db = SessionLocal()
    try:
        ids = list(db.scalars(select(DemoSandbox.id).where(DemoSandbox.status != "purged")))
    finally:
        db.close()
    for i in ids:
        out["hospitals_removed"] += int(_purge(i))
    db = SessionLocal()
    try:
        t = now()
        legacy = list(db.scalars(select(User.id).where(User.email.in_(LEGACY_DEMO_EMAILS))))
        out["sessions_ended"] = db.execute(update(UserSession).where(
            UserSession.revoked_at.is_(None),
            (UserSession.sandbox_lease_id.is_not(None)) | (UserSession.user_id.in_(legacy))).values(revoked_at=t)).rowcount or 0
        acct = db.scalar(select(User).where(User.email == DEMO_ONLY_ACCOUNT))
        if acct and acct.is_active and not acct.is_superadmin:
            acct.is_active = False
            out["accounts_deactivated"] = 1
        audit.record(db, "demo.retired", details=out)
        db.commit()
    finally:
        db.close()
    return out
