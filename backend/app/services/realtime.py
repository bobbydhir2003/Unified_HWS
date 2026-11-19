"""Live updates over Server-Sent Events, fanned out from PostgreSQL LISTEN/NOTIFY.

`publish()` queues a NOTIFY inside the caller's transaction, so clients only hear about committed changes.
Payloads carry a topic plus identifiers — never PHI; browsers refetch through normal, permission-checked APIs.
One LISTEN connection per API process feeds every subscriber in that process.
"""

import asyncio
import json
import logging
import uuid
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

log = logging.getLogger("undeclared.realtime")
CHANNEL = "undeclared_live"


def publish(db: Session, org_id: uuid.UUID, topic: str, **ids) -> None:
    payload = json.dumps({"org": str(org_id), "topic": topic, "ids": {k: str(v) for k, v in ids.items() if v is not None}})
    db.execute(text("SELECT pg_notify(:c, :p)"), {"c": CHANNEL, "p": payload[:7900]})


class Broadcaster:
    def __init__(self) -> None:
        self.subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._task: asyncio.Task | None = None

    def _dsn(self) -> str:
        return settings.database_url.replace("postgresql+psycopg://", "postgresql://")

    async def _run(self) -> None:
        import psycopg

        while True:
            try:
                async with await psycopg.AsyncConnection.connect(self._dsn(), autocommit=True) as conn:
                    await conn.execute(f"LISTEN {CHANNEL}")
                    async for n in conn.notifies():
                        try:
                            msg = json.loads(n.payload)
                        except ValueError:
                            continue
                        for q in list(self.subs.get(msg.get("org", ""), ())):
                            if q.qsize() < 500:
                                q.put_nowait(msg)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.warning("live listener disconnected; retrying")
                await asyncio.sleep(2)

    def subscribe(self, org_id: str) -> asyncio.Queue:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        q: asyncio.Queue = asyncio.Queue()
        self.subs[org_id].add(q)
        return q

    def unsubscribe(self, org_id: str, q: asyncio.Queue) -> None:
        self.subs[org_id].discard(q)


broadcaster = Broadcaster()
