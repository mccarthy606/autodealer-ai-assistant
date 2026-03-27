"""Admin conversation routes -- viewer, send, takeover, return-bot."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.routes.admin_common import auth_check, templates
from src.config import settings
from src.db.models import (
    Conversation, Message, MessageDirectionEnum,
)
from src.services.handoff_rules import get_reason_label

router = APIRouter(prefix="/admin/ui", tags=["admin-ui"])
logger = logging.getLogger(__name__)


@router.get("/conversations", response_class=HTMLResponse)
async def conversations_page(request: Request, db: AsyncSession = Depends(get_db)):
    redir = await auth_check(request)
    if redir:
        return redir

    did = settings.default_dealership_id
    stmt = (
        select(Conversation)
        .where(Conversation.dealership_id == did)
        .order_by(Conversation.last_message_at.desc())
        .limit(200)
    )
    result = await db.execute(stmt)
    conversations = result.scalars().all()

    # Get last message for each conversation
    conv_data = []
    for c in conversations:
        last_msg_stmt = select(Message).where(
            Message.conversation_id == c.id
        ).order_by(Message.created_at.desc()).limit(1)
        msg_r = await db.execute(last_msg_stmt)
        last_msg = msg_r.scalar_one_or_none()
        conv_data.append({
            "conv": c,
            "last_msg": last_msg.text[:80] if last_msg and last_msg.text else "",
            "last_dir": last_msg.direction.value if last_msg else "",
        })

    return templates.TemplateResponse("admin/conversations.html", {
        "request": request,
        "conv_data": conv_data,
    })


@router.get("/conversations/{conv_id}", response_class=HTMLResponse)
async def conversation_detail(conv_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    redir = await auth_check(request)
    if redir:
        return redir

    stmt = select(Conversation).where(
        Conversation.id == conv_id,
        Conversation.dealership_id == settings.default_dealership_id,
    )
    r = await db.execute(stmt)
    conv = r.scalar_one_or_none()
    if not conv:
        return RedirectResponse(url="/admin/ui/conversations", status_code=302)

    msg_stmt = select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at)
    msg_r = await db.execute(msg_stmt)
    messages = msg_r.scalars().all()

    reason_label = get_reason_label(conv.handoff_reason, conv.state.get("language", "es") if conv.state else "es")

    return templates.TemplateResponse("admin/conversation_detail.html", {
        "request": request,
        "conv": conv,
        "messages": messages,
        "reason_label": reason_label,
    })


@router.post("/conversations/{conv_id}/send")
async def conversation_send(conv_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Manager sends a message from the inbox."""
    redir = await auth_check(request)
    if redir:
        return redir

    form = await request.form()
    text = (form.get("text") or "").strip()
    if not text:
        return RedirectResponse(url=f"/admin/ui/conversations/{conv_id}", status_code=302)

    stmt = select(Conversation).where(Conversation.id == conv_id)
    r = await db.execute(stmt)
    conv = r.scalar_one_or_none()
    if not conv:
        return RedirectResponse(url="/admin/ui/conversations", status_code=302)

    msg = Message(
        conversation_id=conv.id,
        direction=MessageDirectionEnum.outbound,
        text=text,
        channel=conv.channel,
    )
    db.add(msg)
    conv.last_message_at = datetime.now(UTC)

    # TODO: Send via channel adapter (WhatsApp/ML) if configured
    # For now: saved to DB, visible in conversation

    return RedirectResponse(url=f"/admin/ui/conversations/{conv_id}", status_code=302)


@router.post("/conversations/{conv_id}/takeover")
async def conversation_takeover(conv_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Switch to manager mode."""
    redir = await auth_check(request)
    if redir:
        return redir

    stmt = select(Conversation).where(Conversation.id == conv_id)
    r = await db.execute(stmt)
    conv = r.scalar_one_or_none()
    if conv:
        conv.mode = "manager"
        conv.handoff_reason = "manual_takeover"
        conv.last_handoff_at = datetime.now(UTC)
    return RedirectResponse(url=f"/admin/ui/conversations/{conv_id}", status_code=302)


@router.post("/conversations/{conv_id}/return-bot")
async def conversation_return_bot(conv_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Return to bot mode."""
    redir = await auth_check(request)
    if redir:
        return redir

    stmt = select(Conversation).where(Conversation.id == conv_id)
    r = await db.execute(stmt)
    conv = r.scalar_one_or_none()
    if conv:
        conv.mode = "bot"
        conv.handoff_reason = None
        state = dict(conv.state or {})
        state["stage"] = "BROWSING"
        state["unhelpful_count"] = 0
        conv.state = state
    return RedirectResponse(url=f"/admin/ui/conversations/{conv_id}", status_code=302)
