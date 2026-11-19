"""Discharge coordination (Milestone B5). `readiness()` returns None when the stay has no discharge plan."""

from sqlalchemy.orm import Session

from app.models import InpatientStay


def readiness(db: Session, stay: InpatientStay) -> dict | None:
    return None
