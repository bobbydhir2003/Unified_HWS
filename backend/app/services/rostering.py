"""Staff rostering: coverage windows, gap detection and deterministic fill suggestions.

Hard constraints (never violated by a suggestion): correct role, no overlapping shift (also DB-enforced), not on time off,
≥ MIN_REST_HOURS between shifts, ≤ MAX_WEEK_HOURS in the trailing 7 days, required skill held and unexpired.
Ranking (soft): fewest hours this week, then longest rest. Each suggestion lists its reasons, so a manager can verify it.
"""

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import now
from app.models import (
    Clinic,
    Department,
    Membership,
    MembershipClinic,
    MembershipDepartment,
    MembershipRole,
    Shift,
    StaffSkill,
    TimeOff,
    User,
)

MIN_REST_HOURS = 10
MAX_WEEK_HOURS = 48
WINDOWS = {"day": (time(7, 0), 12), "night": (time(19, 0), 12)}
DEFAULT_MIN_STAFF = {"inpatient": {"nurse": {"day": 3, "night": 2}}, "icu": {"nurse": {"day": 2, "night": 2}},
                     "emergency": {"nurse": {"day": 2, "night": 2}, "doctor": {"day": 1, "night": 1}}}


def window(fac: Clinic, day, name: str) -> tuple[datetime, datetime]:
    start_t, hours = WINDOWS[name]
    start = datetime.combine(day, start_t, ZoneInfo(fac.timezone))
    return start, start + timedelta(hours=hours)


def requirements(dept: Department) -> dict:
    return (dept.settings or {}).get("min_staff") or DEFAULT_MIN_STAFF.get(dept.kind, {})


def coverage(db: Session, dept: Department, start: datetime, end: datetime, role: str) -> list[Shift]:
    """Shifts of `role` in the department covering at least half of the window."""
    shifts = db.scalars(select(Shift).where(Shift.department_id == dept.id, Shift.role == role, Shift.status == "scheduled",
                                            Shift.start_at < end, Shift.end_at > start)).all()
    half = (end - start) / 2
    return [s for s in shifts if min(s.end_at, end) - max(s.start_at, start) >= half]


def gaps(db: Session, org_id: uuid.UUID, hours_ahead: int = 48) -> list[dict]:
    out = []
    for dept in db.scalars(select(Department).where(Department.organization_id == org_id, Department.is_active.is_(True))):
        req = requirements(dept)
        if not req:
            continue
        fac = db.get(Clinic, dept.facility_id)
        today = now().astimezone(ZoneInfo(fac.timezone)).date()
        for d in range(0, hours_ahead // 24 + 1):
            for name in ("day", "night"):
                start, end = window(fac, today + timedelta(days=d), name)
                if end <= now() or start > now() + timedelta(hours=hours_ahead):
                    continue
                for role, per in req.items():
                    need = int(per.get(name, 0))
                    have = len(coverage(db, dept, start, end, role))
                    if have < need:
                        out.append({"department_id": dept.id, "department": dept.name, "facility_id": dept.facility_id, "role": role, "window": name,
                                    "start": start, "end": end, "required": need, "scheduled": have, "short": need - have})
    return out


def _eligible_users(db: Session, org_id, dept: Department, role: str) -> list[User]:
    q = (select(User).join(Membership, Membership.user_id == User.id).join(MembershipRole, MembershipRole.membership_id == Membership.id)
         .where(Membership.organization_id == org_id, Membership.is_active.is_(True), User.is_active.is_(True), MembershipRole.role == role)
         .where(or_(Membership.all_clinics.is_(True), Membership.id.in_(select(MembershipClinic.membership_id).where(MembershipClinic.clinic_id == dept.facility_id))))
         .where(or_(~Membership.id.in_(select(MembershipDepartment.membership_id)),
                    Membership.id.in_(select(MembershipDepartment.membership_id).where(MembershipDepartment.department_id == dept.id)))))
    return list(db.scalars(q.distinct()).all())


def check_candidate(db: Session, user_id, start: datetime, end: datetime, skill: str | None = None, exclude_shift_id=None) -> tuple[bool, list[str], dict]:
    reasons, info = [], {}
    q = select(Shift).where(Shift.user_id == user_id, Shift.status == "scheduled")
    if exclude_shift_id:
        q = q.where(Shift.id != exclude_shift_id)
    mine = db.scalars(q).all()
    if any(s.start_at < end and s.end_at > start for s in mine):
        return False, ["already working an overlapping shift"], info
    if db.scalar(select(TimeOff.id).where(TimeOff.user_id == user_id, TimeOff.start_at < end, TimeOff.end_at > start).limit(1)):
        return False, ["on approved time off"], info
    before = [s.end_at for s in mine if s.end_at <= start]
    after = [s.start_at for s in mine if s.start_at >= end]
    rest_before = (start - max(before)).total_seconds() / 3600 if before else 999
    rest_after = (min(after) - end).total_seconds() / 3600 if after else 999
    if min(rest_before, rest_after) < MIN_REST_HOURS:
        return False, [f"less than {MIN_REST_HOURS} h rest between shifts"], info
    week = sum(((min(s.end_at, end) - max(s.start_at, start - timedelta(days=7))).total_seconds() / 3600)
               for s in mine if s.end_at > start - timedelta(days=7) and s.start_at < end)
    hours = (end - start).total_seconds() / 3600
    if week + hours > MAX_WEEK_HOURS:
        return False, [f"would exceed {MAX_WEEK_HOURS} h in 7 days ({week:.0f} h scheduled)"], info
    if skill:
        sk = db.scalar(select(StaffSkill).where(StaffSkill.user_id == user_id, StaffSkill.skill == skill))
        if not sk or (sk.expires_on and sk.expires_on < start.date()):
            return False, [f"missing current {skill} credential"], info
        reasons.append(f"{skill} credential current")
    reasons += [f"{week:.0f} h scheduled in the last 7 days", f"{min(rest_before, rest_after):.0f} h rest" if min(rest_before, rest_after) < 999 else "fully rested"]
    info.update(week_hours=round(week, 1), rest_hours=min(rest_before, rest_after))
    return True, reasons, info


def suggest(db: Session, org_id, dept: Department, role: str, start: datetime, end: datetime, skill: str | None = None, limit: int = 5) -> list[dict]:
    out = []
    for u in _eligible_users(db, org_id, dept, role):
        ok, reasons, info = check_candidate(db, u.id, start, end, skill)
        if ok:
            out.append({"user_id": u.id, "name": u.display_name, "reasons": reasons, **info})
    out.sort(key=lambda x: (x["week_hours"], -x["rest_hours"]))
    return out[:limit]


def hours_by_user(db: Session, dept_id, start: datetime, end: datetime) -> dict:
    rows = db.execute(select(Shift.user_id, func.sum(func.extract("epoch", Shift.end_at - Shift.start_at) / 3600)).where(
        Shift.department_id == dept_id, Shift.status == "scheduled", Shift.start_at >= start, Shift.start_at < end).group_by(Shift.user_id)).all()
    return {u: float(h) for u, h in rows}
