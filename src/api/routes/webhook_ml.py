"""MercadoLibre webhook routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.config import settings
from src.adapters.mercadolibre import MercadoLibreAdapter, parse_incoming_question, get_dealership_by_ml
from src.services.outbound_service import handle_ml_inquiry

router = APIRouter(prefix="/webhooks/mercadolibre", tags=["webhooks-ml"])
logger = logging.getLogger(__name__)


@router.post("")
async def receive_ml_notification(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Receive MercadoLibre notifications (questions, orders, etc).
    For questions: trigger outbound flow (WhatsApp first contact) + answer on ML.
    """
    import hashlib
    import hmac as _hmac
    import json as _json
    import secrets as _sec
    raw_body = await request.body()

    # Verify HMAC signature when ML_WEBHOOK_SECRET is configured.
    # When not configured, requests pass through (single-tenant / dev mode).
    if settings.ml_webhook_secret:
        sig_header = request.headers.get("x-signature", "")
        expected = _hmac.new(
            settings.ml_webhook_secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        if not _sec.compare_digest(expected, sig_header):
            logger.warning("ML webhook: invalid signature")
            return {"status": "ok"}
    else:
        logger.warning("ML_WEBHOOK_SECRET not configured — skipping signature verification")

    try:
        payload = _json.loads(raw_body)
    except Exception:
        return {"status": "error"}

    parsed = parse_incoming_question(payload)
    if not parsed:
        return {"status": "ok", "message": "not a question notification"}

    question_id = parsed["question_id"]
    seller_id = str(parsed.get("user_id") or "")
    logger.info("ML question received: %s", question_id)

    # Route to dealership by ML user_id (per D-13).
    # Unknown seller_id rejects silently — prevents spoofed payloads from triggering
    # outbound WhatsApp sends at the dealership's expense.
    dealership_id = settings.default_dealership_id  # fallback for single-tenant legacy
    if seller_id:
        dealer = await get_dealership_by_ml(db, seller_id)
        if dealer:
            dealership_id = dealer.id
        elif settings.default_dealership_id:
            logger.warning(
                "ML webhook: unknown seller_id=%s — not matched to any dealership. "
                "Falling back to default_dealership_id=%s (single-tenant mode).",
                seller_id, settings.default_dealership_id,
            )
        else:
            logger.warning("ML webhook: unknown seller_id=%s, no default configured, rejecting", seller_id)
            return {"status": "ok"}

    # Fetch the actual question data from ML API
    adapter = MercadoLibreAdapter()
    if not adapter.is_configured:
        logger.info("[ML MOCK] Question %s - adapter not configured, skipping", question_id)
        return {"status": "ok", "message": "ml not configured"}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"https://api.mercadolibre.com/questions/{question_id}",
                headers={"Authorization": f"Bearer {settings.ml_access_token}"},
            )
            q_data = resp.json()
            question_text = q_data.get("text", "")
            from_user = str(q_data.get("from", {}).get("id", ""))
            item_id = str(q_data.get("item_id", ""))
    except Exception as e:
        logger.error("Failed to fetch ML question: %s", e)
        return {"status": "error", "message": str(e)}

    if not question_text:
        return {"status": "ok"}

    # Outbound flow: try to contact customer on WhatsApp
    try:
        outbound_result = await handle_ml_inquiry(
            session=db,
            dealership_id=dealership_id,
            question_id=question_id,
            item_id=item_id,
            from_user_id=from_user,
            question_text=question_text,
        )
        logger.info(
            "Outbound result: method=%s success=%s message=%s",
            outbound_result.method, outbound_result.success, outbound_result.message,
        )

        # If we sent WhatsApp template, also answer the ML question with a brief note
        if outbound_result.method == "whatsapp_template":
            try:
                await adapter.send_text(
                    question_id,
                    "Hola! Ya te enviamos la info por WhatsApp. Cualquier duda, escribinos por ahi!",
                )
            except Exception as e:
                logger.warning("Failed to send ML acknowledgment: %s", e)

        # If method was "ml_answer", the outbound service already answered on ML
    except Exception as e:
        logger.error("Outbound flow error: %s", e)
        try:
            await adapter.send_text(question_id, "Hola! Gracias por tu consulta. Te respondemos a la brevedad.")
        except Exception:
            pass

    return {"status": "ok", "question_id": question_id}
