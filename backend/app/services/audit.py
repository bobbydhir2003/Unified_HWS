import ipaddress
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.security import now
from app.models import AuditEvent


def client_ip(request: Request | None) -> str | None:
    """Best-effort client IP. Only trust X-Forwarded-For behind a proxy you control (set at the load balancer)."""
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    raw = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)
    try:
        return str(ipaddress.ip_address(raw)) if raw else None
    except ValueError:
        return None


def record(
    db: Session,
    action: str,
    *,
    org_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: Any = None,
    patient_id: uuid.UUID | None = None,
    outcome: str = "success",
    request: Request | None = None,
    details: dict | None = None,
) -> AuditEvent:
    """Add an audit event to the current transaction. Never put PHI values into `details` — ids and field names only."""
    ev = AuditEvent(
        organization_id=org_id,
        actor_user_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        patient_id=patient_id,
        outcome=outcome,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent", "")[:400] if request else None),
        details=details or {},
        created_at=now(),
    )
    db.add(ev)
    return ev
