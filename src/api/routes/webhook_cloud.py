"""WhatsApp Business Cloud API webhook routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from src.api.deps import get_db
from src.api.rate_limit import check_rate_limit
from src.config import settings
from src.adapters.whatsapp_cloud import (
    WhatsAppCloudAdapter, parse_incoming_message, verify_webhook, get_dealership_by_wa
)
from src.db.models import Message
from src.services.billing import is_subscription_active
from src.services.conversation_engine import process_message

router = APIRouter(prefix="/webhooks/whatsapp_cloud", tags=["webhooks-whatsapp"])
logger = logging.getLogger(__name__)


@router.get("")
async def verify_whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Meta webhook verification (GET). Routes by phone_number_id if present."""
    params = dict(request.query_params)

    # Try per-dealership verify token first
    phone_number_id = params.get("hub.phone_number_id") or params.get("phone_number_id")
    verify_token = None
    if phone_number_id:
        dealer = await get_dealership_by_wa(db, phone_number_id)
        if dealer and dealer.whatsapp_verify_token:
            verify_token = dealer.whatsapp_verify_token

    # Fallback to global settings token (backward compat / single-tenant)
    if not verify_token:
        verify_token = settings.whatsapp_verify_token

    if not verify_token:
        return PlainTextResponse("No verify token configured", status_code=403)

    challenge = verify_webhook(params, verify_token)
    if challenge:
        return PlainTextResponse(challenge)
    return PlainTextResponse("Verification failed", status_code=403)


@router.post("")
async def receive_whatsapp_message(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Receive incoming WhatsApp Cloud messages — routes by phone_number_id."""
    try:
        payload = await request.json()
    except Exception:
        return {"status": "error", "message": "invalid payload"}

    parsed = parse_incoming_message(payload)
    if not parsed:
        return {"status": "ok", "message": "no actionable message"}

    phone, text, wamid, phone_number_id = parsed   # 4-tuple now
    if not text.strip():
        return {"status": "ok"}

    # Route to correct dealership by phone_number_id (per D-10)
    dealer = None
    if phone_number_id:
        dealer = await get_dealership_by_wa(db, phone_number_id)
    if dealer is None:
        # Unknown phone_number_id — return 200 silently (per D-12, never 4xx to Meta)
        logger.info("No dealership for phone_number_id=%s, ignoring", phone_number_id)
        return {"status": "ok"}

    if not is_subscription_active(dealer):
        logger.info(
            "Subscription inactive for dealership=%d (status=%s), dropping WA message",
            dealer.id,
            dealer.subscription_status,
        )
        return {"status": "ok"}

    dealership_id = dealer.id
    # Prefer dealership's own WABA token; fall back to settings (per D-02)
    wa_token = dealer.whatsapp_access_token or settings.whatsapp_cloud_token

    # Dedup: check if wamid already processed (ENG-04)
    if wamid:
        stmt = select(Message.id).where(Message.wamid == wamid).limit(1)
        existing = await db.execute(stmt)
        if existing.scalar_one_or_none() is not None:
            logger.info("Duplicate wamid=%s, skipping", wamid)
            return {"status": "ok", "message": "duplicate"}

    # Rate limit: per dealership per phone (per D-15)
    allowed, retry_after = await check_rate_limit(
        key=phone, limit=20, window_seconds=60,
        prefix=f"rate:wa:{dealership_id}",
    )
    if not allowed:
        return JSONResponse(
            {"error": "rate limited"},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )

    # Process through engine
    result = await process_message(
        session=db,
        dealership_id=dealership_id,
        phone=phone,
        text=text,
        channel="whatsapp",
        wamid=wamid,
    )

    # Send reply using dealership-specific credentials (per D-02, D-03)
    if result.text:
        adapter = WhatsAppCloudAdapter(
            phone_number_id=phone_number_id,
            token=wa_token,
        )
        await adapter.send_text(phone, result.text)
        if result.photo_urls:
            await adapter.send_images(phone, result.photo_urls)

    return {"status": "ok"}
