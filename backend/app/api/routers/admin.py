import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError

from app.api.deps import TenantContext, get_auth_user, get_ctx, require
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.permissions import P, Role
from app.core.security import hash_token, new_opaque_token, now
from app.integrations.adapters import status as adapter_status
from app.models import (
    AuditEvent,
    Clinic,
    Invitation,
    Membership,
    MembershipClinic,
    MembershipRole,
    Organization,
    OutboundMessage,
    ProviderProfile,
    User,
)
from app.schemas.admin import (
    AuditOut,
    ClinicIn,
    ClinicOut,
    InvitationCreated,
    InvitationIn,
    InvitationOut,
    OrgCreate,
    OrgOut,
    OrgUpdate,
    OutboxOut,
    ProviderInfo,
    StaffOut,
    StaffUpdate,
)
from app.schemas.common import Message, Page
from app.services import audit
from app.services.identity import send_email

router = APIRouter(tags=["admin"])


# ---------- Organizations ----------

@router.get("/organizations", response_model=list[OrgOut])
def list_orgs(auth=Depends(get_auth_user), db=Depends(get_db)):
    q = select(Organization).order_by(Organization.name)
    if not auth.user.is_superadmin:
        q = q.where(Organization.id.in_([m.organization_id for m in auth.user.memberships if m.is_active]))
    return db.scalars(q).all()


@router.post("/organizations", response_model=OrgOut, status_code=201)
def create_org(body: OrgCreate, ctx: TenantContext = Depends(require(P.ORG_MANAGE))):
    from app.core.db import unbind_tenant

    unbind_tenant(ctx.db)  # platform operation: creates rows in a new organization
    db = ctx.db
    if db.scalar(select(Organization.id).where(Organization.slug == body.slug)):
        raise conflict("An organization with that slug already exists")
    org = Organization(name=body.name, slug=body.slug, settings={})
    db.add(org)
    db.flush()
    db.add(Clinic(organization_id=org.id, name=body.first_clinic_name, code=body.first_clinic_code,
                  timezone=body.timezone, rooms=["Exam 1", "Exam 2"]))
    audit.record(db, "org.created", org_id=org.id, actor_id=ctx.user.id, resource_type="organization",
                 resource_id=org.id, request=ctx.request)
    if body.admin_email:
        _create_invitation(ctx, org.id, InvitationIn(
            email=body.admin_email, first_name=body.admin_first_name or "Clinic",
            last_name=body.admin_last_name or "Admin", roles=[Role.CLINIC_ADMIN]))
    db.commit()
    return org


@router.get("/organization", response_model=OrgOut)
def current_org(ctx: TenantContext = Depends(get_ctx)):
    return ctx.db.get(Organization, ctx.org_id)


@router.patch("/organization", response_model=OrgOut)
def update_org(body: OrgUpdate, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    org = ctx.db.get(Organization, ctx.org_id)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and not ctx.can(P.ORG_MANAGE):
        raise forbidden("Only platform administrators can change organization status")
    if "settings" in data:
        org.settings = {**(org.settings or {}), **(data.pop("settings") or {})}
    for k, v in data.items():
        setattr(org, k, v)
    ctx.audit("org.updated", resource_type="organization", resource_id=org.id, details={"fields": list(body.model_fields_set)})
    ctx.db.commit()
    return org


# ---------- Clinics ----------

@router.get("/clinics", response_model=list[ClinicOut])
def list_clinics(include_inactive: bool = False, ctx: TenantContext = Depends(get_ctx)):
    q = select(Clinic).where(Clinic.organization_id == ctx.org_id).order_by(Clinic.name)
    if not include_inactive:
        q = q.where(Clinic.is_active.is_(True))
    if ctx.clinic_ids is not None:
        q = q.where(Clinic.id.in_(ctx.clinic_ids))
    return ctx.db.scalars(q).all()


@router.post("/clinics", response_model=ClinicOut, status_code=201)
def create_clinic(body: ClinicIn, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    clinic = Clinic(organization_id=ctx.org_id, **body.model_dump())
    ctx.db.add(clinic)
    try:
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise conflict("A clinic with that code already exists") from None
    ctx.audit("clinic.created", resource_type="clinic", resource_id=clinic.id)
    ctx.db.commit()
    return clinic


@router.patch("/clinics/{clinic_id}", response_model=ClinicOut)
def update_clinic(clinic_id: uuid.UUID, body: ClinicIn, ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    clinic = ctx.db.get(Clinic, clinic_id)
    if not clinic or clinic.organization_id != ctx.org_id:
        raise not_found("Clinic")
    for k, v in body.model_dump().items():
        setattr(clinic, k, v)
    ctx.audit("clinic.updated", resource_type="clinic", resource_id=clinic.id)
    ctx.db.commit()
    return clinic


# ---------- Staff ----------

def _staff_out(ctx: TenantContext, m: Membership) -> StaffOut:
    prov = ctx.db.scalar(select(ProviderProfile).where(ProviderProfile.organization_id == ctx.org_id,
                                                       ProviderProfile.user_id == m.user_id))
    u = m.user
    return StaffOut(
        membership_id=m.id, user_id=u.id, email=u.email, first_name=u.first_name, last_name=u.last_name,
        title=u.title, roles=m.role_names, is_active=m.is_active and u.is_active, all_clinics=m.all_clinics,
        clinic_ids=[c.clinic_id for c in m.clinics], department_ids=[d.department_id for d in m.departments], mfa_enabled=u.mfa_enabled, last_login_at=u.last_login_at,
        provider=ProviderInfo.model_validate(prov) if prov else None,
    )


@router.get("/staff", response_model=list[StaffOut])
def list_staff(q: str | None = None, role: str | None = None, ctx: TenantContext = Depends(require(P.USERS_MANAGE))):
    stmt = (select(Membership).join(User).where(Membership.organization_id == ctx.org_id)
            .order_by(User.last_name, User.first_name))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.email).like(like), func.lower(User.first_name + " " + User.last_name).like(like)))
    if role:
        stmt = stmt.where(Membership.roles.any(MembershipRole.role == role))
    else:
        stmt = stmt.where(~Membership.roles.any(MembershipRole.role == "patient"))
    return [_staff_out(ctx, m) for m in ctx.db.scalars(stmt).unique().all()]


