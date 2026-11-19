import uuid

from sqlalchemy.orm import Session

from app.core.security import now
from app.models import Notification


def notify(db: Session, org_id: uuid.UUID, user_id: uuid.UUID, kind: str, title: str, body: str | None = None,
           link: str | None = None) -> None:
    """In-app notification. Keep PHI minimal: titles may name the patient (shown only to authorized staff)."""
    db.add(Notification(organization_id=org_id, user_id=user_id, kind=kind, title=title, body=body, link=link,
                        created_at=now()))
