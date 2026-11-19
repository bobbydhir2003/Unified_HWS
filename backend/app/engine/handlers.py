"""Built-in outbox handlers. Imported by the dispatcher before processing events."""

from sqlalchemy.orm import Session

from app.engine.events import handler
from app.models import DomainEvent


@handler("workflows", "*")
def template_workflows(db: Session, ev: DomainEvent) -> None:
    from app.services.automation import run_workflows

    run_workflows(db, ev.organization_id, ev.event_type, dict(ev.payload or {}))
