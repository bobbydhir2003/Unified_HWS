"""Private demo hospitals (DEMO_MODE only).

Every demo visitor gets their OWN synthetic hospital — a separate organization built by the same builder as Harborview
(app.seed.build_hospital) — instead of sharing seven accounts in one organization. Isolation reuses the platform's
tenant model: each hospital is its own organization (TenantContext membership checks + PostgreSQL row-level security),
and its staff/patient identities exist only inside it.

Identities (users.sandbox_org_id set):
  * have no password hash and are refused by password sign-in, password reset and invitation acceptance;
  * are reachable only through a demo LEASE: every session carries sandbox_lease_id, and every request checks that the
    lease is still active and belongs to that hospital (deps.get_auth_user → check_session);
  * are deleted with the hospital (users.sandbox_org_id → organizations ON DELETE CASCADE).

Lifecycle (one row in demo_sandboxes per hospital):
  building → ready (pool) → leased (one visitor) → releasing (expired / reset / stale) → purging → purged
`maintain()` runs from Celery beat (or the in-process scheduler in development): it expires idle/old leases, removes
released hospitals (database rows via one cascading delete under an authorised-purge marker that the append-only
triggers recognise, plus stored files), retires pool hospitals built on an earlier day, and builds new ones up to the
pool size. Audit: lifecycle events are recorded platform-level (no organization, no actor) so they outlive the hospital.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.core.security import now
from app.models import DemoSandbox, Membership, Organization, User, UserSession

log = logging.getLogger("undeclared.demo.sandbox")

HOSPITAL_TZ = ZoneInfo("America/New_York")
LIVE = ("building", "ready", "leased", "releasing", "purging")


@dataclass(frozen=True)
class DemoRole:
    key: str     # stable key used by the demo buttons and the role switcher
    role: str    # the actual application role (app.core.permissions.Role)
    label: str   # ROLE_LABELS wording
    local: str   # the identity inside each demo hospital (<local>@<tag>.demo.example.com)
    featured: bool = False  # shown on the public homepage cards


def _roles() -> list[DemoRole]:
    from app.core.permissions import ROLE_LABELS, Role

    rows = [  # every role defined in app.core.permissions.Role, in a sensible switcher order
        ("super_admin", Role.SUPER_ADMIN, "superadmin", True),
        ("hospital_admin", Role.HOSPITAL_ADMIN, "hospitaladmin", False),
        ("clinic_admin", Role.CLINIC_ADMIN, "clinicadmin", True),
        ("doctor", Role.DOCTOR, "dr.chen", True),
        ("nurse", Role.NURSE, "nurse.rivera", True),
        ("front_desk", Role.RECEPTIONIST, "frontdesk", True),
        ("billing", Role.BILLING, "billing", True),
        ("insurance_specialist", Role.INSURANCE_SPECIALIST, "insurance", False),
        ("pharmacist", Role.PHARMACIST, "pharmacist", False),
        ("lab_tech", Role.LAB_TECH, "lab", False),
        ("radiology_tech", Role.RADIOLOGY_TECH, "radtech", False),
        ("radiologist", Role.RADIOLOGIST, "radiology", False),
        ("bed_manager", Role.BED_MANAGER, "bedmanager", False),
        ("patient", Role.PATIENT, "patient", True),
    ]
    return [DemoRole(k, r.value, ROLE_LABELS[r], local, feat) for k, r, local, feat in rows]


ROLES: list[DemoRole] = _roles()
BY_KEY = {r.key: r for r in ROLES}
BY_LOCAL = {r.local: r for r in ROLES}


# Organization settings that make a hospital a (synthetic) demo hospital; a visitor can change any other setting.
PROTECTED_ORG_SETTINGS = frozenset({"synthetic_data", "sandbox", "fax_webhook_secret", "voice_webhook_secret"})


class SandboxUnavailable(Exception):
    """A demo hospital can't be provided right now (pool exhausted, per-visitor limit, unsafe configuration)."""


def enabled() -> bool:
    from app.core import demo

    return demo.enabled() and settings.demo_sandbox_enabled


def external_effects_simulated() -> bool:
    """Demo hospitals run real internal workflows but must never reach the outside world. Fail closed if an operator
    has configured any non-simulated integration adapter."""
    from app.integrations.adapters import status

    safe = {"simulated", "outbox"}
    return all(v in safe for v in status().values())


def visitor_hash(ip: str | None) -> str:
    return hashlib.sha256(f"{settings.secret_key}|demo-visitor|{ip or 'unknown'}".encode()).hexdigest()


