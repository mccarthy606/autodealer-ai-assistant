"""MercadoLibre webhook routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.config import settings
from src.adapters.mercadolibre import MercadoLibreAdapter, parse_incoming_question
from src.services.conversation_engine import process_message

router = APIRouter(prefix="/webhooks/mercadolibre", tags=["webhooks-ml"])
logger = logging.getLogger(__name__)


@router.post("")
async def receive_ml_notification(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Receive MercadoLibre notifications (questions, orders, etc).
    For questions: process through engine and send answer.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "error"}

    parsed = parse_incoming_question(payload)
    if not parsed:
        return {"status": "ok", "message": "not a question notification"}

    question_id = parsed["question_id"]
    logger.info("ML question received: %s", question_id)

    # Fetch the actual question text from ML API
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

    # Use item_id or from_user as phone identifier
    phone = f"ml_{from_user}" if from_user else f"ml_{question_id}"

    result = await process_message(
        session=db,
        dealership_id=settings.default_dealership_id,
        phone=phone,
        text=question_text,
        channel="mercadolibre",
    )

    # Send answer
    if result.text:
        await adapter.send_text(question_id, result.text)

    return {"status": "ok", "question_id": question_id}
