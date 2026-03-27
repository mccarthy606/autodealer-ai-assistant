"""Outbound service: ML inquiry -> WhatsApp first contact pipeline."""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Conversation, Dealership, InventoryItem, Message, MessageDirectionEnum, Event
from src.adapters.whatsapp_cloud import WhatsAppCloudAdapter
from src.adapters.mercadolibre import MercadoLibreAdapter

logger = logging.getLogger(__name__)

OUTBOUND_TEMPLATE_NAME = "outbound_car_inquiry_v1"
OUTBOUND_TEMPLATE_LANG = "es_AR"


@dataclass
class OutboundResult:
    success: bool
    method: str  # "whatsapp_template" | "ml_answer" | "error"
    conversation_id: Optional[int] = None
    message: str = ""


async def handle_ml_inquiry(
    session: AsyncSession,
    dealership_id: int,
    question_id: str,
    item_id: str,
    from_user_id: str,
    question_text: str,
) -> OutboundResult:
    """
    Full outbound pipeline:
    1. Match item_id to InventoryItem
    2. Get dealership info
    3. Attempt to get buyer phone from ML
    4. If phone: send WhatsApp template, create OUTBOUND_INIT conversation
    5. If no phone: answer ML question with car details + WhatsApp invitation
    """
    car = await _match_car(session, dealership_id, item_id)

    dealer = await _get_dealership(session, dealership_id)
    address = (dealer.address or "nuestro salon") if dealer else "nuestro salon"

    if car:
        car_title = car.display_title
        car_year_km = f"{car.year}"
        if car.km:
            car_year_km += f" - {car.km:,} km".replace(",", ".")
        car_price = f"${car.price:,.0f} {car.currency}".replace(",", ".") if car.price else "Consultar"
    else:
        car_title = "el vehiculo consultado"
        car_year_km = ""
        car_price = "Consultar"

    ml_adapter = MercadoLibreAdapter()
    buyer = await ml_adapter.get_buyer_contact(question_id)

    if buyer and buyer.get("phone"):
        customer_name = buyer.get("name", "")
        customer_phone = buyer["phone"]

        wa_adapter = WhatsAppCloudAdapter()
        components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": customer_name or "Hola"},
                    {"type": "text", "text": car_title},
                    {"type": "text", "text": car_year_km},
                    {"type": "text", "text": car_price},
                    {"type": "text", "text": address},
                ],
            }
        ]

        send_result = await wa_adapter.send_template(
            to=customer_phone,
            template_name=OUTBOUND_TEMPLATE_NAME,
            language_code=OUTBOUND_TEMPLATE_LANG,
            components=components,
        )

        if send_result.get("error"):
            logger.warning("WhatsApp template failed: %s, falling back to ML answer", send_result["error"])
            return await _fallback_ml_answer(
                ml_adapter, question_id, car_title, car_price, car_year_km, address
            )

        conv = await _create_outbound_conversation(
            session, dealership_id, customer_phone, question_id, item_id, car,
        )

        msg_out = Message(
            conversation_id=conv.id,
            direction=MessageDirectionEnum.outbound,
            text=f"[TEMPLATE] {OUTBOUND_TEMPLATE_NAME}",
            channel="whatsapp",
        )
        session.add(msg_out)

        session.add(Event(
            dealership_id=dealership_id,
            type="outbound_whatsapp_sent",
            payload={
                "question_id": question_id,
                "item_id": item_id,
                "phone": customer_phone,
                "template": OUTBOUND_TEMPLATE_NAME,
            },
            conversation_id=conv.id,
        ))

        logger.info(
            "Outbound WhatsApp sent: question=%s phone=%s car=%s",
            question_id, customer_phone, car_title,
        )

        return OutboundResult(
            success=True,
            method="whatsapp_template",
            conversation_id=conv.id,
            message=f"Template sent to {customer_phone}",
        )

    else:
        return await _fallback_ml_answer(
            ml_adapter, question_id, car_title, car_price, car_year_km, address
        )


async def _match_car(
    session: AsyncSession, dealership_id: int, item_id: str,
) -> Optional[InventoryItem]:
    if not item_id:
        return None
    stmt = select(InventoryItem).where(
        InventoryItem.dealership_id == dealership_id,
        InventoryItem.ml_item_id == item_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_dealership(
    session: AsyncSession, dealership_id: int,
) -> Optional[Dealership]:
    stmt = select(Dealership).where(Dealership.id == dealership_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _create_outbound_conversation(
    session: AsyncSession,
    dealership_id: int,
    customer_phone: str,
    question_id: str,
    item_id: str,
    car: Optional[InventoryItem],
) -> Conversation:
    stmt = select(Conversation).where(
        Conversation.dealership_id == dealership_id,
        Conversation.user_phone == customer_phone,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    outbound_state = {
        "stage": "OUTBOUND_INIT",
        "source": "mercadolibre",
        "ml_question_id": question_id,
        "ml_item_id": item_id,
        "outbound": True,
        "selected_car_id": car.id if car else None,
        "language": "es",
    }

    if existing:
        existing.state = {**(existing.state or {}), **outbound_state}
        existing.channel = "whatsapp"
        existing.mode = "bot"
        await session.flush()
        return existing

    conv = Conversation(
        dealership_id=dealership_id,
        user_phone=customer_phone,
        channel="whatsapp",
        state=outbound_state,
        mode="bot",
    )
    session.add(conv)
    await session.flush()
    return conv


async def _fallback_ml_answer(
    ml_adapter: MercadoLibreAdapter,
    question_id: str,
    car_title: str,
    car_price: str,
    car_year_km: str,
    address: str,
) -> OutboundResult:
    parts = [f"Hola! Gracias por tu consulta sobre {car_title}."]
    if car_year_km:
        parts.append(f"Detalles: {car_year_km}.")
    parts.append(f"Precio: {car_price}.")
    parts.append(f"Te esperamos en {address}.")
    parts.append("Si queres mas info, escribinos por WhatsApp para una atencion mas rapida!")

    answer_text = " ".join(parts)
    await ml_adapter.send_text(question_id, answer_text)

    logger.info("Outbound ML fallback answer sent: question=%s", question_id)

    return OutboundResult(
        success=True,
        method="ml_answer",
        message=f"ML answer sent for question {question_id}",
    )