def email_for(tag: str, local: str) -> str:
    return f"{local}@{tag}.demo.example.com"


# ---------------------------------------------------------------------------------------------- lookups

_org_cache: dict = {"at": 0.0, "ids": frozenset()}


def sandbox_org_ids(db: Session | None = None) -> frozenset:
    """Organizations that are demo hospitals in any live state (cached briefly; used to keep the platform AI key and
    background work away from them)."""
    if time.monotonic() - _org_cache["at"] < 30:
        return _org_cache["ids"]
    own = db is None
    db = db or SessionLocal()
    try:
        ids = frozenset(db.scalars(select(DemoSandbox.organization_id).where(DemoSandbox.status.in_(LIVE),
                                                                             DemoSandbox.organization_id.is_not(None))))
    finally:
        if own:
            db.close()
    _org_cache.update(at=time.monotonic(), ids=ids)
    return ids


def invalidate_cache() -> None:
    _org_cache["at"] = 0.0


def is_sandbox_org(org_id, db: Session | None = None) -> bool:
    if org_id is None:
        return False
    if org_id in sandbox_org_ids(db):
        return True
    # A cold/just-built hospital may not be in the cache yet: confirm from the table (never guess "not a sandbox").
    own = db is None
    db = db or SessionLocal()
    try:
        hit = db.scalar(select(DemoSandbox.id).where(DemoSandbox.organization_id == org_id)) is not None
    finally:
        if own:
            db.close()
    if hit:
        invalidate_cache()
    return hit


def inactive_sandbox_org_ids(db: Session) -> set:
    """Hospitals nobody is using (pool, being built or removed): background monitors skip them."""
    return set(db.scalars(select(DemoSandbox.organization_id).where(DemoSandbox.status.in_(("building", "ready", "releasing", "purging", "failed")),
                                                                    DemoSandbox.organization_id.is_not(None))))


def default_ai_scope(db: Session, org_id) -> str | None:
    """Background AI work for a demo hospital with no visitor scope (e.g. a fax webhook, automatic case assistance) uses
    the owner-managed demo provider or the labelled simulation — never the platform key."""
    return f"org:{org_id}" if is_sandbox_org(org_id, db) else None


def for_lease(db: Session, lease_id) -> DemoSandbox | None:
    return db.scalar(select(DemoSandbox).where(DemoSandbox.lease_id == lease_id)) if lease_id else None


def role_of(user: User) -> DemoRole | None:
    return BY_LOCAL.get(user.email.split("@", 1)[0])


# ---------------------------------------------------------------------------------------------- building

_build_lock = threading.Lock()


def _npi(base: str) -> str:
    """A Luhn-valid synthetic NPI (prefix 80840 per the NPI check-digit rule)."""
    digits = [int(c) for c in "80840" + base]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            d *= 2
            d = d - 9 if d > 9 else d
        total += d
    return base + str((10 - total % 10) % 10)


def _extras(db: Session, org: Organization) -> None:
    """Identities the demo needs beyond the Harborview staff: a Super Admin inside the hospital (with a provider profile
    so clinical signing can be exercised) and a separate radiology technologist."""
    from app.models import Clinic, Department, MembershipClinic, MembershipDepartment, ProviderProfile
    from app.seed import em, member, user

    sa = user(db, em("superadmin"), "Alex", "Morgan", "MD")
    member(db, sa, org, "super_admin")
    db.add(ProviderProfile(organization_id=org.id, user_id=sa.id, specialty="Hospital Medicine", credentials="MD", color="slate",
                           npi=_npi("123456789")))
    hosp = db.scalar(select(Clinic).where(Clinic.organization_id == org.id, Clinic.facility_type == "hospital"))
    if hosp:
        rt = user(db, em("radtech"), "Jamie", "Ortega", "RT(R)")
        m = Membership(user_id=rt.id, organization_id=org.id, all_clinics=False)
        db.add(m)
        db.flush()
        from app.models import MembershipRole

        m.roles.append(MembershipRole(role="radiology_tech"))
        m.clinics.append(MembershipClinic(clinic_id=hosp.id))
        dept = db.scalar(select(Department.id).where(Department.facility_id == hosp.id, Department.code == "RAD"))
        if dept:
            m.departments.append(MembershipDepartment(department_id=dept))
    db.flush()


