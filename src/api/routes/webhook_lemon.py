"""Lemon Squeezy webhook handler with signature verification."""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.config import settings
from src.db.models import Dealership
from src.services.billing import map_ls_status

router = APIRouter(prefix="/webhooks/lemon-squeezy", tags=["webhooks-billing"])
logger = logging.getLogger(__name__)


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature from X-Signature header."""
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("")
async def lemon_squeezy_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle incoming Lemon Squeezy webhook events."""
    secret = settings.lemon_squeezy_webhook_secret
    if not secret:
        logger.warning("LEMON_SQUEEZY_WEBHOOK_SECRET not configured, rejecting webhook")
        return JSONResponse({"error": "not configured"}, status_code=200)

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

    # Extract dealership_id from custom_data
    dealership_id_str = payload.get("meta", {}).get("custom_data", {}).get("dealership_id")
    if not dealership_id_str:
        logger.warning("LS webhook %s: missing custom_data.dealership_id", event_name)
        return {"status": "ok", "event": event_name}
    try:
        dealership_id = int(dealership_id_str)
    except (ValueError, TypeError):
        logger.warning("LS webhook %s: invalid dealership_id=%r", event_name, dealership_id_str)
        return {"status": "ok", "event": event_name}
    if dealership_id <= 0:
        logger.warning("LS webhook %s: zero/negative dealership_id=%d", event_name, dealership_id)
        return {"status": "ok", "event": event_name}

    # Load dealership row
    stmt = select(Dealership).where(Dealership.id == dealership_id)
    result = await db.execute(stmt)
    dealer = result.scalar_one_or_none()
    if dealer is None:
        logger.warning("LS webhook %s: dealership %d not found", event_name, dealership_id)
        return {"status": "ok", "event": event_name}

    # Event dispatch
    try:
        if event_name == "subscription_created":
            attrs = payload["data"]["attributes"]
            dealer.subscription_id = payload["data"]["id"]
            dealer.ls_customer_id = str(attrs.get("customer_id", ""))
            dealer.plan = attrs.get("variant_name")
            dealer.subscription_status = map_ls_status(attrs.get("status", ""))
            trial_str = attrs.get("trial_ends_at")
            if trial_str:
                try:
                    dealer.trial_ends_at = datetime.fromisoformat(trial_str.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning("LS webhook: could not parse trial_ends_at=%r", trial_str)
            elif attrs.get("status") == "on_trial":
                dealer.trial_ends_at = datetime.now(UTC) + timedelta(days=7)  # D-11 fallback

        elif event_name == "subscription_updated":
            attrs = payload["data"]["attributes"]
            dealer.subscription_id = payload["data"]["id"]
            dealer.subscription_status = map_ls_status(attrs.get("status", ""))
            if attrs.get("variant_name") is not None:
                dealer.plan = attrs.get("variant_name")
            trial_str = attrs.get("trial_ends_at")
            if trial_str:
                try:
                    dealer.trial_ends_at = datetime.fromisoformat(trial_str.replace("Z", "+00:00"))
                except ValueError:
                    logger.warning("LS webhook: could not parse trial_ends_at=%r", trial_str)
            else:
                dealer.trial_ends_at = None  # trial ended, clear it

        elif event_name == "subscription_payment_failed":
            # CRITICAL: data.type is "subscription_invoices" here — data.id is the INVOICE id.
            # Subscription ID is at data.attributes.subscription_id (integer in payload).
            sub_id = payload["data"]["attributes"]["subscription_id"]
            if sub_id is not None:
                dealer.subscription_id = str(sub_id)
            dealer.subscription_status = "past_due"
            dealer.grace_period_ends_at = datetime.now(UTC) + timedelta(days=7)  # D-12

        elif event_name == "subscription_cancelled":
            dealer.subscription_status = "cancelled"

        elif event_name == "subscription_expired":
            dealer.subscription_status = "expired"
            dealer.grace_period_ends_at = None

        else:
            logger.info("LS webhook: unhandled event=%s for dealership=%d", event_name, dealership_id)
            return {"status": "ok", "event": event_name}

        await db.commit()
        logger.info(
            "LS webhook %s: updated dealership %d status=%s",
            event_name,
            dealership_id,
            dealer.subscription_status,
        )
        return {"status": "ok", "event": event_name}

    except Exception as exc:
        logger.exception("LS webhook %s: DB error for dealership %d: %s", event_name, dealership_id, exc)
        # Still return 200 to prevent LS retry storm (per RESEARCH pitfall 4)
        return {"status": "ok", "event": event_name}
