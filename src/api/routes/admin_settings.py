"""Admin settings and integrations routes."""

import logging

import httpx
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

    saved = request.query_params.get("saved") == "1"

    return templates.TemplateResponse("admin/settings.html", {
        "request": request,
        "dealer": dealer,
        "llm_enabled": settings.llm_enabled,
        "followups_enabled": settings.followups_enabled,
        "saved": saved,
        "dealer_llm_api_key_set": bool(dealer and dealer.llm_api_key),
        "dealer_llm_model": (dealer.llm_model or "") if dealer else "",
        "dealer_llm_enabled": dealer.llm_enabled if dealer else None,
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
        # LLM config (D-08) — blank api_key keeps existing (credentials not echoed back)
        if form.get("llm_api_key"):
            dealer.llm_api_key = form["llm_api_key"].strip()
        dealer.llm_model = (form.get("llm_model") or "").strip() or None
        # HTML checkbox: key present in form = checked = True, absent = False
        dealer.llm_enabled = "llm_enabled" in form

    return RedirectResponse(url="/admin/ui/settings?saved=1", status_code=302)


# === Integrations ===

@router.get("/integrations", response_class=HTMLResponse)
async def integrations_page(request: Request, db: AsyncSession = Depends(get_db)):
    did = await auth_check(request)
    if not isinstance(did, int):
        return did

    stmt = select(Dealership).where(Dealership.id == did)
    r = await db.execute(stmt)
    dealer = r.scalar_one_or_none()

    wa_configured = bool(
        (dealer and dealer.whatsapp_access_token) or settings.whatsapp_cloud_token
    )
    ml_configured = bool(
        (dealer and dealer.ml_access_token) or settings.ml_access_token
    )

    stmt2 = (
        select(InventoryItem)
        .where(InventoryItem.dealership_id == did, InventoryItem.ml_item_id.isnot(None))
        .limit(200)
    )
    r2 = await db.execute(stmt2)
    ml_cars = r2.scalars().all()

    saved = request.query_params.get("saved") == "1"

    return templates.TemplateResponse("admin/integrations.html", {
        "request": request,
        "dealer": dealer,
        "wa_configured": wa_configured,
        "ml_configured": ml_configured,
        "ml_cars": ml_cars,
        "saved": saved,
    })


@router.post("/integrations")
async def integrations_save(request: Request, db: AsyncSession = Depends(get_db)):
    """Save WhatsApp and MercadoLibre credentials to the Dealership row."""
    did = await auth_check(request)
    if not isinstance(did, int):
        return did

    form = await request.form()
    stmt = select(Dealership).where(Dealership.id == did)
    r = await db.execute(stmt)
    dealer = r.scalar_one_or_none()

    if dealer:
        # Only update non-blank submitted fields — blank = keep existing value
        if form.get("whatsapp_phone_number_id"):
            dealer.whatsapp_phone_number_id = form["whatsapp_phone_number_id"].strip()
        if form.get("whatsapp_access_token"):
            dealer.whatsapp_access_token = form["whatsapp_access_token"].strip()
        if form.get("whatsapp_verify_token"):
            dealer.whatsapp_verify_token = form["whatsapp_verify_token"].strip()
        if form.get("whatsapp_webhook_secret"):
            dealer.whatsapp_webhook_secret = form["whatsapp_webhook_secret"].strip()
        if form.get("ml_access_token"):
            dealer.ml_access_token = form["ml_access_token"].strip()
        if form.get("ml_refresh_token"):
            dealer.ml_refresh_token = form["ml_refresh_token"].strip()
        if form.get("ml_app_id"):
            dealer.ml_app_id = form["ml_app_id"].strip()
        if form.get("ml_client_secret"):
            dealer.ml_client_secret = form["ml_client_secret"].strip()
        if form.get("ml_user_id"):
            dealer.ml_user_id = form["ml_user_id"].strip()

    return RedirectResponse(url="/admin/ui/integrations?saved=1", status_code=302)


@router.post("/integrations/test-connection")
async def test_connection(request: Request, db: AsyncSession = Depends(get_db)):
    """Live API validation for WhatsApp or MercadoLibre credentials."""
    did = await auth_check(request)
    if not isinstance(did, int):
        return {"ok": False, "detail": "No autenticado"}

    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "detail": "Solicitud invalida"}

    service = body.get("service")  # "whatsapp" or "mercadolibre"

    stmt = select(Dealership).where(Dealership.id == did)
    r = await db.execute(stmt)
    dealer = r.scalar_one_or_none()
    if not dealer:
        return {"ok": False, "detail": "Concesionario no encontrado"}

    if service == "whatsapp":
        token = dealer.whatsapp_access_token or settings.whatsapp_cloud_token
        phone_id = dealer.whatsapp_phone_number_id or settings.whatsapp_phone_number_id
        if not token or not phone_id:
            return {"ok": False, "detail": "Credenciales no configuradas"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://graph.facebook.com/v18.0/{phone_id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            data = resp.json()
            if resp.status_code == 200:
                name = data.get("display_phone_number") or data.get("verified_name") or phone_id
                return {"ok": True, "detail": f"Conectado: {name}"}
            error = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            return {"ok": False, "detail": f"Error de Meta: {error}"}
        except Exception as e:
            logger.warning("test_connection whatsapp error: %s", e)
            return {"ok": False, "detail": "Error de red — verificar conexion a internet"}

    if service == "mercadolibre":
        token = dealer.ml_access_token or settings.ml_access_token
        if not token:
            return {"ok": False, "detail": "Token ML no configurado"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.mercadolibre.com/users/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
            data = resp.json()
            if resp.status_code == 200:
                nickname = data.get("nickname") or str(data.get("id", ""))
                return {"ok": True, "detail": f"Conectado como: {nickname}"}
            return {"ok": False, "detail": "Token invalido — refrescar token ML"}
        except Exception as e:
            logger.warning("test_connection mercadolibre error: %s", e)
            return {"ok": False, "detail": "Error de red — verificar conexion a internet"}

    return {"ok": False, "detail": "Servicio desconocido"}
