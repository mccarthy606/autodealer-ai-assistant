"""Admin lead listing routes."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.routes.admin_common import auth_check, templates
from src.db.models import Lead, LeadIntentEnum, LeadStatusEnum

router = APIRouter(prefix="/admin/ui", tags=["admin-ui"])
logger = logging.getLogger(__name__)


@router.get("/leads", response_class=HTMLResponse)
async def leads_page(request: Request, db: AsyncSession = Depends(get_db)):
    did = await auth_check(request)
    if not isinstance(did, int):
        return did
    intent_filter = request.query_params.get("intent", "").strip()
    status_filter = request.query_params.get("status", "").strip()
    source_filter = request.query_params.get("source", "").strip()

    stmt = select(Lead).where(Lead.dealership_id == did)
    if intent_filter:
        try:
            stmt = stmt.where(Lead.intent == LeadIntentEnum(intent_filter))
        except ValueError:
            pass
    if status_filter:
        try:
            stmt = stmt.where(Lead.status == LeadStatusEnum(status_filter))
        except ValueError:
            pass
    if source_filter:
        stmt = stmt.where(Lead.source == source_filter)

    stmt = stmt.order_by(Lead.created_at.desc()).limit(200)
    result = await db.execute(stmt)
    leads = result.scalars().all()

    return templates.TemplateResponse("admin/leads.html", {
        "request": request,
        "leads": leads,
        "filters": {"intent": intent_filter, "status": status_filter, "source": source_filter},
    })
