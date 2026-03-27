"""Debug endpoint for testing bot without WhatsApp payload."""

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.deps import get_db
from src.config import settings
from src.services.conversation_engine import process_message

router = APIRouter(prefix="/debug", tags=["debug"])


class DebugMessageRequest(BaseModel):
    phone: str
    text: str
    dealership_id: Optional[int] = None
    channel: str = "admin_test"


class DebugMessageResponse(BaseModel):
    text: str
    matched_cars: list[dict[str, Any]] = []
    conversation_id: int = 0
    state: dict[str, Any] = {}
    lead_id: Optional[int] = None
    intent: str = ""
    stage: str = ""
    mode: str = "bot"
    handoff_reason: Optional[str] = None


@router.post("/message", response_model=DebugMessageResponse)
async def debug_message(
    req: DebugMessageRequest,
    db=Depends(get_db),
) -> dict[str, Any]:
    """Process message through conversation engine (no webhook parsing)."""
    did = req.dealership_id or settings.default_dealership_id

    result = await process_message(
        session=db,
        dealership_id=did,
        phone=req.phone,
        text=req.text,
        channel=req.channel,
    )

    return {
        "text": result.text,
        "matched_cars": result.matched_cars,
        "conversation_id": result.conversation_id,
        "state": result.state,
        "lead_id": result.lead_id,
        "intent": result.intent,
        "stage": result.stage,
        "mode": result.mode,
        "handoff_reason": result.handoff_reason,
    }