def build(reason: str = "pool") -> DemoSandbox:
    """Build one complete demo hospital and add it to the pool (status ready). Serialised per process: the seed builder
    uses module-level identity settings and a deterministic random generator so every hospital starts identical."""
    import app.seed as seed
    from app.engine.events import dispatch_pending
    from app.engine.monitors import run_all
    from app.seed_extend import extend_org

    tag = secrets.token_hex(4)
    db = SessionLocal()
    sb = DemoSandbox(tag=tag, status="building", created_at=now())
    db.add(sb)
    db.commit()
    started = time.monotonic()
    try:
        with _build_lock:
            saved = dict(seed._IDENTITY)
            seed.rng = seed.random.Random(seed.RNG_SEED)
            seed._IDENTITY.update(domain=f"{tag}.demo.example.com", sandbox_org_id=None)
            try:
                org = seed.build_hospital(db, name="Harborview Health", slug=f"demo-{tag}", sandbox=True)
                org.settings = {**(org.settings or {}), "sandbox": True}
                sb.organization_id = org.id
                db.flush()
                extend_org(db, org)
                _extras(db, org)
            finally:
                seed._IDENTITY.clear()
                seed._IDENTITY.update(saved)
        db.commit()
        run_all(db, [org.id])  # initial automation pass, exactly like the first Harborview seed
        db.commit()
        sb.status, sb.ready_at, sb.build_seconds = "ready", now(), round(time.monotonic() - started, 2)
        _platform_audit(db, "demo.sandbox_built", sb, {"reason": reason, "seconds": sb.build_seconds})
        db.commit()
        invalidate_cache()
        dispatch_pending()
        log.info("demo hospital built", extra={"tag": tag, "seconds": sb.build_seconds})
        db.refresh(sb)
        return sb
    except Exception as e:
        db.rollback()
        sb = db.get(DemoSandbox, sb.id)
        if sb:
            sb.status, sb.error = "failed", f"{type(e).__name__}: {str(e)[:400]}"
            db.commit()
        log.exception("demo hospital build failed")
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------------------------- leasing

def lease(db: Session, *, visitor: str, exclude: uuid.UUID | None = None) -> DemoSandbox:
    """Give a visitor a ready hospital (or build one now if the pool is empty and the cap allows)."""
    if not enabled():
        raise SandboxUnavailable("Demo hospitals aren't available on this server.")
    if not external_effects_simulated():
        raise SandboxUnavailable("Demo hospitals are disabled because a live external integration is configured.")
    open_now = db.scalar(select(func.count()).select_from(DemoSandbox).where(
        DemoSandbox.status == "leased", DemoSandbox.visitor_hash == visitor, DemoSandbox.id != (exclude or uuid.uuid4())))
    if open_now >= settings.demo_sandbox_per_visitor:
        raise SandboxUnavailable(f"You already have {open_now} demo hospitals open. Use Reset my hospital in your open demo, "
                                 "or wait for an older one to expire.")
    row = db.scalar(select(DemoSandbox).where(DemoSandbox.status == "ready").order_by(DemoSandbox.ready_at)
                    .with_for_update(skip_locked=True).limit(1))
    if row is None:
        live = db.scalar(select(func.count()).select_from(DemoSandbox).where(DemoSandbox.status.in_(LIVE)))
        if live >= settings.demo_sandbox_max_total:
            raise SandboxUnavailable("All demo hospitals are in use right now. Please try again in a few minutes.")
        db.commit()  # don't hold locks while building
        try:
            build(reason="on-demand")
        except Exception:
            raise SandboxUnavailable("A demo hospital couldn't be prepared. Please try again in a moment.") from None
        row = db.scalar(select(DemoSandbox).where(DemoSandbox.status == "ready").order_by(DemoSandbox.ready_at)
                        .with_for_update(skip_locked=True).limit(1))
        if row is None:
            raise SandboxUnavailable("All demo hospitals are in use right now. Please try again in a few minutes.")
    t = now()
    row.status, row.lease_id, row.visitor_hash = "leased", uuid.uuid4(), visitor
    row.leased_at = row.last_active_at = t
    row.expires_at = t + timedelta(hours=settings.demo_sandbox_max_hours)
    _platform_audit(db, "demo.sandbox_leased", row, {})
    db.flush()
    return row


def identity(db: Session, sb: DemoSandbox, *, key: str | None = None, user_id: uuid.UUID | None = None) -> User | None:
    """A staff/patient identity of THIS hospital: by demo role key, or any active member chosen in the switcher."""
    if user_id is not None:
        u = db.get(User, user_id)
    else:
        r = BY_KEY.get(key or "")
        if not r:
            return None
        u = db.scalar(select(User).where(User.email == email_for(sb.tag, r.local)))
    if not u or not u.is_active or u.sandbox_org_id != sb.organization_id:
        return None
    m = db.scalar(select(Membership).where(Membership.user_id == u.id, Membership.organization_id == sb.organization_id,
                                           Membership.is_active.is_(True)))
    return u if m else None


