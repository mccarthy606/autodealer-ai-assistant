"""Unified conversation engine. Single entry point for all channels.

State machine stages:
  NEW -> BROWSING -> PRESENTING -> DETAILS -> CLOSING -> HANDOFF
                                           -> NOTIFY_WAIT
"""

import logging
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Conversation, Dealership, Message, MessageDirectionEnum,
    Event, InventoryItem,
)
from src.services.intent import (
    detect_intent,
    SEARCH_CAR, ASK_PHOTOS, ASK_DETAILS, ASK_PRICE, ASK_KM, ASK_STATUS,
    VISIT, FINANCING, TRADE_IN, NOTIFY, HUMAN, GREETING, OTHER,
    OPT_OUT,
)
from src.services.entities import extract_all, detect_language
from src.services.handoff_rules import check_handoff, REASON_VISIT_SCHEDULING, REASON_PHOTOS_MISSING
from src.services.inventory import InventoryService
from src.services import responder
from src.services.lead_service import create_lead_from_conversation

logger = logging.getLogger(__name__)


class EngineResult:
    """Structured result from engine processing."""
    def __init__(self):
        self.text: str = ""
        self.matched_cars: list[dict] = []
        self.selected_car: Optional[dict] = None
        self.photo_urls: list[str] = []
        self.lead_id: Optional[int] = None
        self.mode: str = "bot"
        self.stage: str = "NEW"
        self.intent: str = "OTHER"
        self.language: str = "es"
        self.handoff_reason: Optional[str] = None
        self.state: dict = {}
        self.conversation_id: int = 0

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "matched_cars": self.matched_cars,
            "selected_car": self.selected_car,
            "photo_urls": self.photo_urls,
            "lead_id": self.lead_id,
            "mode": self.mode,
            "stage": self.stage,
            "intent": self.intent,
            "language": self.language,
            "handoff_reason": self.handoff_reason,
            "state": self.state,
            "conversation_id": self.conversation_id,
        }


