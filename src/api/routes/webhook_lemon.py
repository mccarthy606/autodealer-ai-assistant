"""Lemon Squeezy webhook handler with signature verification."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.config import settings

router = APIRouter(prefix="/webhooks/lemon-squeezy", tags=["webhooks-billing"])
logger = logging.getLogger(__name__)


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature from X-Signature header."""
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("")
async def lemon_squeezy_webhook(request: Request):
    """Handle incoming Lemon Squeezy webhook events."""
    secret = settings.lemon_squeezy_webhook_secret
    if not secret:
        logger.warning("LEMON_SQUEEZY_WEBHOOK_SECRET not configured, rejecting webhook")
        return JSONResponse({"error": "not configured"}, status_code=500)

    raw_body = await request.body()
    signature = request.headers.get("x-signature", "")

    if not signature or not _verify_signature(raw_body, signature, secret):
        logger.warning("Lemon Squeezy webhook: invalid signature")
        return JSONResponse({"error": "invalid signature"}, status_code=401)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    event_name = payload.get("meta", {}).get("event_name", "unknown")
    logger.info("Lemon Squeezy event: %s", event_name)

    # Placeholder: actual event handling comes in Phase 8 (BILL-02)
    return {"status": "ok", "event": event_name}