def open_session(db: Session, sb: DemoSandbox, user: User, request, response):
    """Issue a normal session for a hospital identity, bound to the visitor's lease."""
    from app.services.identity import issue_session

    out = issue_session(db, user, request, response, sandbox_lease_id=sb.lease_id, ai_root=sb.root_session_id)
    if sb.root_session_id is None:  # the first session of a lease keys the visitor's demo AI settings and limits
        sid = db.scalar(select(UserSession.id).where(UserSession.user_id == user.id, UserSession.sandbox_lease_id == sb.lease_id)
                        .order_by(UserSession.created_at.desc()).limit(1))
        sb.root_session_id = sid
        db.flush()
        from app.services.identity import access_token_for

        out.access_token = access_token_for(user, sid, sandbox_lease_id=sb.lease_id, ai_root=sid)
    return out


def check_session(db: Session, user: User, sess: UserSession) -> DemoSandbox:
    """Every request of a hospital identity: the lease must be active, unexpired, and for this identity's hospital."""
    from fastapi import HTTPException

    expired = HTTPException(401, {"code": "demo_expired", "message": "This demo hospital has ended. Start a new demo to continue."})
    if not enabled() or sess.sandbox_lease_id is None:
        raise expired
    sb = for_lease(db, sess.sandbox_lease_id)
    t = now()
    if (not sb or sb.status != "leased" or sb.organization_id != user.sandbox_org_id or (sb.expires_at and sb.expires_at <= t)
            or (sb.last_active_at and sb.last_active_at <= t - timedelta(hours=settings.demo_sandbox_idle_hours))):
        raise expired
    _touch(sb)
    return sb


_touched: dict = {}


def _touch(sb: DemoSandbox) -> None:
    """Record activity at most once a minute per hospital (a separate tiny transaction; never blocks the request)."""
    mono = time.monotonic()
    if mono - _touched.get(sb.id, 0.0) < 60:
        return
    _touched[sb.id] = mono
    try:
        with engine.begin() as c:
            c.execute(update(DemoSandbox).where(DemoSandbox.id == sb.id, DemoSandbox.status == "leased").values(last_active_at=now()))
    except Exception:  # activity tracking must never fail a request
        log.warning("demo activity update failed", exc_info=True)


def info(db: Session, sb: DemoSandbox, user: User) -> dict:
    """What the demo banner and role switcher show."""
    r = role_of(user)
    idle_at = (sb.last_active_at or now()) + timedelta(hours=settings.demo_sandbox_idle_hours)
    staff = db.execute(
        select(User.id, User.first_name, User.last_name, User.title, Membership.id, User.email)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == sb.organization_id, Membership.is_active.is_(True), User.sandbox_org_id == sb.organization_id)
        .order_by(User.last_name)
    ).all()
    member_roles = {}
    from app.models import MembershipRole

    for mid, role in db.execute(select(MembershipRole.membership_id, MembershipRole.role).where(
            MembershipRole.membership_id.in_([s[4] for s in staff]))):
        member_roles.setdefault(mid, []).append(role)
    return {
        "hospital": f"Demo hospital {sb.tag.upper()}", "tag": sb.tag, "expires_at": min(sb.expires_at, idle_at) if sb.expires_at else idle_at,
        "hard_expires_at": sb.expires_at, "idle_hours": settings.demo_sandbox_idle_hours,
        "role_key": r.key if r else None, "role_label": r.label if r else None,
        "roles": [{"key": x.key, "role": x.role, "label": x.label} for x in ROLES],
        "people": [{"user_id": str(uid), "name": f"{fn} {ln}".strip(), "title": t, "roles": sorted(member_roles.get(mid, [])),
                    "role_key": (BY_LOCAL.get(email.split("@", 1)[0]).key if BY_LOCAL.get(email.split("@", 1)[0]) else None)}
                   for uid, fn, ln, t, mid, email in staff],
    }


