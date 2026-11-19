"""GET /stream — Server-Sent Events for the active organization (topics + ids only, no PHI)."""

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import TenantContext, get_ctx
from app.services.realtime import broadcaster

router = APIRouter(tags=["live"])


@router.get("/stream")
async def stream(request: Request, ctx: TenantContext = Depends(get_ctx)):
    org = str(ctx.org_id)
    ctx.db.close()  # don't hold a pooled DB connection for the life of the stream

    async def gen():
        q = broadcaster.subscribe(org)
        try:
            yield "retry: 3000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"event: {msg['topic']}\ndata: {json.dumps(msg.get('ids', {}))}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            broadcaster.unsubscribe(org, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
