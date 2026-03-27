"""Handoff and notification service - email, webhook, console log."""

import logging
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import Lead, Dealership

logger = logging.getLogger(__name__)


async def handoff_to_manager(
    session: AsyncSession,
    dealership_id: int,
    lead_id: int,
    summary_text: str,
) -> None:
    """Notify manager about handoff: log, email, webhook."""
    from sqlalchemy import select

    stmt = select(Lead).where(Lead.id == lead_id, Lead.dealership_id == dealership_id)
    result = await session.execute(stmt)
    lead = result.scalar_one_or_none()
    if not lead:
        return

    stmt = select(Dealership).where(Dealership.id == dealership_id)
    result = await session.execute(stmt)
    dealership = result.scalar_one_or_none()
    address = (dealership.address or "consultar") if dealership else "consultar"

    body = (
        f"🧾 LEAD CALIENTE - Visita acordada\n\n"
        f"Teléfono: {lead.phone}\n"
        f"Nombre: {lead.name or 'No indicado'}\n"
        f"Intención: {lead.intent.value}\n"
        f"Marca/modelo preferido: {lead.preferred_brand or '-'} / {lead.preferred_model or '-'}\n"
        f"Presupuesto: {lead.budget_min or '-'} - {lead.budget_max or '-'} ARS\n\n"
        f"Resumen: {summary_text}\n\n"
        f"Dirección salón: {address}"
    )

    # 1. Console log
    logger.info("=" * 60)
    logger.info("HANDOFF TO MANAGER")
    logger.info("=" * 60)
    logger.info(body)
    logger.info("=" * 60)

    # 2. Email
    if settings.smtp_host and settings.smtp_to:
        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg["Subject"] = f"[Lead] {lead.phone} - Visita acordada"
            msg["From"] = settings.smtp_user or "noreply@autodealer.local"
            msg["To"] = settings.smtp_to
            msg.attach(MIMEText(body, "plain", "utf-8"))

            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user or None,
                password=settings.smtp_pass or None,
                use_tls=True,
            )
        except Exception as e:
            logger.warning("Failed to send handoff email: %s", e)

    # 3. Webhook
    if settings.manager_webhook_url:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    settings.manager_webhook_url,
                    json={
                        "event": "handoff",
                        "lead_id": lead_id,
                        "dealership_id": dealership_id,
                        "phone": lead.phone,
                        "name": lead.name,
                        "summary": summary_text,
                        "body": body,
                    },
                )
        except Exception as e:
            logger.warning("Failed to call manager webhook: %s", e)
