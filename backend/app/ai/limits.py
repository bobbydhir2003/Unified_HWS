"""Staff AI admission control — enforced BEFORE a live model call, reconciled after it.

Every live call made on behalf of a person (agent runs, HMS Assist turns, chart questions, scribe/document pipelines)
passes `admit()`:
  * per-user daily requests, per-agent (per organization) daily requests, per-organization daily requests — atomic
    durable counters (app/ai/usage.py, Postgres);
  * per-organization MONTHLY estimated-spend budget — a conservative amount is *reserved* before the call
    (usage.reserve_cost, atomic, never exceeds the budget) and reconciled with the measured estimate afterwards;
  * per-user concurrency slot (Redis; fails CLOSED in staging/production).
If any check fails, everything already taken is given back and LimitError explains which limit applies.
Rule-based (simulated) answers cost nothing and are not counted. Costs are estimates from a price table.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.ai import usage
from app.core.config import settings


class LimitError(Exception):
    """A staff AI limit is reached (shown to the user; HTTP 429)."""


def _keys(org_id, user_id, agent_key) -> dict:
    d, m = usage.day_key(), usage.month_key()
    k = {"org_day": f"staff:org:{org_id}:day:{d}", "agent_day": f"staff:agent:{org_id}:{agent_key}:day:{d}",
         "org_month": f"staff:org:{org_id}:month:{m}"}
    if user_id:
        k["user_day"] = f"staff:user:{user_id}:day:{d}"
        k["user_slot"] = f"staff:user:{user_id}"
    return k


@dataclass
class Admission:
    keys: dict
    reserved: float
    taken: list[str] = field(default_factory=list)
    slot: str | None = None
    settled: bool = False

    def settle(self, cost_usd: float | None, input_tokens: int | None = None, output_tokens: int | None = None) -> None:
        """Replace the reservation with the measured estimate (unknown cost keeps the conservative reservation)."""
        if self.settled:
            return
        self.settled = True
        delta = (cost_usd - self.reserved) if cost_usd is not None else 0.0
        usage.adjust(self.keys["org_month"], cost_delta=delta, input_tokens=input_tokens or 0, output_tokens=output_tokens or 0)

    def release(self) -> None:
        if self.slot:
            usage.release_slot(self.slot)
            self.slot = None

    def refund(self) -> None:
        """The call never happened (e.g. blocked by policy before sending): give everything back."""
        for k in self.taken:
            usage.give_back_request(k)
        if not self.settled:
            usage.adjust(self.keys["org_month"], cost_delta=-self.reserved)
            self.settled = True
        self.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
        return False


def admit(org_id: uuid.UUID, user_id: uuid.UUID | None, agent_key: str, *, reserve_usd: float) -> Admission:
    k = _keys(org_id, user_id, agent_key)
    taken: list[str] = []

    def undo():
        for key in taken:
            usage.give_back_request(key)

    checks = [("user_day", settings.ai_user_daily_requests, "your daily AI request limit"),
              ("agent_day", settings.ai_agent_daily_requests, "this assistant's daily limit for your organization"),
              ("org_day", settings.ai_org_daily_requests, "your organization's daily AI request limit")]
    for name, limit, label in checks:
        if name not in k:
            continue
        if not usage.take_request(k[name], limit):
            undo()
            raise LimitError(f"AI request not sent: {label} ({limit}) is reached. It resets at midnight UTC.")
        taken.append(k[name])
    reserve = max(0.0, float(reserve_usd))
    if not usage.reserve_cost(k["org_month"], reserve, settings.ai_org_monthly_budget_usd):
        undo()
        raise LimitError(f"AI request not sent: your organization's estimated monthly AI budget "
                         f"(${settings.ai_org_monthly_budget_usd:.2f}) would be exceeded.")
    adm = Admission(keys=k, reserved=reserve, taken=taken)
    if "user_slot" in k:
        try:
            ok = usage.acquire_slot(k["user_slot"], settings.ai_user_concurrency)
        except usage.LimitError as e:
            adm.refund()
            raise LimitError(str(e)) from None
        if not ok:
            adm.refund()
            raise LimitError(f"You already have {settings.ai_user_concurrency} AI requests running. Wait for one to finish.")
        adm.slot = k["user_slot"]
    return adm


def org_month_key(org_id) -> str:
    return f"staff:org:{org_id}:month:{usage.month_key()}"
