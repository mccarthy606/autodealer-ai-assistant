"""Lead creation service. Auto-creates leads from conversations, idempotent."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Lead, Event, Conversation, InventoryItem,
    LeadIntentEnum, LeadStatusEnum,
)

logger = logging.getLogger(__name__)

# Map string intents to enum
_INTENT_MAP = {
    "visit": LeadIntentEnum.visit,
    "info": LeadIntentEnum.info,
    "financing": LeadIntentEnum.financing,
    "trade_in": LeadIntentEnum.trade_in,
}


async def create_lead_from_conversation(
    session: AsyncSession,
    dealership_id: int,
    conv: "Conversation",
    state: dict,
    intent: str = "visit",
    car: Optional["InventoryItem"] = None,
    handoff_reason: Optional[str] = None,
) -> Optional[int]:
    """
    Create lead from conversation state. Idempotent: won't duplicate
    if a lead with same intent exists for this conversation in last 30 minutes.
    Returns lead_id or None if duplicate.
    """
    # Idempotency check
    cutoff = datetime.now(UTC) - timedelta(minutes=30)
    intent_enum = _INTENT_MAP.get(intent, LeadIntentEnum.info)

    stmt = select(Lead).where(
        Lead.dealership_id == dealership_id,
        Lead.phone == conv.user_phone,
        Lead.intent == intent_enum,
        Lead.created_at >= cutoff,
    )
    r = await session.execute(stmt)
    existing = r.scalar_one_or_none()
    if existing:
        logger.info("Lead already exists (id=%s) for %s/%s, skipping", existing.id, conv.user_phone, intent)
        return existing.id

    # Build notes
    lang = state.get("language", "es")
    prefs = state.get("preferences", {})
    car_summary = ""
    if car:
        car_summary = f"{car.brand} {car.model} {car.year}"
    elif state.get("last_results_ids"):
        car_summary = f"IDs: {state['last_results_ids'][:3]}"

    notes_parts = []
    if car_summary:
        notes_parts.append(f"Interested: {car_summary}")
    if state.get("preferred_time"):
        notes_parts.append(f"Time: {state['preferred_time']}")
    if prefs.get("budget_max"):
        notes_parts.append(f"Budget: ${prefs['budget_max']:,.0f}")
    notes = ". ".join(notes_parts) or None

    lead = Lead(
        dealership_id=dealership_id,
        name=state.get("name"),
        phone=conv.user_phone,
        intent=intent_enum,
        preferred_brand=prefs.get("brand") or (car.brand if car else None),
        preferred_model=prefs.get("model") or (car.model if car else None),
        budget_min=prefs.get("budget_min"),
        budget_max=prefs.get("budget_max"),
        status=LeadStatusEnum.qualified,
        notes=notes,
        source=conv.channel or "whatsapp",
        language=lang,
        last_car_id=car.id if car else None,
        preferred_time=state.get("preferred_time"),
        handoff_reason=handoff_reason,
        conversation_id=conv.id,
    )
    session.add(lead)
    await session.flush()

    # Event
    session.add(Event(
        dealership_id=dealership_id,
        type="lead_created",
        payload={
            "lead_id": lead.id,
            "intent": intent,
            "handoff_reason": handoff_reason,
            "phone": conv.user_phone,
        },
        conversation_id=conv.id,
        lead_id=lead.id,
    ))

    logger.info("Lead created: id=%s intent=%s phone=%s", lead.id, intent, conv.user_phone)
    return lead.id