@router.patch("/staff/{membership_id}", response_model=StaffOut)
def update_staff(membership_id: uuid.UUID, body: StaffUpdate, ctx: TenantContext = Depends(require(P.USERS_MANAGE))):
    db = ctx.db
    m = db.get(Membership, membership_id)
    if not m or m.organization_id != ctx.org_id:
        raise not_found("Staff member")
    if m.user_id == ctx.user.id and (body.is_active is False or (body.roles is not None and Role.CLINIC_ADMIN not in body.roles
                                                                 and ctx.has_role(Role.CLINIC_ADMIN)
                                                                 and Role.HOSPITAL_ADMIN not in body.roles)):
        raise bad_request("You can't deactivate yourself or remove your own admin role")
    if body.roles is not None:
        if Role.SUPER_ADMIN in body.roles and not ctx.can(P.ORG_MANAGE):
            raise forbidden("Only platform administrators can grant Super Admin")
        m.roles.clear()
        db.flush()
        for r in sorted(set(body.roles)):
            m.roles.append(MembershipRole(role=r.value))
    if body.is_active is not None:
        m.is_active = body.is_active
    if body.all_clinics is not None:
        m.all_clinics = body.all_clinics
    if body.clinic_ids is not None:
        valid = set(db.scalars(select(Clinic.id).where(Clinic.organization_id == ctx.org_id, Clinic.id.in_(body.clinic_ids))))
        m.clinics.clear()
        db.flush()
        for cid in valid:
            m.clinics.append(MembershipClinic(clinic_id=cid))
    if body.department_ids is not None:
        from app.models import Department, MembershipDepartment

        valid_d = set(db.scalars(select(Department.id).where(Department.organization_id == ctx.org_id, Department.id.in_(body.department_ids))))
        m.departments.clear()
        db.flush()
        for did in valid_d:
            m.departments.append(MembershipDepartment(department_id=did))
    if body.title is not None:
        m.user.title = body.title or None
    if body.provider is not None:
        prov = db.scalar(select(ProviderProfile).where(ProviderProfile.organization_id == ctx.org_id,
                                                       ProviderProfile.user_id == m.user_id))
        if prov is None:
            prov = ProviderProfile(organization_id=ctx.org_id, user_id=m.user_id)
            db.add(prov)
        for k, v in body.provider.model_dump().items():
            setattr(prov, k, v)
    ctx.audit("user.updated", resource_type="membership", resource_id=m.id,
              details={"fields": sorted(body.model_fields_set), "roles": [r.value for r in body.roles or []]})
    db.commit()
    db.refresh(m)
    return _staff_out(ctx, m)


# ---------- Invitations ----------

