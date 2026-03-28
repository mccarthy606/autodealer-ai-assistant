"""Admin settings and integrations routes."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.routes.admin_common import auth_check, templates
from src.config import settings
from src.db.models import Dealership, InventoryItem

router = APIRouter(prefix="/admin/ui", tags=["admin-ui"])
logger = logging.getLogger(__name__)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    did = await auth_check(request)
    if not isinstance(did, int):
        return did

    stmt = select(Dealership).where(Dealership.id == did)
    r = await db.execute(stmt)
    dealer = r.scalar_one_or_none()

    saved = request.query_params.get("saved")

    return templates.TemplateResponse("admin/settings.html", {
        "request": request,
        "dealer": dealer,
        "settings": settings,
        "saved": saved,
    })


@router.post("/settings")
async def settings_save(request: Request, db: AsyncSession = Depends(get_db)):
    did = await auth_check(request)
    if not isinstance(did, int):
        return did

    form = await request.form()
    stmt = select(Dealership).where(Dealership.id == did)
    r = await db.execute(stmt)
    dealer = r.scalar_one_or_none()
    if dealer:
        dealer.address = (form.get("address") or "").strip() or None
        dealer.business_hours = (form.get("business_hours") or "").strip() or None
        dealer.name = (form.get("name") or dealer.name).strip()
        dealer.default_language = (form.get("default_language") or "es-AR").strip()

    return RedirectResponse(url="/admin/ui/settings?saved=1", status_code=302)


# === Integrations ===

@router.get("/integrations", response_class=HTMLResponse)
async def integrations_page(request: Request, db: AsyncSession = Depends(get_db)):
    did = await auth_check(request)
    if not isinstance(did, int):
        return did

    wa_configured = bool(settings.whatsapp_cloud_token and settings.whatsapp_phone_number_id)
    ml_configured = bool(settings.ml_access_token and settings.ml_user_id)

    # ML linked cars
    stmt = select(InventoryItem).where(
        InventoryItem.dealership_id == did,
        InventoryItem.ml_item_id.isnot(None),
    )
    r = await db.execute(stmt)
    ml_cars = r.scalars().all()

    return templates.TemplateResponse("admin/integrations.html", {
        "request": request,
        "wa_configured": wa_configured,
        "ml_configured": ml_configured,
        "ml_cars": ml_cars,
        "wa_phone_id": settings.whatsapp_phone_number_id or "Not set",
        "wa_verify_token": bool(settings.whatsapp_verify_token),
    })
