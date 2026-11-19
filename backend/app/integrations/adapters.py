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


class EligibilityGateway(Protocol):
    """X12 270/271 eligibility inquiry for one member and date of service."""

    name: str

    def inquire(self, *, payer_name: str, member_id: str, date_of_service, subscriber_name: str | None) -> dict: ...


class SimulatedEligibility:
    """Deterministic payer simulator (labeled `simulated` everywhere). It deliberately ignores the *stored* end date:
    only the payer response decides coverage. Member IDs ending in 0 → inactive; 9 → active but the plan ends at the end
    of the date-of-service month (renewal pending); 8 → payer unavailable (error); anything else → active."""

    name = "simulated"

    def inquire(self, *, payer_name: str, member_id: str, date_of_service, subscriber_name: str | None) -> dict:
        import calendar
        from datetime import date

        trace = "SIM-" + hashlib.sha256(f"{member_id}{date_of_service}".encode()).hexdigest()[:10].upper()
        last = member_id.strip()[-1:] if member_id else ""
        if last == "8":
            return {"result": "error", "message": "Payer system unavailable (simulated AAA*42)", "trace": trace}
        if last == "0":
            return {"result": "inactive", "message": "Coverage not active on date of service (simulated)", "trace": trace,
                    "coverage_end": date(date_of_service.year, 1, 1).replace(year=date_of_service.year - 1, month=12, day=31)}
        end = None
        if last == "9":
            end = date(date_of_service.year, date_of_service.month, calendar.monthrange(date_of_service.year, date_of_service.month)[1])
        return {"result": "active", "message": "Active coverage (simulated)", "trace": trace, "coverage_start": date(date_of_service.year, 1, 1),
                "coverage_end": end, "plan": f"{payer_name} (simulated benefits)", "copay_cents": 2500}


class ImagingArchive(Protocol):
    """External PACS/VNA over DICOMweb (QIDO-RS/WADO-RS) + a zero-footprint viewer. Undeclared never stores pixels."""

    name: str

    def register_order(self, *, accession: int, modality: str, patient_mrn: str) -> str | None: ...
    def viewer_url(self, *, study_instance_uid: str | None, accession: int) -> str | None: ...


class SimulatedArchive:
    """No PACS connected: generates a synthetic Study Instance UID for workflow testing; no images or viewer exist."""

    name = "simulated"

    def register_order(self, *, accession: int, modality: str, patient_mrn: str) -> str | None:
        return f"2.25.{int(hashlib.sha256(f'{accession}{patient_mrn}'.encode()).hexdigest()[:24], 16)}"

    def viewer_url(self, *, study_instance_uid: str | None, accession: int) -> str | None:
        return None


class OutboxGateway:
    name = "outbox"

    def send(self, db: Session, *, channel: str, to: str, subject: str, body: str, org_id: uuid.UUID | None) -> None:
        from app.models import OutboundMessage

        db.add(OutboundMessage(organization_id=org_id, channel=channel, to_address=to, subject=subject, body=body, created_at=now()))


_REGISTRY = {
    "order_transmitter": {"simulated": SimulatedOrderTransmitter},
    "clearinghouse": {"simulated": SimulatedClearinghouse},
    "message_gateway": {"outbox": OutboxGateway},
    "eligibility": {"simulated": SimulatedEligibility},
    "imaging_archive": {"simulated": SimulatedArchive},
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


def eligibility_gateway() -> EligibilityGateway:
    return _get("eligibility", settings.eligibility_adapter)


def imaging_archive() -> ImagingArchive:
    return _get("imaging_archive", "simulated")


def status() -> dict:
    return {"order_transmitter": settings.order_transmitter_adapter, "clearinghouse": settings.clearinghouse_adapter,
            "message_gateway": settings.message_gateway_adapter, "eligibility": settings.eligibility_adapter}
