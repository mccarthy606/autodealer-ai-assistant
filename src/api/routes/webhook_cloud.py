"""WhatsApp Business Cloud API webhook routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.rate_limit import check_rate_limit
from src.config import settings
from src.adapters.whatsapp_cloud import WhatsAppCloudAdapter, parse_incoming_message, verify_webhook
from src.services.conversation_engine import process_message

router = APIRouter(prefix="/webhooks/whatsapp_cloud", tags=["webhooks-whatsapp"])
logger = logging.getLogger(__name__)


@router.get("")
async def verify_whatsapp_webhook(request: Request):
    """Meta webhook verification (GET)."""
    params = dict(request.query_params)
    token = settings.whatsapp_verify_token
    if not token:
        return PlainTextResponse("No verify token configured", status_code=403)

    challenge = verify_webhook(params, token)
    if challenge:
        return PlainTextResponse(challenge)
    return PlainTextResponse("Verification failed", status_code=403)


@router.post("")
async def receive_whatsapp_message(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Receive incoming WhatsApp Cloud messages."""
    try:
        payload = await request.json()
    except Exception:
        return {"status": "error", "message": "invalid payload"}

    parsed = parse_incoming_message(payload)
    if not parsed:
        return {"status": "ok", "message": "no actionable message"}

    phone, text = parsed
    if not text.strip():
        return {"status": "ok"}

    # Rate limit: 20 requests per 60s per phone (per D-07)
    allowed, retry_after = await check_rate_limit(
        key=phone, limit=20, window_seconds=60, prefix="rate:whatsapp"
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
        dealership_id=settings.default_dealership_id,
        phone=phone,
        text=text,
        channel="whatsapp",
    )

    # Send reply via WhatsApp Cloud
    if result.text:
        adapter = WhatsAppCloudAdapter()
        await adapter.send_text(phone, result.text)

        # Send photos if any
        if result.photo_urls:
            await adapter.send_images(phone, result.photo_urls)

    return {"status": "ok"}
