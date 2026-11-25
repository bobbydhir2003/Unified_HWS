"""HMS Assist conversations API: department agents with persistent, record-bound conversations.

Employees use these from their workspaces; administrators review conversations under /admin/assist (audited).
All authorization happens server-side on every call (see app/services/assist.py and app/agents/context.py)."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents import runner as R
from app.api.deps import TenantContext, require
from app.core.permissions import P
from app.models import AgentConfig, AssistActionDraft, AssistConversation
from app.services import assist as S

router = APIRouter(tags=["assist"])


def _raise(e: S.AssistError):
    raise HTTPException(e.status, {"code": e.code, "message": str(e)})


@router.get("/assist/agents")
def assist_agents(ctx: TenantContext = Depends(require(P.AI_USE))):
    """The ten agents as THIS user sees them now: enabled, usable, contexts, prompts, capabilities (allowed tools ∩ permissions)."""
    R.ensure_defaults(ctx.db, ctx.org_id)
    ctx.db.commit()
    rows = ctx.db.scalars(select(AgentConfig).where(AgentConfig.organization_id == ctx.org_id)).all()
    return {"feature_enabled": S.feature_enabled(ctx.db, ctx.org_id),
            "agents": [S.agent_card(ctx, R.view(c)) for c in sorted(rows, key=lambda c: R.display_name(c.key))]}


class OpenIn(BaseModel):
    agent_key: str = Field(max_length=40)
    context_type: Literal["workspace", "case", "patient", "stay", "claim", "inventory_item", "message_thread", "scribe_session", "document"] = "workspace"
    context_id: str | None = Field(default=None, max_length=80)
    new: bool = False


@router.post("/assist/conversations")
def open_conversation(body: OpenIn, ctx: TenantContext = Depends(require(P.AI_USE))):
    try:
        c = S.open_conversation(ctx, body.agent_key, body.context_type, body.context_id, new=body.new)
    except S.AssistError as e:
        ctx.db.rollback()
        _raise(e)
    ctx.db.commit()
    return S.conversation_view(ctx, c)


@router.get("/assist/conversations")
def my_conversations(agent_key: str | None = None, context_type: str | None = None, context_id: str | None = None,
                     ctx: TenantContext = Depends(require(P.AI_USE))):
    q = select(AssistConversation).where(AssistConversation.organization_id == ctx.org_id, AssistConversation.user_id == ctx.user.id)
    if agent_key:
        q = q.where(AssistConversation.agent_key == agent_key)
    if context_type:
        q = q.where(AssistConversation.context_type == context_type)
    if context_id:
        q = q.where(AssistConversation.context_id == context_id)
    rows = ctx.db.scalars(q.order_by(AssistConversation.last_message_at.desc()).limit(30)).all()
    return [{"id": str(c.id), "agent_key": c.agent_key, "agent_name": R.display_name(c.agent_key), "context_type": c.context_type,
             "context_label": c.context_label, "status": c.status, "last_message_at": c.last_message_at, "created_at": c.created_at} for c in rows]


@router.get("/assist/conversations/{cid}")
def get_conversation(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.AI_USE))):
    try:
        c = S.get_owned(ctx, cid)
        if c.patient_id:  # restricted charts / revoked access: re-checked on read too
            S._resolve(ctx, c.agent_key, c.context_type, c.context_id)
    except S.AssistError as e:
        _raise(e)
    return S.conversation_view(ctx, c)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/assist/conversations/{cid}/messages")
def send_message(cid: uuid.UUID, body: MessageIn, ctx: TenantContext = Depends(require(P.AI_USE))):
    try:
        c = S.get_owned(ctx, cid)
        S.send(ctx, c, body.text)
    except S.AssistError as e:
        ctx.db.rollback()
        _raise(e)
    ctx.db.commit()
    return S.conversation_view(ctx, c)


@router.post("/assist/conversations/{cid}/close")
def close_conversation(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.AI_USE))):
    try:
        c = S.get_owned(ctx, cid)
    except S.AssistError as e:
        _raise(e)
    c.status = "closed"
    ctx.audit("assist.conversation_closed", resource_type="assist_conversation", resource_id=c.id, patient_id=c.patient_id)
    ctx.db.commit()
    return {"id": str(c.id), "status": c.status}


def _draft(ctx, did) -> AssistActionDraft:
    d = ctx.db.get(AssistActionDraft, did)
    if not d or d.organization_id != ctx.org_id:
        raise HTTPException(404, "Prepared action not found")
    return d


@router.post("/assist/drafts/{did}/confirm")
def confirm(did: uuid.UUID, ctx: TenantContext = Depends(require(P.AI_USE))):
    d = _draft(ctx, did)
    try:
        S.confirm_draft(ctx, d)
    except S.AssistError as e:
        ctx.db.commit() if d.status == "expired" else ctx.db.rollback()
        _raise(e)
    ctx.db.commit()
    return S.conversation_view(ctx, S.get_owned(ctx, d.conversation_id))


@router.post("/assist/drafts/{did}/discard")
def discard(did: uuid.UUID, ctx: TenantContext = Depends(require(P.AI_USE))):
    d = _draft(ctx, did)
    try:
        c = S.get_owned(ctx, d.conversation_id)
    except S.AssistError as e:
        _raise(e)
    if d.status == "draft":
        d.status = "discarded"
        S._add_message(ctx.db, c, "system", f"{d.title}: discarded.", actions=[{"type": "draft", "id": str(d.id)}], mode="system")
    ctx.db.commit()
    return S.conversation_view(ctx, c)


# ---------------------------------------------------------------------------------------------- administration (audited)

@router.get("/admin/assist/conversations")
def admin_conversations(agent_key: str | None = None, limit: int = 100, ctx: TenantContext = Depends(require(P.AI_MANAGE))):
    from app.models import Patient, User

    q = (select(AssistConversation, User.first_name + " " + User.last_name).join(User, User.id == AssistConversation.user_id)
         .outerjoin(Patient, Patient.id == AssistConversation.patient_id)
         .where(AssistConversation.organization_id == ctx.org_id)
         .where((Patient.id.is_(None)) | (Patient.is_restricted.is_(False))))  # restricted charts never listed
    if ctx.facility_ids is not None:
        q = q.where((AssistConversation.facility_id.is_(None)) | (AssistConversation.facility_id.in_(ctx.facility_ids)))
    if agent_key:
        q = q.where(AssistConversation.agent_key == agent_key)
    rows = ctx.db.execute(q.order_by(AssistConversation.last_message_at.desc()).limit(min(limit, 300))).all()
    return [{"id": str(c.id), "agent_key": c.agent_key, "agent_name": R.display_name(c.agent_key), "user": name, "acting_role": c.acting_role,
             "context_type": c.context_type, "context_label": c.context_label, "status": c.status, "created_at": c.created_at,
             "last_message_at": c.last_message_at} for c, name in rows]


@router.get("/admin/assist/conversations/{cid}")
def admin_conversation(cid: uuid.UUID, ctx: TenantContext = Depends(require(P.AI_MANAGE))):
    c = ctx.db.get(AssistConversation, cid)
    if not c or c.organization_id != ctx.org_id or not ctx.facility_allowed(c.facility_id):
        raise HTTPException(404, "Conversation not found")
    if c.patient_id:
        from app.services.patients import get_patient

        get_patient(ctx, c.patient_id)  # restricted charts: break-the-glass rules apply to reviewers too
    ctx.audit("assist.conversation_reviewed", resource_type="assist_conversation", resource_id=c.id, patient_id=c.patient_id,
              details={"agent": c.agent_key, "owner": str(c.user_id)})
    ctx.db.commit()
    return S.conversation_view(ctx, c, admin=True)
