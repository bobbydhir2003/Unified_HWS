"""Data-handling policy for AI calls."""

import uuid

from sqlalchemy.orm import Session

from app.core.config import settings


def contains_phi(db: Session, org_id: uuid.UUID) -> bool:
    """True unless the organization is flagged synthetic (demo/test data) and synthetic external AI is allowed.
    Real organizations are always treated as PHI → blocked from external AI unless AI_PHI_ALLOWED (BAA required)."""
    from app.models import Organization

    org = db.get(Organization, org_id)
    synthetic = bool(org and (org.settings or {}).get("synthetic_data"))
    return not (synthetic and settings.ai_allow_synthetic_external)


def provider_label() -> dict:
    """What the UI should say about the active AI path. Never includes secrets."""
    from app.ai.openai_provider import available

    configured = settings.ai_provider
    if configured == "openai" and not available():
        return {"configured": "openai", "active": "simulated", "live": False,
                "note": "OpenAI selected but OPENAI_API_KEY / AI_TEXT_MODEL not set — using the rule-based simulation."}
    live = configured in ("openai", "anthropic")
    return {"configured": configured, "active": configured, "live": live,
            "note": "Live external AI provider." if live else "Rule-based simulation (no external AI)."}
