"""Owner-managed public demo AI (DEMO_MODE deployments).

The platform owner (a real Super Admin — never a demo account) enables a persistent AI provider for the synthetic-data
demonstration: `ai_provider_settings` row with scope="demo". Its key is either the platform key or a dedicated demo
project key (recommended), encrypted with CREDENTIALS_ENCRYPTION_KEY. Demo visitors use it server-side only: it is never
returned, hinted or logged. Limits (app/ai/usage.py) are enforced per visitor session and globally.
"""

from __future__ import annotations

import copy
import time

from app.core.config import settings

AGENT_KEYS = ["insurance_guardian", "doctor_assistant", "medical_scribe", "document_intelligence", "pharmacy_watchdog", "discharge_coordination",
              "hospital_operations", "claims_review", "patient_communication", "staff_scheduling", "voice_concierge"]

DEFAULT_POLICY: dict = {
    "enabled": False,               # off until the owner configures a key and turns it on
    "key_source": "dedicated",      # dedicated (separate demo project key, recommended) | platform
    "text_model": "gpt-4.1-mini", "vision_model": "gpt-4.1-mini", "transcription_model": "", "realtime_model": "",
    "allowed_models": ["gpt-4.1-mini"],
    "allowed_agents": list(AGENT_KEYS),
    "limits": {"visitor_daily_requests": 25, "global_daily_requests": 200, "monthly_budget_usd": 10.0,
               "visitor_concurrency": 2, "global_concurrency": 6,
               "realtime_enabled": False, "realtime_max_seconds": 120, "realtime_daily_sessions": 20},
}

_CACHE: dict = {"at": 0.0, "value": None}
TTL = 15.0


def merged_policy(raw: dict | None) -> dict:
    p = copy.deepcopy(DEFAULT_POLICY)
    raw = raw or {}
    for k, v in raw.items():
        if k == "limits" and isinstance(v, dict):
            p["limits"].update({lk: lv for lk, lv in v.items() if lk in p["limits"]})
        elif k in p:
            p[k] = v
    return p


def _load_row():
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models import AIProviderSettings

    db = SessionLocal()
    try:
        return db.scalar(select(AIProviderSettings).where(AIProviderSettings.scope == "demo"))
    finally:
        db.close()


def invalidate() -> None:
    _CACHE["value"] = None


def load():
    """(policy, EffectiveAI | None). EffectiveAI is None when the owner demo provider is off or unusable."""
    now = time.monotonic()
    if _CACHE["value"] is None or now - _CACHE["at"] > TTL:
        _CACHE["value"], _CACHE["at"] = _build(), now
    return _CACHE["value"]


def _build():
    from app.ai.config import EffectiveAI, platform_effective
    from app.core.crypto import decrypt

    try:
        row = _load_row()
    except Exception:  # noqa: BLE001 — table missing during migrations
        return merged_policy(None), None
    policy = merged_policy(row.policy if row else None)
    if not row or not policy["enabled"] or settings.demo_ai_disabled:
        return policy, None
    key = None
    if policy["key_source"] == "platform":
        plat = platform_effective()
        key = plat.api_key if plat.provider == "openai" else None
    elif row.api_key_encrypted:
        try:
            key = decrypt(row.api_key_encrypted)
        except ValueError:
            key = None
    if not key or not policy["text_model"]:
        return policy, None
    eff = EffectiveAI(provider="openai", api_key=key, key_hint=None, source="owner-demo", text_model=policy["text_model"],
                      vision_model=policy["vision_model"] or policy["text_model"], transcription_model=policy["transcription_model"] or "",
                      realtime_model=(policy["realtime_model"] or "") if policy["limits"]["realtime_enabled"] else "",
                      allowed_agents=list(policy["allowed_agents"]), limits=dict(policy["limits"]),
                      allowed_models=sorted({*policy["allowed_models"], policy["text_model"], policy["vision_model"] or "",
                                             policy["transcription_model"] or "", policy["realtime_model"] or ""} - {""}))
    return policy, eff
