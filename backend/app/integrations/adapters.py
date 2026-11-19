"""External integration adapters.

Business code calls these interfaces; the registry picks an implementation from settings. Only simulated
implementations ship today — each returns records marked `simulated: True`. Real adapters (Surescripts, lab interface
engines, clearinghouses, email/SMS vendors) must be certified/contracted (BAA) and validated before being enabled.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import now


class OrderTransmitter(Protocol):
    """Sends a signed order to its destination (pharmacy via eRx, lab/imaging interface, referral recipient)."""

    name: str

    def transmit(self, order_type: str, details: dict, order_id: uuid.UUID) -> dict: ...


class Clearinghouse(Protocol):
    """Submits an 837P claim; returns the clearinghouse tracking reference."""

    name: str

    def submit(self, claim_id: uuid.UUID, idempotency_key: str) -> str: ...


class MessageGateway(Protocol):
    """Delivers email/SMS. The simulated gateway writes to the outbox table instead of sending."""

    name: str

    def send(self, db: Session, *, channel: str, to: str, subject: str, body: str, org_id: uuid.UUID | None) -> None: ...


class SimulatedOrderTransmitter:
    name = "simulated"
    CHANNELS = {"medication": "eRx (simulated)", "lab": "Lab interface (simulated)", "imaging": "Imaging order (simulated)",
                "referral": "Referral fax (simulated)"}

    def transmit(self, order_type: str, details: dict, order_id: uuid.UUID) -> dict:
        return {"channel": self.CHANNELS[order_type], "reference": f"SIM-{order_type[:3].upper()}-{uuid.uuid4().hex[:8].upper()}",
                "simulated": True, "destination": details.get("pharmacy") or details.get("specialist_org") or "Default partner (simulated)",
                "sent_at": now().isoformat()}


class SimulatedClearinghouse:
    name = "simulated"

    def submit(self, claim_id: uuid.UUID, idempotency_key: str) -> str:
        return f"SIM-837-{hashlib.sha1(f'{claim_id}{idempotency_key}'.encode()).hexdigest()[:10].upper()}"


class OutboxGateway:
    name = "outbox"

    def send(self, db: Session, *, channel: str, to: str, subject: str, body: str, org_id: uuid.UUID | None) -> None:
        from app.models import OutboundMessage

        db.add(OutboundMessage(organization_id=org_id, channel=channel, to_address=to, subject=subject, body=body, created_at=now()))


_REGISTRY = {
    "order_transmitter": {"simulated": SimulatedOrderTransmitter},
    "clearinghouse": {"simulated": SimulatedClearinghouse},
    "message_gateway": {"outbox": OutboxGateway},
}


def _get(kind: str, choice: str):
    impls = _REGISTRY[kind]
    if choice not in impls:
        raise RuntimeError(f"No '{choice}' adapter registered for {kind}; available: {', '.join(impls)}")
    return impls[choice]()


def order_transmitter() -> OrderTransmitter:
    return _get("order_transmitter", settings.order_transmitter_adapter)


def clearinghouse() -> Clearinghouse:
    return _get("clearinghouse", settings.clearinghouse_adapter)


def message_gateway() -> MessageGateway:
    return _get("message_gateway", settings.message_gateway_adapter)


def status() -> dict:
    return {"order_transmitter": settings.order_transmitter_adapter, "clearinghouse": settings.clearinghouse_adapter,
            "message_gateway": settings.message_gateway_adapter}
