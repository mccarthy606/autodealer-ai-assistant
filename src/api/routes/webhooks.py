"""Legacy WhatsApp webhook route (Twilio-compatible)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.config import settings
from src.services.conversation_engine import process_message
from src.webhooks.whatsapp import extract_whatsapp_message

router = APIRouter(prefix="/webhooks/whatsapp", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("")
async def whatsapp_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Receive WhatsApp messages (Twilio format).
    For Meta Cloud API format, use /webhooks/whatsapp_cloud instead.
    """
    raw_body = await request.body()
    content_type = request.headers.get("content-type", "") or ""

    if "application/json" in content_type and raw_body:
        import json
        try:
            payload = json.loads(raw_body)
        except Exception:
            payload = {}
    elif "application/x-www-form-urlencoded" in content_type and raw_body:
        from urllib.parse import parse_qs
        decoded = raw_body.decode("utf-8")
        params = parse_qs(decoded)
        payload = {k: (v[0] if v else "") for k, v in params.items()}
    else:
        payload = {}

    extracted = extract_whatsapp_message(payload)
    if not extracted:
        return {"error": "unparseable", "status": 400}

    user_phone, message_text = extracted
    if not message_text:
        return {"text": "", "status": "ok"}

    result = await process_message(
        session=session,
        dealership_id=settings.default_dealership_id,
        phone=user_phone,
        text=message_text,
        channel="whatsapp",
    )

    return {
        "text": result.text,
        "to": user_phone,
        "status": "ok",
    }