def _create_invitation(ctx: TenantContext, org_id: uuid.UUID, body: InvitationIn) -> tuple[Invitation, str]:
    if Role.SUPER_ADMIN in body.roles and not ctx.can(P.ORG_MANAGE):
        raise forbidden("Only platform administrators can grant Super Admin")
    token = new_opaque_token()
    inv = Invitation(
        organization_id=org_id, email=body.email.lower(), first_name=body.first_name, last_name=body.last_name,
        roles=[r.value for r in body.roles], clinic_ids=[str(c) for c in body.clinic_ids] if body.clinic_ids else None,
        token_hash=hash_token(token), invited_by_id=ctx.user.id, expires_at=now() + timedelta(days=7),
    )
    ctx.db.add(inv)
    ctx.db.flush()
    link = f"{settings.frontend_url}/accept-invite?token={token}"
    org = ctx.db.get(Organization, org_id)
    send_email(ctx.db, inv.email, f"You're invited to {org.name} on Undeclared",
               f"{ctx.user.full_name} invited you to join {org.name}.\nAccept within 7 days: {link}", org_id)
    audit.record(ctx.db, "user.invited", org_id=org_id, actor_id=ctx.user.id, resource_type="invitation",
                 resource_id=inv.id, request=ctx.request, details={"roles": inv.roles})
    return inv, link


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(ctx: TenantContext = Depends(require(P.USERS_MANAGE))):
    return ctx.db.scalars(select(Invitation).where(Invitation.organization_id == ctx.org_id)
                          .order_by(Invitation.created_at.desc()).limit(200)).all()


@router.post("/invitations", response_model=InvitationCreated, status_code=201)
def create_invitation(body: InvitationIn, ctx: TenantContext = Depends(require(P.USERS_MANAGE))):
    existing = ctx.db.scalar(select(Membership).join(User).where(
        Membership.organization_id == ctx.org_id, User.email == body.email.lower(), Membership.is_active.is_(True)))
    if existing:
        raise conflict("That person is already an active member of this organization")
    inv, link = _create_invitation(ctx, ctx.org_id, body)
    ctx.db.commit()
    return InvitationCreated(**InvitationOut.model_validate(inv).model_dump(), invite_link=link)


@router.delete("/invitations/{inv_id}", response_model=Message)
def revoke_invitation(inv_id: uuid.UUID, ctx: TenantContext = Depends(require(P.USERS_MANAGE))):
    inv = ctx.db.get(Invitation, inv_id)
    if not inv or inv.organization_id != ctx.org_id:
        raise not_found("Invitation")
    if inv.accepted_at:
        raise bad_request("Invitation was already accepted")
    inv.revoked_at = now()
    ctx.audit("user.invitation_revoked", resource_type="invitation", resource_id=inv.id)
    ctx.db.commit()
    return Message(message="Invitation revoked")


# ---------- Audit & outbox ----------

@router.get("/audit", response_model=Page[AuditOut])
def list_audit(
    action: str | None = None, actor_id: uuid.UUID | None = None, patient_id: uuid.UUID | None = None,
    outcome: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    ctx: TenantContext = Depends(require(P.AUDIT_READ)),
):
    q = select(AuditEvent).where(AuditEvent.organization_id == ctx.org_id)
    if action:
        q = q.where(AuditEvent.action.like(f"{action}%"))
    if actor_id:
        q = q.where(AuditEvent.actor_user_id == actor_id)
    if patient_id:
        q = q.where(AuditEvent.patient_id == patient_id)
    if outcome:
        q = q.where(AuditEvent.outcome == outcome)
    if date_from:
        q = q.where(AuditEvent.created_at >= date_from)
    if date_to:
        q = q.where(AuditEvent.created_at <= date_to)
    total = ctx.db.scalar(select(func.count()).select_from(q.subquery()))
    rows = ctx.db.scalars(q.order_by(AuditEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    names = dict(ctx.db.execute(select(User.id, User.first_name + " " + User.last_name)
                                .where(User.id.in_({r.actor_user_id for r in rows if r.actor_user_id}))).all())
    items = []
    for r in rows:
        a = AuditOut.model_validate(r)
        a.ip_address = str(r.ip_address) if r.ip_address else None
        a.actor_name = names.get(r.actor_user_id)
        items.append(a)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/outbox", response_model=list[OutboxOut])
def outbox(ctx: TenantContext = Depends(require(P.USERS_MANAGE))):
    return ctx.db.scalars(select(OutboundMessage).where(OutboundMessage.organization_id == ctx.org_id)
                          .order_by(OutboundMessage.created_at.desc()).limit(100)).all()


@router.get("/system/status")
def system_status(ctx: TenantContext = Depends(require(P.CLINIC_MANAGE))):
    from app.api.routers.health import dependency_checks

    checks = dependency_checks()
    rev = ctx.db.execute(text("select version_num from alembic_version")).scalar()
    return {
        "checks": checks,
        "environment": settings.environment,
        "migration": rev,
        "ai_provider": settings.ai_provider,
        "ai_phi_allowed": settings.ai_phi_allowed,
        "storage_backend": settings.storage_backend,
        "mfa_enforced": settings.enforce_mfa,
        "adapters": adapter_status(),
        "integrations": {
            "email": "simulated (outbox)", "sms": "simulated", "eprescribing": "simulated",
            "labs": "simulated", "clearinghouse": "simulated", "payments": "simulated", "telephony": "sandbox",
        },
    }