def add_staff(db: Session, org_id, inv) -> User:
    """A staff member 'invited' in a demo hospital: created directly as a sign-in-less identity of that hospital."""
    import re

    from app.models import MembershipClinic, MembershipRole

    sb = db.scalar(select(DemoSandbox).where(DemoSandbox.organization_id == org_id))
    base = re.sub(r"[^a-z0-9]+", ".", inv.email.split("@", 1)[0].lower()).strip(".")[:40] or "staff"
    email, n = email_for(sb.tag, f"staff.{base}"), 1
    while db.scalar(select(User.id).where(User.email == email)):
        n += 1
        email = email_for(sb.tag, f"staff.{base}.{n}")
    u = User(email=email, first_name=inv.first_name, last_name=inv.last_name, password_hash=None, sandbox_org_id=org_id)
    db.add(u)
    db.flush()
    m = Membership(user_id=u.id, organization_id=org_id, all_clinics=not inv.clinic_ids)
    db.add(m)
    db.flush()
    for r in inv.roles:
        m.roles.append(MembershipRole(role=r))
    for cid in inv.clinic_ids or []:
        m.clinics.append(MembershipClinic(clinic_id=uuid.UUID(cid)))
    inv.accepted_at = now()
    db.flush()
    return u


# ---------------------------------------------------------------------------------------------- release & purge

def release(db: Session, sb: DemoSandbox, reason: str) -> None:
    """End a lease: no session of it works any more; the hospital is queued for removal."""
    if sb.status not in ("leased", "ready", "building", "failed"):
        return
    sb.status, sb.released_at, sb.release_reason = "releasing", now(), reason[:20]
    if sb.lease_id:
        db.execute(update(UserSession).where(UserSession.sandbox_lease_id == sb.lease_id, UserSession.revoked_at.is_(None))
                   .values(revoked_at=now()))
    _platform_audit(db, "demo.sandbox_released", sb, {"reason": reason})
    db.flush()


def purge(sandbox_id: uuid.UUID) -> bool:
    """Remove a released hospital completely: every row of its organization (one cascading delete), its identities and
    their sessions/AI settings, its usage counters, and its stored files. Only rows of THIS organization can pass the
    append-only triggers, and only while this row is in status 'purging'."""
    db = SessionLocal()
    try:
        sb = db.get(DemoSandbox, sandbox_id)
        if not sb or sb.status not in ("releasing", "failed", "purging"):
            return False
        org_id, root = sb.organization_id, sb.root_session_id
        keys: list[str] = []
        if org_id:
            from app.models import Document, ScribeSession

            keys = [k for k in db.scalars(select(Document.storage_key).where(Document.organization_id == org_id)) if k]
            keys += [k for k in db.scalars(select(ScribeSession.audio_storage_key).where(ScribeSession.organization_id == org_id)) if k]
            # Refuse anything that isn't registered as a demo hospital organization with our slug pattern.
            org = db.get(Organization, org_id)
            if org and not (org.slug == f"demo-{sb.tag}" and (org.settings or {}).get("synthetic_data")):
                sb.status, sb.error = "failed", "refused: organization does not look like this demo hospital"
                db.commit()
                log.error("demo purge refused", extra={"tag": sb.tag})
                return False
        db.close()
        with engine.begin() as c:
            c.execute(update(DemoSandbox).where(DemoSandbox.id == sandbox_id).values(status="purging"))
            if org_id:
                c.exec_driver_sql("SELECT set_config('app.sandbox_purge', %s, true)", (str(org_id),))
                c.execute(text("DELETE FROM audit_events WHERE organization_id = :o OR actor_user_id IN "
                               "(SELECT id FROM users WHERE sandbox_org_id = :o)"), {"o": org_id})
                c.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": org_id})
                c.execute(text("DELETE FROM users WHERE sandbox_org_id = :o"), {"o": org_id})  # normally already cascaded
                c.exec_driver_sql("SELECT set_config('app.sandbox_purge', '', true)")
            if root:
                c.execute(text("DELETE FROM ai_usage_counters WHERE key LIKE :k"), {"k": f"%{root}%"})
            if org_id:
                c.execute(text("DELETE FROM ai_usage_counters WHERE key LIKE :k"), {"k": f"%{org_id}%"})
            c.execute(update(DemoSandbox).where(DemoSandbox.id == sandbox_id).values(status="purged", purged_at=now()))
        _delete_files(org_id, keys)
        db = SessionLocal()
        sb = db.get(DemoSandbox, sandbox_id)
        _platform_audit(db, "demo.sandbox_purged", sb, {"files": len(keys)})
        db.commit()
        invalidate_cache()
        return True
    except Exception as e:
        log.exception("demo hospital purge failed")
        try:
            db.rollback()
            with engine.begin() as c:
                c.execute(update(DemoSandbox).where(DemoSandbox.id == sandbox_id, DemoSandbox.status != "purged")
                          .values(status="releasing", error=f"purge: {type(e).__name__}: {str(e)[:300]}"))
        except Exception:
            log.exception("could not record purge failure")
        return False
    finally:
        db.close()


