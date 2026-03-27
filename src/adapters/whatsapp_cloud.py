"""WhatsApp Business Cloud API adapter (Meta)."""

import logging
from typing import Any, Optional

import httpx

from src.config import settings
from src.adapters.base import ChannelAdapter

logger = logging.getLogger(__name__)

GRAPH_API_URL = "https://graph.facebook.com/v18.0"


class WhatsAppCloudAdapter(ChannelAdapter):
    """WhatsApp Cloud API adapter. Works in mock mode if tokens are not set."""

    def __init__(self):
        self.token = settings.whatsapp_cloud_token
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.is_configured = bool(self.token and self.phone_number_id)

    async def send_text(self, to: str, text: str) -> dict:
        if not self.is_configured:
            logger.info("[WhatsApp MOCK] send_text to=%s: %s", to, text[:100])
            return {"status": "mock", "to": to}

        url = f"{GRAPH_API_URL}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        return await self._post(url, payload)

    async def send_images(self, to: str, image_urls: list[str], caption: Optional[str] = None) -> dict:
        if not self.is_configured:
            logger.info("[WhatsApp MOCK] send_images to=%s urls=%s", to, image_urls[:3])
            return {"status": "mock", "to": to, "images": len(image_urls)}

        results = []
        for i, url in enumerate(image_urls[:3]):
            img_payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "image",
                "image": {"link": url},
            }
            if i == 0 and caption:
                img_payload["image"]["caption"] = caption
            r = await self._post(f"{GRAPH_API_URL}/{self.phone_number_id}/messages", img_payload)
            results.append(r)
        return {"status": "sent", "count": len(results), "results": results}

    async def send_template(
        self, to: str, template_name: str, language_code: str,
        components: list[dict],
    ) -> dict:
        """Send a template message via WhatsApp Cloud API. Per D-05."""
        if not self.is_configured:
            logger.info("[WhatsApp MOCK] send_template to=%s template=%s", to, template_name)
            return {"status": "mock", "to": to, "template": template_name}

        url = f"{GRAPH_API_URL}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        }
        return await self._post(url, payload)

    async def _post(self, url: str, payload: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                )
                return resp.json()
        except Exception as e:
            logger.error("WhatsApp API error: %s", e)
            return {"error": str(e)}


def parse_incoming_message(payload: dict) -> Optional[tuple[str, str, Optional[str]]]:
    """
    Parse incoming Meta WhatsApp Cloud webhook payload.
    Returns (phone, text, wamid) or None.
    """
    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None
        msg = messages[0]
        phone = msg.get("from", "")
        if msg.get("type") == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg.get("type") == "button":
            text = msg.get("button", {}).get("text", "")
        elif msg.get("type") == "interactive":
            interactive = msg.get("interactive", {})
            if interactive.get("type") == "button_reply":
                text = interactive.get("button_reply", {}).get("title", "")
            elif interactive.get("type") == "list_reply":
                text = interactive.get("list_reply", {}).get("title", "")
            else:
                text = ""
        else:
            text = ""
        wamid = msg.get("id")
        if phone and text:
            return phone, text, wamid
        return None
    except (IndexError, KeyError):
        return None


def verify_webhook(params: dict, verify_token: str) -> Optional[str]:
    """
    Handle Meta webhook verification (GET request).
    Returns challenge string if valid, None otherwise.
    """
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == verify_token:
        return challenge
    return None
