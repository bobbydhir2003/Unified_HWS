"""Built-in outbox handlers. Imported by the dispatcher before processing events."""

from sqlalchemy.orm import Session

from app.engine.events import handler
from app.models import DomainEvent


@handler("workflows", "*")
def template_workflows(db: Session, ev: DomainEvent) -> None:
    from app.services.automation import run_workflows

    run_workflows(db, ev.organization_id, ev.event_type, dict(ev.payload or {}))
import app.agents.tools  # noqa: E402,F401  (registers agent proposal executors)
import app.services.discharge  # noqa: E402,F401  (registers discharge_coordinator handler)
import app.services.ed  # noqa: E402,F401  (registers ed_boarding_release handler)
import app.services.inventory  # noqa: E402,F401  (registers inventory.removal approval executor)
import app.services.revenue  # noqa: E402,F401  (registers facility_charges handler)