def _delete_files(org_id, keys: list[str]) -> None:
    from app.services.storage import storage

    for k in keys:
        try:
            storage.delete(k)
        except Exception:
            log.warning("demo file delete failed", exc_info=True)
    if org_id and settings.storage_backend == "local":  # anything else written under the organization's prefix
        root = Path(settings.storage_local_path).resolve() / str(org_id)
        if root.is_dir() and root.parent == Path(settings.storage_local_path).resolve():
            shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------------------------- maintenance

def _stale(sb: DemoSandbox) -> bool:
    """Pool hospitals are built with 'today's' schedule; retire ones built on an earlier hospital-local day."""
    ref = sb.ready_at or sb.created_at
    return ref.astimezone(HOSPITAL_TZ).date() != now().astimezone(HOSPITAL_TZ).date()


def maintain(*, build_limit: int = 1) -> dict:
    """Expire, purge, retire and replenish. Safe to run concurrently with requests; idempotent."""
    out = {"expired": 0, "purged": 0, "retired": 0, "built": 0, "failed_builds": 0}
    if not enabled():
        return out
    db = SessionLocal()
    try:
        t = now()
        idle_cut = t - timedelta(hours=settings.demo_sandbox_idle_hours)
        for sb in db.scalars(select(DemoSandbox).where(DemoSandbox.status == "leased")):
            if (sb.expires_at and sb.expires_at <= t) or (sb.last_active_at and sb.last_active_at <= idle_cut):
                release(db, sb, "expired" if sb.expires_at and sb.expires_at <= t else "idle")
                out["expired"] += 1
        for sb in db.scalars(select(DemoSandbox).where(DemoSandbox.status == "ready")):
            if _stale(sb):
                release(db, sb, "stale")
                out["retired"] += 1
        stuck = t - timedelta(minutes=30)
        for sb in db.scalars(select(DemoSandbox).where(DemoSandbox.status == "building", DemoSandbox.created_at <= stuck)):
            sb.status, sb.error = "failed", "build did not finish"
        db.commit()
        todo = list(db.scalars(select(DemoSandbox.id).where(
            (DemoSandbox.status.in_(("releasing", "purging"))) | ((DemoSandbox.status == "failed") & DemoSandbox.organization_id.is_not(None)
                                                                  & DemoSandbox.purged_at.is_(None)))))
        # Purged history older than 30 days is no longer needed (the platform audit log keeps the lifecycle events).
        db.execute(delete(DemoSandbox).where(DemoSandbox.status == "purged", DemoSandbox.purged_at <= t - timedelta(days=30)))
        db.execute(delete(DemoSandbox).where(DemoSandbox.status == "failed", DemoSandbox.organization_id.is_(None),
                                             DemoSandbox.created_at <= t - timedelta(days=1)))
        db.commit()
    finally:
        db.close()
    for sid in todo:
        out["purged"] += int(purge(sid))
    for _ in range(max(0, build_limit)):
        db = SessionLocal()
        try:
            ready = db.scalar(select(func.count()).select_from(DemoSandbox).where(DemoSandbox.status.in_(("ready", "building"))))
            live = db.scalar(select(func.count()).select_from(DemoSandbox).where(DemoSandbox.status.in_(LIVE)))
        finally:
            db.close()
        if ready >= settings.demo_sandbox_pool_size or live >= settings.demo_sandbox_max_total or not external_effects_simulated():
            break
        try:
            build()
            out["built"] += 1
        except Exception:
            out["failed_builds"] += 1
            break
    return out


def status(db: Session) -> dict:
    """Operator view (counts only)."""
    rows = dict(db.execute(select(DemoSandbox.status, func.count()).group_by(DemoSandbox.status)).all())
    return {"pool_size": settings.demo_sandbox_pool_size, "max_total": settings.demo_sandbox_max_total, "by_status": rows,
            "external_effects_simulated": external_effects_simulated()}


def _platform_audit(db: Session, action: str, sb: DemoSandbox | None, details: dict) -> None:
    from app.services import audit

    if sb is None:
        return
    audit.record(db, action, org_id=None, actor_id=None, resource_type="demo_sandbox", resource_id=sb.id,
                 details={"tag": sb.tag, "status": sb.status, **details})