async def process_message(
    session: AsyncSession,
    dealership_id: int,
    phone: str,
    text: str,
    channel: str = "whatsapp",
    wamid: Optional[str] = None,
) -> EngineResult:
    """
    Main entry point. Process incoming message and return structured result.
    """
    result = EngineResult()

    # 1. Get or create conversation
    conv = await _get_or_create_conversation(session, dealership_id, phone, channel)
    result.conversation_id = conv.id

    # 2. Save inbound message
    msg_in = Message(
        conversation_id=conv.id,
        direction=MessageDirectionEnum.inbound,
        text=text,
        channel=channel,
        wamid=wamid,
    )
    session.add(msg_in)
    await session.flush()

    # Log event
    session.add(Event(
        dealership_id=dealership_id,
        type="message_in",
        payload={"phone": phone, "channel": channel},
        conversation_id=conv.id,
    ))

    # 3. Load state
    state = dict(conv.state or {})

    # 4. Check if in manager mode — don't auto reply
    if conv.mode == "manager":
        result.text = ""
        result.mode = "manager"
        result.stage = state.get("stage", "HANDOFF")
        result.language = state.get("language", "es")
        result.state = state
        result.handoff_reason = conv.handoff_reason
        # Still save the message but no bot response
        conv.last_message_at = datetime.now(UTC)
        return result

    # Skip opted-out conversations — silently ignore, return empty response
    if state.get("opted_out"):
        result.text = ""
        result.intent = OPT_OUT
        result.mode = conv.mode
        result.stage = state.get("stage", "NEW")
        result.language = state.get("language", "es")
        result.state = state
        return result

    # 5. Detect language + save
    lang = state.get("language")
    detected_lang = detect_language(text)
    if not lang:
        lang = detected_lang
    elif detected_lang != lang.split("-")[0]:
        # User switched language - update to match (symmetric: es->en and en->es)
        lang = detected_lang
    state["language"] = lang
    result.language = lang

    # 6. Extract entities
    entities = extract_all(text)
    if entities["name"]:
        state["name"] = entities["name"]
    if entities["time"]:
        state["preferred_time"] = entities["time"]

    # Update preferences from entities
    prefs = state.get("preferences", {})
    if entities["brand"]:
        prefs["brand"] = entities["brand"]
    if entities["model"]:
        prefs["model"] = entities["model"]
    if entities["year"]:
        prefs["year"] = entities["year"]
    if entities["budget_max"]:
        prefs["budget_max"] = entities["budget_max"]
    if entities["budget_min"]:
        prefs["budget_min"] = entities["budget_min"]
    if entities["condition"]:
        prefs["condition"] = entities["condition"]
    state["preferences"] = prefs

    # 7. Detect intent
    intent = detect_intent(text, state)
    result.intent = intent

    # 8. Get dealership info
    dealer = await _get_dealership(session, dealership_id)
    address = (dealer.address or "nuestro salón") if dealer else "nuestro salón"
    hours = (dealer.business_hours or "") if dealer else ""

    # 9. Process by intent
    stage = state.get("stage", "NEW")

    # --- OUTBOUND_INIT: customer replied to our outbound template ---
    if stage == "OUTBOUND_INIT":
        state["stage"] = "PRESENTING"
        stage = "PRESENTING"
        logger.info("Outbound conversation activated: conv=%s", conv.id)

    # --- OPT_OUT (per D-10, D-11, D-12) ---
    if intent == OPT_OUT:
        state = {**state, "opted_out": True}
        conv.last_message_at = datetime.now(UTC)

        lang = state.get("language", "es")
        if lang.startswith("es"):
            result.text = "Entendido, no te vamos a molestar más. Si cambiás de opinión, escribinos!"
        else:
            result.text = "Understood, we won't bother you again. Feel free to write us if you change your mind!"

        result.intent = OPT_OUT
        result.mode = conv.mode
        result.stage = state.get("stage", "NEW")
        result.language = lang
        result.state = state

        session.add(Event(
            dealership_id=dealership_id,
            type="opt_out",
            payload={"phone": phone},
            conversation_id=conv.id,
        ))
        # Save state BEFORE returning — use JSONB-safe assignment (single write, no double-assign)
        conv.state = {**dict(conv.state or {}), "opted_out": True}
        await session.flush()
        return result

    # --- GREETING ---
    if intent == GREETING and stage == "NEW":
        result.text = responder.get_response(GREETING, lang)
        state["stage"] = "BROWSING"

    # --- SEARCH ---
    elif intent == SEARCH_CAR or (intent in (ASK_PRICE, OTHER) and stage in ("NEW", "BROWSING") and (prefs.get("brand") or prefs.get("model"))):
        cars = await InventoryService.search(
            session, dealership_id,
            brand=prefs.get("brand"),
            model=prefs.get("model"),
            year=prefs.get("year"),
            condition=prefs.get("condition"),
            budget_max=prefs.get("budget_max"),
            budget_min=prefs.get("budget_min"),
            limit=3,
        )
        alternatives = []
        if not cars and prefs.get("brand"):
            # Try alternatives: same brand, no model filter
            alternatives = await InventoryService.search(
                session, dealership_id,
                brand=prefs.get("brand"),
                limit=3,
            )
            if not alternatives:
                # Try similar price range
                if prefs.get("budget_max"):
                    alternatives = await InventoryService.search(
                        session, dealership_id,
                        budget_max=prefs["budget_max"] * 1.2,
                        limit=3,
                    )

        result.text = responder.build_search_response(cars, alternatives, lang)
        result.matched_cars = cars or alternatives

        if cars:
            state["last_results_ids"] = [c["id"] for c in cars]
            state["selected_car_id"] = cars[0]["id"]
            state["stage"] = "PRESENTING"
        elif alternatives:
            state["last_results_ids"] = [c["id"] for c in alternatives]
            state["selected_car_id"] = alternatives[0]["id"]
            state["stage"] = "PRESENTING"
        else:
            state["unhelpful_count"] = state.get("unhelpful_count", 0) + 1
            state["stage"] = "BROWSING"

        # Log search event
        session.add(Event(
            dealership_id=dealership_id,
            type="search_performed",
            payload={"brand": prefs.get("brand"), "model": prefs.get("model"), "results": len(result.matched_cars)},
            conversation_id=conv.id,
        ))

    # --- ASK_PHOTOS ---
    elif intent == ASK_PHOTOS:
        car = await _get_selected_car(session, state)
        if car:
            text_resp, photo_urls = responder.build_photos_response(_car_to_dict(car), lang)
            result.text = text_resp
            result.photo_urls = photo_urls
            result.selected_car = _car_to_dict(car)

            if not photo_urls:
                # Handoff: photos missing
                handoff_reason = REASON_PHOTOS_MISSING
                result.text = responder.build_handoff_response(handoff_reason, lang)
                await _do_handoff(session, conv, state, handoff_reason, dealership_id, result)
        else:
            result.text = responder.get_response("PHOTOS_MISSING", lang)
            state["unhelpful_count"] = state.get("unhelpful_count", 0) + 1

    # --- ASK_DETAILS ---
    elif intent == ASK_DETAILS:
        car = await _get_selected_car(session, state)
        if car:
            result.text = responder.build_details_response(_car_to_dict(car), lang)
            result.selected_car = _car_to_dict(car)
            state["stage"] = "DETAILS"
        else:
            result.text = responder.get_response(OTHER, lang)
            state["unhelpful_count"] = state.get("unhelpful_count", 0) + 1

    # --- ASK_PRICE ---
    elif intent == ASK_PRICE:
        car = await _get_selected_car(session, state)
        if car:
            price_str = f"${float(car.price):,.0f} {car.currency}"
            if lang.startswith("es"):
                result.text = f"El precio es {price_str}. ¿Querés pasar a verlo?"
            else:
                result.text = f"The price is {price_str}. Would you like to come see it?"
            result.selected_car = _car_to_dict(car)
        else:
            result.text = responder.get_response(OTHER, lang)

    # --- ASK_KM ---
    elif intent == ASK_KM:
        car = await _get_selected_car(session, state)
        if car:
            km_str = f"{car.km:,} km" if car.km else "0 km"
            if lang.startswith("es"):
                result.text = f"Tiene {km_str}. ¿Querés más detalles o pasar a verlo?"
            else:
                result.text = f"It has {km_str}. Want more details or to come see it?"
            result.selected_car = _car_to_dict(car)
        else:
            result.text = responder.get_response(OTHER, lang)

    # --- ASK_STATUS ---
    elif intent == ASK_STATUS:
        car = await _get_selected_car(session, state)
        if car:
            status_labels = {
                "available": ("Sí, está disponible", "Yes, it's available"),
                "in_transit": ("Está en camino, llega pronto", "It's in transit, arriving soon"),
                "reserved": ("Está reservado por otro cliente", "It's reserved by another customer"),
                "sold": ("Lamentablemente ya se vendió", "Unfortunately it's already sold"),
            }
            es_label, en_label = status_labels.get(car.status.value, ("Disponible", "Available"))
            label = es_label if lang.startswith("es") else en_label
            suffix = " ¿Querés pasar a verlo?" if lang.startswith("es") else " Would you like to come see it?"
            result.text = f"{label}.{suffix}"
            result.selected_car = _car_to_dict(car)
        else:
            result.text = responder.get_response(OTHER, lang)

    # --- VISIT ---
    elif intent == VISIT:
        state["stage"] = "CLOSING"
        time_str = state.get("preferred_time") or entities.get("time")
        name = state.get("name")
        result.text = responder.build_visit_response(address, hours, name, time_str, lang)

        # Auto create lead
        car = await _get_selected_car(session, state)
        lead_id = await create_lead_from_conversation(
            session, dealership_id, conv, state,
            intent="visit",
            car=car,
            handoff_reason=REASON_VISIT_SCHEDULING,
        )
        result.lead_id = lead_id
        if car:
            result.selected_car = _car_to_dict(car)

        # Handoff to manager
        await _do_handoff(session, conv, state, REASON_VISIT_SCHEDULING, dealership_id, result)

    # --- FINANCING ---
    elif intent == FINANCING:
        result.text = responder.build_handoff_response("financing", lang)
        car = await _get_selected_car(session, state)
        lead_id = await create_lead_from_conversation(
            session, dealership_id, conv, state,
            intent="financing",
            car=car,
            handoff_reason="financing",
        )
        result.lead_id = lead_id
        await _do_handoff(session, conv, state, "financing", dealership_id, result)

    # --- TRADE_IN ---
    elif intent == TRADE_IN:
        result.text = responder.build_handoff_response("trade_in", lang)
        car = await _get_selected_car(session, state)
        lead_id = await create_lead_from_conversation(
            session, dealership_id, conv, state,
            intent="trade_in",
            car=car,
            handoff_reason="trade_in",
        )
        result.lead_id = lead_id
        await _do_handoff(session, conv, state, "trade_in", dealership_id, result)

    # --- HUMAN ---
    elif intent == HUMAN:
        result.text = responder.build_handoff_response("requested_human", lang)
        lead_id = await create_lead_from_conversation(
            session, dealership_id, conv, state,
            intent="info",
            handoff_reason="requested_human",
        )
        result.lead_id = lead_id
        await _do_handoff(session, conv, state, "requested_human", dealership_id, result)

    # --- NOTIFY ---
    elif intent == NOTIFY:
        result.text = responder.get_response("NOTIFY", lang)
        car = await _get_selected_car(session, state)
        await create_lead_from_conversation(
            session, dealership_id, conv, state,
            intent="info",
            car=car,
            handoff_reason=None,
        )
        state["stage"] = "NOTIFY_WAIT"

    # --- OTHER ---
    else:
        # If we have context (selected car), try to be helpful
        if stage in ("PRESENTING", "DETAILS") and state.get("selected_car_id"):
            car = await _get_selected_car(session, state)
            if car:
                result.text = responder.build_details_response(_car_to_dict(car), lang)
                result.selected_car = _car_to_dict(car)
                state["stage"] = "DETAILS"
            else:
                result.text = responder.get_response(OTHER, lang)
                state["unhelpful_count"] = state.get("unhelpful_count", 0) + 1
        else:
            result.text = responder.get_response(OTHER, lang)
            state["unhelpful_count"] = state.get("unhelpful_count", 0) + 1

    # 10. Check unhelpful handoff (H6)
    if state.get("unhelpful_count", 0) >= 2 and conv.mode != "manager":
        handoff_reason = "bot_unhelpful"
        result.text = responder.build_handoff_response(handoff_reason, lang)
        await _do_handoff(session, conv, state, handoff_reason, dealership_id, result)

    # 10b. LLM full response (D-02: generate_response takes over when llm_enabled=True)
    if result.text and result.mode == "bot":
        try:
            from src.config import settings as _settings
            from src.db.models import Dealership as _Dealership

            # Fetch dealer row for per-dealer config (D-04)
            _dealer_stmt = select(_Dealership).where(_Dealership.id == dealership_id)
            _dealer_row = (await session.execute(_dealer_stmt)).scalar_one_or_none()

            # D-06: dealer.llm_enabled overrides global when not None
            _effective_llm = (
                _dealer_row.llm_enabled
                if _dealer_row is not None and _dealer_row.llm_enabled is not None
                else _settings.llm_enabled
            )

            # D-05: dealer key first, then global key; if neither set, skip LLM
            _effective_key = (
                (_dealer_row.llm_api_key or "") if _dealer_row else ""
            ) or _settings.openai_api_key

            if _effective_llm and _effective_key:
                from src.services.llm_service import LLMService, ToolsExecutor
                from openai import AsyncOpenAI

                # Build LLM client with effective key and model
                _llm = LLMService()
                _llm.client = AsyncOpenAI(api_key=_effective_key)
                _llm.model = (
                    (_dealer_row.llm_model or "") if _dealer_row else ""
                ) or _settings.openai_model

                # D-07: last 10 messages as conversation history
                _hist_stmt = (
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.id.desc())
                    .limit(10)
                )
                _hist_rows = (await session.execute(_hist_stmt)).scalars().all()
                _history = [
                    {"direction": m.direction.value, "text": m.text or ""}
                    for m in reversed(_hist_rows)
                ]

                # Wire ToolsExecutor — callbacks are optional notifications;
                # ToolsExecutor handles lead creation and handoff internally.
                _tools_exec = ToolsExecutor(
                    on_create_lead=None,
                    on_handoff=None,
                )

                _llm_text, _llm_state = await _llm.generate_response(
                    session=session,
                    dealership_id=dealership_id,
                    user_message=text,
                    conversation_history=_history,
                    state=state,
                    user_phone=phone,
                    tools_executor=_tools_exec,
                )
                if _llm_text:
                    result.text = _llm_text
                    state = _llm_state

        except Exception as _e:
            logger.warning("LLM generate_response failed, using deterministic: %s", _e)

    # 11. Save outbound message (if any)
    if result.text:
        msg_out = Message(
            conversation_id=conv.id,
            direction=MessageDirectionEnum.outbound,
            text=result.text,
            channel=channel,
            attachments=result.photo_urls if result.photo_urls else [],
        )
        session.add(msg_out)
        session.add(Event(
            dealership_id=dealership_id,
            type="message_out",
            payload={"conversation_id": conv.id},
            conversation_id=conv.id,
        ))

    # 12. Update conversation state
    conv.state = state
    conv.last_message_at = datetime.now(UTC)
    result.state = state
    result.stage = state.get("stage", "NEW")
    result.mode = conv.mode or "bot"
    result.handoff_reason = conv.handoff_reason

    return result


