"""Revenue monitors: services needing prior authorization, authorizations expiring before the service, claims on hold."""

import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.core.security import now
from app.engine.cases import Finding
from app.engine.monitors import Monitor, register
from app.models import Claim, ImagingStudy, Order, Patient, PriorAuthorization
from app.services.revenue import approved_auth, ensure_pa_for_order, pa_codes


class PriorAuthRequired(Monitor):
    key = "billing.prior_auth_required"
    name = "Prior authorization needed"
    description = "A signed order for a service that the payer requires prior authorization for has no approved authorization yet. Drafts the request with its checklist."
    category = "billing"
    default_config = {"assign_role": "insurance_specialist"}
    config_help = {"assign_role": "Role that works prior authorizations"}

    def evaluate(self, db, org_id, cfg):
        codes = pa_codes(db, org_id)
        orders = db.scalars(select(Order).where(Order.organization_id == org_id, Order.status.in_(("signed", "transmitted", "in_progress")),
                                                Order.code.in_(list(codes)))).all()
        out = []
        for o in orders:
            if approved_auth(db, o.patient_id, o.code, date.today()):
                continue
            pa = db.scalar(select(PriorAuthorization).where(PriorAuthorization.order_id == o.id,
                                                            PriorAuthorization.status.not_in(("expired", "cancelled"))))
            status = pa.status if pa else "none"
            out.append(Finding(dedupe_key=f"pa.req:{o.id}", kind=self.key, category="billing",
                               severity="high" if o.priority in ("stat", "urgent") or status == "denied" else "medium",
                               title=f"Prior auth {'denied' if status == 'denied' else 'pending' if status in ('submitted', 'pended') else 'needed'} — {o.title}, {db.get(Patient, o.patient_id).full_name}",
                               patient_id=o.patient_id, subject_type="order", subject_id=str(o.id), assign_role=cfg["assign_role"],
                               link="/revenue?tab=prior-auth", sla_minutes=240 if o.priority != "routine" else 1440,
                               evidence={"service": o.title, "code": o.code, "priority": o.priority, "authorization_status": status},
                               data={"order_id": str(o.id)}))
        return out

    def on_open(self, db, case, f, cfg):
        o = db.get(Order, uuid.UUID(f.data["order_id"]))
        if o:
            ensure_pa_for_order(db, o)

    def clear(self, db, case, cfg):
        o = db.get(Order, uuid.UUID(case.subject_id))
        if o and o.status == "cancelled":
            return "no_longer_applicable", "Order cancelled."
        pa = db.scalar(select(PriorAuthorization).where(PriorAuthorization.order_id == uuid.UUID(case.subject_id), PriorAuthorization.status == "approved"))
        return ("verified_active", f"Authorized ({pa.auth_number}, valid to {pa.valid_to:%b %d}).") if pa else ("no_longer_applicable", "Order no longer active.")


class PriorAuthExpiring(Monitor):
    key = "billing.prior_auth_expiring"
    name = "Prior authorization expiring before service"
    description = "An approved authorization expires within the window and the service hasn't been performed."
    category = "billing"
    default_config = {"window_days": 7, "assign_role": "insurance_specialist"}
    config_help = {"window_days": "Warn this many days before expiry", "assign_role": "Owner role"}

    def evaluate(self, db, org_id, cfg):
        out = []
        for pa in db.scalars(select(PriorAuthorization).where(PriorAuthorization.organization_id == org_id, PriorAuthorization.status == "approved",
                                                              PriorAuthorization.valid_to <= date.today() + timedelta(days=int(cfg["window_days"])))):
            performed = pa.order_id and db.scalar(select(ImagingStudy.id).where(ImagingStudy.order_id == pa.order_id, ImagingStudy.status.in_(("completed", "preliminary", "final"))))
            if performed:
                continue
            days = (pa.valid_to - date.today()).days
            out.append(Finding(dedupe_key=f"pa.exp:{pa.id}", kind=self.key, category="billing", severity="high" if days <= 2 else "medium",
                               title=f"Authorization {pa.auth_number} for {pa.service_description} {'expired' if days < 0 else f'expires in {days} d'} — {pa.patient.full_name}",
                               patient_id=pa.patient_id, subject_type="prior_auth", subject_id=str(pa.id), assign_role=cfg["assign_role"],
                               link="/revenue?tab=prior-auth", sla_minutes=max(days, 1) * 720, evidence={"valid_to": pa.valid_to.isoformat(), "days_left": days}))
        return out

    def clear(self, db, case, cfg):
        return "condition_cleared", "Service performed or authorization extended/replaced."


class ClaimsOnHold(Monitor):
    key = "billing.claims_on_hold"
    name = "Claims on hold"
    description = "Claims stuck in draft (scrub errors / review blockers) or denied without an appeal beyond the target."
    category = "billing"
    default_config = {"days": 3, "assign_role": "billing"}
    config_help = {"days": "Days before a held claim becomes a case", "assign_role": "Owner role"}

    def evaluate(self, db, org_id, cfg):
        cutoff = now() - timedelta(days=int(cfg["days"]))
        out = []
        for c in db.scalars(select(Claim).where(Claim.organization_id == org_id, Claim.updated_at < cutoff,
                                                ((Claim.status == "draft") | ((Claim.status == "denied") & Claim.appeal_submitted_at.is_(None))))):
            out.append(Finding(dedupe_key=f"claim.hold:{c.id}:{c.status}", kind=self.key, category="billing", severity="medium",
                               title=f"Claim {c.claim_number} {c.status} for {(now() - c.updated_at).days} days — {c.payer_name}", patient_id=c.patient_id,
                               subject_type="claim", subject_id=str(c.id), assign_role=cfg["assign_role"], link=f"/billing?claim={c.id}", sla_minutes=1440,
                               evidence={"status": c.status, "scrub_errors": c.scrub_errors, "denial": c.denial_reason}))
        return out

    def clear(self, db, case, cfg):
        c = db.get(Claim, uuid.UUID(case.subject_id))
        return "verified_active", f"Claim now {c.status if c else 'removed'}."


register(PriorAuthRequired())
register(PriorAuthExpiring())
register(ClaimsOnHold())
