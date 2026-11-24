"""Server-side Super Admin bootstrap and recovery. Requires shell access to the server (there is no public Super Admin
registration). Every command asks for typed confirmation, reads passwords without echo, never prints secrets or
hashes, and writes an audit event.

    uv run python -m app.cli list-superadmins
    uv run python -m app.cli create-superadmin --email owner@example.com --first Ada --last Owner [--org harborview]
    uv run python -m app.cli reset-password --email owner@example.com [--disable-mfa]
    uv run python -m app.cli set-email --email old@example.com --new-email new@example.com
    uv run python -m app.cli retire-demo   (one time: remove the former Demo Mode's demo hospitals and sessions)

In Docker: docker compose exec api python -m app.cli <command> …
"""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Callable

from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.core.security import hash_password, now, validate_password_strength
from app.models import Membership, MembershipRole, Organization, User, UserSession
from app.services import audit

Prompt = Callable[[str], str]


class CLIError(Exception):
    pass


def _confirm(phrase: str, ask: Prompt) -> None:
    got = ask(f'Type "{phrase}" to continue: ').strip()
    if got != phrase:
        raise CLIError("Confirmation did not match. Nothing was changed.")


def _new_password(secret: Prompt) -> str:
    pw = secret("New password: ")
    if pw != secret("Repeat new password: "):
        raise CLIError("Passwords did not match. Nothing was changed.")
    if err := validate_password_strength(pw):
        raise CLIError(err)
    return pw


def _user(db, email: str) -> User:
    u = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not u:
        raise CLIError("No account with that email.")
    return u


def _revoke_sessions(db, user: User) -> None:
    db.execute(update(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None)).values(revoked_at=now()))


def list_superadmins(out=print) -> list[str]:
    with SessionLocal() as db:
        rows = db.scalars(select(User).where(User.is_superadmin.is_(True)).order_by(User.email)).all()
        for u in rows:
            out(f"{u.email}\t{'active' if u.is_active else 'inactive'}\tMFA {'on' if u.mfa_enabled else 'off'}")
        return [u.email for u in rows]


def create_superadmin(email: str, first: str, last: str, org_slug: str | None, *, ask: Prompt = input, secret: Prompt = getpass.getpass) -> str:
    email = email.strip().lower()
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.email == email))
        if existing and existing.is_superadmin:
            raise CLIError("That account is already a Super Admin. Use reset-password to recover it.")
        org = db.scalar(select(Organization).where(Organization.slug == org_slug)) if org_slug else \
            db.scalar(select(Organization).order_by(Organization.created_at))
        if org_slug and not org:
            raise CLIError("No organization with that slug.")
        _confirm(f"{'PROMOTE' if existing else 'CREATE'} SUPERADMIN {email}", ask)
        if existing:
            u = existing  # promote: keeps their password
        else:
            u = User(email=email, first_name=first, last_name=last, password_hash=hash_password(_new_password(secret)))
            db.add(u)
            db.flush()
        u.is_superadmin, u.is_active = True, True
        if org and not db.scalar(select(Membership).where(Membership.user_id == u.id, Membership.organization_id == org.id)):
            m = Membership(user_id=u.id, organization_id=org.id, all_clinics=True)
            db.add(m)
            db.flush()
            m.roles.append(MembershipRole(role="super_admin"))
        audit.record(db, "auth.superadmin_promoted" if existing else "auth.superadmin_created", org_id=org.id if org else None,
                     resource_type="user", resource_id=u.id, details={"via": "server-cli"})
        db.commit()
        return "promoted" if existing else "created"


def reset_password(email: str, *, disable_mfa: bool = False, ask: Prompt = input, secret: Prompt = getpass.getpass) -> None:
    with SessionLocal() as db:
        u = _user(db, email)
        _confirm(f"RESET PASSWORD {u.email}", ask)
        u.password_hash = hash_password(_new_password(secret))
        u.failed_login_count, u.locked_until, u.is_active = 0, None, True
        if disable_mfa:
            u.mfa_enabled, u.mfa_secret = False, None
        _revoke_sessions(db, u)
        audit.record(db, "auth.password_reset_cli", resource_type="user", resource_id=u.id, details={"via": "server-cli", "mfa_disabled": disable_mfa})
        db.commit()


def set_email(email: str, new_email: str, *, ask: Prompt = input) -> None:
    new = new_email.strip().lower()
    if "@" not in new or len(new) > 320:
        raise CLIError("That doesn't look like an email address.")
    with SessionLocal() as db:
        u = _user(db, email)
        if db.scalar(select(User.id).where(User.email == new)):
            raise CLIError("Another account already uses that email.")
        _confirm(f"CHANGE EMAIL {u.email} TO {new}", ask)
        u.email = new
        _revoke_sessions(db, u)
        audit.record(db, "auth.email_changed_cli", resource_type="user", resource_id=u.id, details={"via": "server-cli"})
        db.commit()


def retire_demo(*, ask: Prompt = input) -> dict:
    """See app/demo_retirement.py. Only demo-owned data; real organizations and accounts are untouched."""
    _confirm("RETIRE DEMO", ask)
    from app.demo_retirement import retire

    return retire()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.cli", description="HMS Workflows server administration (Super Admin bootstrap/recovery).")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-superadmins")
    c = sub.add_parser("create-superadmin", help="Create (or promote) a Super Admin")
    c.add_argument("--email", required=True)
    c.add_argument("--first", default="Platform")
    c.add_argument("--last", default="Owner")
    c.add_argument("--org", help="Organization slug for the membership (default: the first organization)")
    r = sub.add_parser("reset-password", help="Set a new password (signs out all sessions)")
    r.add_argument("--email", required=True)
    r.add_argument("--disable-mfa", action="store_true", help="Also turn off MFA (lost authenticator)")
    e = sub.add_parser("set-email", help="Change an account's sign-in email (signs out all sessions)")
    e.add_argument("--email", required=True)
    e.add_argument("--new-email", required=True)
    sub.add_parser("retire-demo", help="Remove former demo hospitals, end demo sessions, deactivate the demo-only Super Admin")
    a = p.parse_args(argv)
    try:
        if a.cmd == "list-superadmins":
            if not list_superadmins():
                print("No Super Admin accounts.")
        elif a.cmd == "create-superadmin":
            print(f"Super Admin {create_superadmin(a.email, a.first, a.last, a.org)}.")
        elif a.cmd == "reset-password":
            reset_password(a.email, disable_mfa=a.disable_mfa)
            print("Password updated; all sessions were signed out.")
        elif a.cmd == "set-email":
            set_email(a.email, a.new_email)
            print("Email updated; all sessions were signed out.")
        elif a.cmd == "retire-demo":
            print(retire_demo())
    except CLIError as ex:
        print(f"Error: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