# === Helpers ===

async def _get_or_create_conversation(
    session: AsyncSession, dealership_id: int, phone: str, channel: str
) -> Conversation:
    stmt = select(Conversation).where(
        Conversation.dealership_id == dealership_id,
        Conversation.user_phone == phone,
    )
    r = await session.execute(stmt)
    conv = r.scalar_one_or_none()
    if not conv:
        try:
            conv = Conversation(
                dealership_id=dealership_id,
                user_phone=phone,
                channel=channel,
                state={},
                mode="bot",
            )
            session.add(conv)
            await session.flush()
        except IntegrityError:
            # Race condition: another request created the conversation first
            await session.rollback()
            r = await session.execute(stmt)
            conv = r.scalar_one_or_none()
            if not conv:
                raise
    return conv


async def _get_dealership(session: AsyncSession, dealership_id: int) -> Optional[Dealership]:
    stmt = select(Dealership).where(Dealership.id == dealership_id)
    r = await session.execute(stmt)
    return r.scalar_one_or_none()


async def _get_selected_car(session: AsyncSession, state: dict) -> Optional[InventoryItem]:
    car_id = state.get("selected_car_id")
    if not car_id:
        # Try first from last results
        ids = state.get("last_results_ids", [])
        if ids:
            car_id = ids[0]
    if not car_id:
        return None
    stmt = select(InventoryItem).where(InventoryItem.id == car_id)
    r = await session.execute(stmt)
    return r.scalar_one_or_none()


def _car_to_dict(car: InventoryItem) -> dict:
    return {
        "id": car.id,
        "brand": car.brand,
        "model": car.model,
        "trim": car.trim,
        "year": car.year,
        "condition": car.condition.value,
        "km": car.km,
        "price": float(car.price),
        "currency": car.currency,
        "status": car.status.value,
        "location": car.location,
        "photos": car.photos or [],
        "description": car.description,
        "title": car.display_title,
        "tags": car.tags or [],
    }


async def _do_handoff(
    session: AsyncSession,
    conv: Conversation,
    state: dict,
    reason: str,
    dealership_id: int,
    result: EngineResult,
):
    """Execute handoff: update conversation mode and log event."""
    conv.mode = "manager"
    conv.handoff_reason = reason
    conv.last_handoff_at = datetime.now(UTC)
    state["stage"] = "HANDOFF"
    result.mode = "manager"
    result.handoff_reason = reason

    session.add(Event(
        dealership_id=dealership_id,
        type="handoff",
        payload={"reason": reason, "conversation_id": conv.id},
        conversation_id=conv.id,
    ))
    logger.info("HANDOFF: conv=%s reason=%s", conv.id, reason)
