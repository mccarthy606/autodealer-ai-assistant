"""WhatsApp webhook adapter - supports Twilio-like and Meta-like payloads."""

import hashlib
import hmac
import logging
from typing import Any, Optional

from fastapi import Header, HTTPException, Request

logger = logging.getLogger(__name__)


def extract_whatsapp_message(raw: dict) -> Optional[tuple[str, str]]:
    """
    Extract (user_phone, message_text) from webhook payload.
    Supports Twilio-style and Meta (WhatsApp Business API) style.
    Returns None if unparseable.
    """
    # Meta / WhatsApp Business API
    if "entry" in raw:
        try:
            for entry in raw.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value:
                        for msg in value["messages"]:
                            phone = msg.get("from", "")
                            text = ""
                            if msg.get("type") == "text":
                                text = msg.get("text", {}).get("body", "")
                            elif msg.get("type") == "button":
                                text = msg.get("button", {}).get("text", "")
                            if phone:
                                return (phone, text.strip())
        except (KeyError, TypeError):
            pass

    # Twilio-style
    if "From" in raw or "Body" in raw:
        phone = raw.get("From", raw.get("From", ""))
        body = raw.get("Body", raw.get("body", ""))
        if isinstance(phone, str) and phone:
            return (phone, str(body).strip())

    # Generic fallback
    if "user_phone" in raw and "message_text" in raw:
        return (str(raw["user_phone"]), str(raw.get("message_text", "")).strip())

    return None


def verify_webhook_signature(
    payload: bytes,
    signature_header: Optional[str],
    secret: str,
) -> bool:
    """Verify webhook signature if secret is set."""
    if not secret or not signature_header:
        return True
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature_header)


async def get_raw_body(request: Request) -> bytes:
    """Read raw body for signature verification."""
    return await request.body()
