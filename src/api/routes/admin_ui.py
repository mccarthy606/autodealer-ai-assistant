"""Admin UI - Jinja2 templates. Complete MVP admin panel."""

import csv
import io
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, Response, Cookie, Form
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.auth import (
    create_session, clear_session, remove_session, is_authenticated, _check_password,
)
from src.config import settings
from src.db.models import (
    InventoryItem, Lead, Conversation, Message, Event, Dealership,
    StatusEnum, ConditionEnum, LeadIntentEnum, LeadStatusEnum,
    MessageDirectionEnum,
)
from src.services.conversation_engine import process_message
from src.services.responder import format_car_whatsapp_message
from src.services.handoff_rules import REASON_LABELS, get_reason_label

router = APIRouter(prefix="/admin/ui", tags=["admin-ui"])
logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# === Auth helpers ===

def _auth_check(request: Request) -> Optional[RedirectResponse]:
    session = request.cookies.get("admin_session")
    if not is_authenticated(session):
        return RedirectResponse(url="/admin/ui/login", status_code=302)
    return None


# === Auth routes ===

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if not settings.admin_password:
        return RedirectResponse(url="/admin/ui", status_code=302)
    error = request.query_params.get("error")
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": error})


@router.post("/login")
async def login_submit(request: Request):
    if not settings.admin_password:
        return RedirectResponse(url="/admin/ui", status_code=302)
    form = await request.form()
    password = form.get("password", "")
    if _check_password(password):
        resp = RedirectResponse(url="/admin/ui", status_code=302)
        create_session(resp)
        return resp
    return RedirectResponse(url="/admin/ui/login?error=1", status_code=302)


@router.get("/logout")
async def logout_page(request: Request):
    session = request.cookies.get("admin_session")
    remove_session(session)
    resp = RedirectResponse(url="/admin/ui/login" if settings.admin_password else "/admin/ui", status_code=302)
    clear_session(resp)
    return resp


# === Dashboard ===

@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    did = settings.default_dealership_id
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())

    # Conversations today
    r = await db.execute(select(func.count(Conversation.id)).where(
        Conversation.dealership_id == did,
        Conversation.last_message_at >= today_start,
    ))
    convs_today = r.scalar() or 0

    # Leads today
    r = await db.execute(select(func.count(Lead.id)).where(
        Lead.dealership_id == did,
        Lead.created_at >= today_start,
    ))
    leads_today = r.scalar() or 0

    # Pending handoffs
    r = await db.execute(select(func.count(Conversation.id)).where(
        Conversation.dealership_id == did,
        Conversation.mode == "manager",
    ))
    pending_handoffs = r.scalar() or 0

    # Top searched (from events)
    brand_col = Event.payload["brand"].astext
    try:
        r = await db.execute(
            select(
                brand_col.label("brand"),
                func.count(Event.id).label("cnt"),
            ).where(
                Event.dealership_id == did,
                Event.type == "search_performed",
                Event.created_at >= today_start - timedelta(days=7),
            ).group_by(brand_col)
            .order_by(func.count(Event.id).desc())
            .limit(5)
        )
        top_searches = [{"brand": row.brand, "count": row.cnt} for row in r.all() if row.brand]
    except Exception:
        top_searches = []

    # Cars count
    r = await db.execute(select(func.count(InventoryItem.id)).where(
        InventoryItem.dealership_id == did,
        InventoryItem.status != StatusEnum.sold,
    ))
    cars_available = r.scalar() or 0

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "convs_today": convs_today,
        "leads_today": leads_today,
        "pending_handoffs": pending_handoffs,
        "top_searches": top_searches,
        "cars_available": cars_available,
    })


# === Cars ===

@router.get("/cars", response_class=HTMLResponse)
async def cars_list(request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    did = settings.default_dealership_id
    q = request.query_params.get("q", "").strip()
    status_filter = request.query_params.get("status", "").strip()
    condition_filter = request.query_params.get("condition", "").strip()

    stmt = select(InventoryItem).where(InventoryItem.dealership_id == did)
    if q:
        stmt = stmt.where(
            (InventoryItem.brand.ilike(f"%{q}%")) |
            (InventoryItem.model.ilike(f"%{q}%")) |
            (InventoryItem.trim.ilike(f"%{q}%"))
        )
    if status_filter:
        try:
            stmt = stmt.where(InventoryItem.status == StatusEnum(status_filter))
        except ValueError:
            pass
    if condition_filter:
        try:
            stmt = stmt.where(InventoryItem.condition == ConditionEnum(condition_filter))
        except ValueError:
            pass

    stmt = stmt.order_by(InventoryItem.created_at.desc()).limit(200)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return templates.TemplateResponse("admin/cars.html", {
        "request": request,
        "items": items,
        "filters": {"q": q, "status": status_filter, "condition": condition_filter},
    })


@router.get("/cars/new", response_class=HTMLResponse)
async def car_new(request: Request):
    redir = _auth_check(request)
    if redir:
        return redir
    return templates.TemplateResponse("admin/car_form.html", {
        "request": request,
        "car": None,
        "is_edit": False,
    })


@router.post("/cars/new")
async def car_create(request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    form = await request.form()
    photos = [u.strip() for u in (form.get("photos", "") or "").split("\n") if u.strip()]
    tags = [t.strip() for t in (form.get("tags", "") or "").split(",") if t.strip()]

    try:
        condition = ConditionEnum(form.get("condition", "used"))
    except ValueError:
        condition = ConditionEnum.used

    try:
        status = StatusEnum(form.get("status", "available"))
    except ValueError:
        status = StatusEnum.available

    item = InventoryItem(
        dealership_id=settings.default_dealership_id,
        brand=(form.get("brand") or "").strip(),
        model=(form.get("model") or "").strip(),
        trim=(form.get("trim") or "").strip() or None,
        year=int(form.get("year") or 2024),
        condition=condition,
        km=int(form.get("km") or 0) if form.get("km") else None,
        price=Decimal(form.get("price") or "0"),
        currency=form.get("currency") or "ARS",
        status=status,
        title=(form.get("title") or "").strip() or None,
        description=(form.get("description") or "").strip() or None,
        photos=photos,
        tags=tags,
        ml_item_id=(form.get("ml_item_id") or "").strip() or None,
        location=(form.get("location") or "").strip() or None,
        source="manual",
    )
    db.add(item)
    await db.flush()

    db.add(Event(
        dealership_id=settings.default_dealership_id,
        type="car_created",
        payload={"car_id": item.id},
    ))

    return RedirectResponse(url=f"/admin/ui/cars/{item.id}", status_code=302)


@router.get("/cars/{car_id}", response_class=HTMLResponse)
async def car_detail(car_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    stmt = select(InventoryItem).where(
        InventoryItem.id == car_id,
        InventoryItem.dealership_id == settings.default_dealership_id,
    )
    r = await db.execute(stmt)
    car = r.scalar_one_or_none()
    if not car:
        return RedirectResponse(url="/admin/ui/cars", status_code=302)

    wa_msg_es = format_car_whatsapp_message({
        "brand": car.brand, "model": car.model, "trim": car.trim, "year": car.year,
        "price": float(car.price), "currency": car.currency, "km": car.km,
        "condition": car.condition.value, "location": car.location,
    }, "es")
    wa_msg_en = format_car_whatsapp_message({
        "brand": car.brand, "model": car.model, "trim": car.trim, "year": car.year,
        "price": float(car.price), "currency": car.currency, "km": car.km,
        "condition": car.condition.value, "location": car.location,
    }, "en")

    return templates.TemplateResponse("admin/car_detail.html", {
        "request": request,
        "car": car,
        "wa_msg_es": wa_msg_es,
        "wa_msg_en": wa_msg_en,
    })


@router.get("/cars/{car_id}/edit", response_class=HTMLResponse)
async def car_edit(car_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    stmt = select(InventoryItem).where(InventoryItem.id == car_id)
    r = await db.execute(stmt)
    car = r.scalar_one_or_none()
    if not car:
        return RedirectResponse(url="/admin/ui/cars", status_code=302)

    return templates.TemplateResponse("admin/car_form.html", {
        "request": request,
        "car": car,
        "is_edit": True,
    })


@router.post("/cars/{car_id}/edit")
async def car_update(car_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    stmt = select(InventoryItem).where(InventoryItem.id == car_id)
    r = await db.execute(stmt)
    car = r.scalar_one_or_none()
    if not car:
        return RedirectResponse(url="/admin/ui/cars", status_code=302)

    form = await request.form()
    car.brand = (form.get("brand") or car.brand).strip()
    car.model = (form.get("model") or car.model).strip()
    car.trim = (form.get("trim") or "").strip() or None
    car.year = int(form.get("year") or car.year)
    car.km = int(form.get("km") or 0) if form.get("km") else None
    car.price = Decimal(form.get("price") or str(car.price))
    car.currency = form.get("currency") or "ARS"
    car.title = (form.get("title") or "").strip() or None
    car.description = (form.get("description") or "").strip() or None
    car.photos = [u.strip() for u in (form.get("photos", "") or "").split("\n") if u.strip()]
    car.tags = [t.strip() for t in (form.get("tags", "") or "").split(",") if t.strip()]
    car.ml_item_id = (form.get("ml_item_id") or "").strip() or None
    car.location = (form.get("location") or "").strip() or None

    try:
        car.condition = ConditionEnum(form.get("condition", car.condition.value))
    except ValueError:
        pass
    try:
        car.status = StatusEnum(form.get("status", car.status.value))
    except ValueError:
        pass

    car.updated_at = datetime.utcnow()
    return RedirectResponse(url=f"/admin/ui/cars/{car_id}", status_code=302)


@router.post("/cars/{car_id}/sold")
async def car_mark_sold(car_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    stmt = select(InventoryItem).where(InventoryItem.id == car_id)
    r = await db.execute(stmt)
    car = r.scalar_one_or_none()
    if car:
        car.status = StatusEnum.sold
        car.updated_at = datetime.utcnow()
    return RedirectResponse(url=f"/admin/ui/cars/{car_id}", status_code=302)


@router.post("/cars/{car_id}/duplicate")
async def car_duplicate(car_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    stmt = select(InventoryItem).where(InventoryItem.id == car_id)
    r = await db.execute(stmt)
    car = r.scalar_one_or_none()
    if not car:
        return RedirectResponse(url="/admin/ui/cars", status_code=302)

    new_car = InventoryItem(
        dealership_id=car.dealership_id,
        brand=car.brand, model=car.model, trim=car.trim,
        year=car.year, condition=car.condition, km=car.km,
        price=car.price, currency=car.currency, status=StatusEnum.available,
        title=car.title, description=car.description,
        photos=list(car.photos or []), tags=list(car.tags or []),
        location=car.location, source="manual",
    )
    db.add(new_car)
    await db.flush()
    return RedirectResponse(url=f"/admin/ui/cars/{new_car.id}/edit", status_code=302)


# === Leads ===

@router.get("/leads", response_class=HTMLResponse)
async def leads_page(request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    did = settings.default_dealership_id
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


# === Conversations ===

@router.get("/conversations", response_class=HTMLResponse)
async def conversations_page(request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    did = settings.default_dealership_id
    stmt = (
        select(Conversation)
        .where(Conversation.dealership_id == did)
        .order_by(Conversation.last_message_at.desc())
        .limit(200)
    )
    result = await db.execute(stmt)
    conversations = result.scalars().all()

    # Get last message for each conversation
    conv_data = []
    for c in conversations:
        last_msg_stmt = select(Message).where(
            Message.conversation_id == c.id
        ).order_by(Message.created_at.desc()).limit(1)
        msg_r = await db.execute(last_msg_stmt)
        last_msg = msg_r.scalar_one_or_none()
        conv_data.append({
            "conv": c,
            "last_msg": last_msg.text[:80] if last_msg and last_msg.text else "",
            "last_dir": last_msg.direction.value if last_msg else "",
        })

    return templates.TemplateResponse("admin/conversations.html", {
        "request": request,
        "conv_data": conv_data,
    })


@router.get("/conversations/{conv_id}", response_class=HTMLResponse)
async def conversation_detail(conv_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    stmt = select(Conversation).where(
        Conversation.id == conv_id,
        Conversation.dealership_id == settings.default_dealership_id,
    )
    r = await db.execute(stmt)
    conv = r.scalar_one_or_none()
    if not conv:
        return RedirectResponse(url="/admin/ui/conversations", status_code=302)

    msg_stmt = select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at)
    msg_r = await db.execute(msg_stmt)
    messages = msg_r.scalars().all()

    reason_label = get_reason_label(conv.handoff_reason, conv.state.get("language", "es") if conv.state else "es")

    return templates.TemplateResponse("admin/conversation_detail.html", {
        "request": request,
        "conv": conv,
        "messages": messages,
        "reason_label": reason_label,
    })


@router.post("/conversations/{conv_id}/send")
async def conversation_send(conv_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Manager sends a message from the inbox."""
    redir = _auth_check(request)
    if redir:
        return redir

    form = await request.form()
    text = (form.get("text") or "").strip()
    if not text:
        return RedirectResponse(url=f"/admin/ui/conversations/{conv_id}", status_code=302)

    stmt = select(Conversation).where(Conversation.id == conv_id)
    r = await db.execute(stmt)
    conv = r.scalar_one_or_none()
    if not conv:
        return RedirectResponse(url="/admin/ui/conversations", status_code=302)

    msg = Message(
        conversation_id=conv.id,
        direction=MessageDirectionEnum.outbound,
        text=text,
        channel=conv.channel,
    )
    db.add(msg)
    conv.last_message_at = datetime.utcnow()

    # TODO: Send via channel adapter (WhatsApp/ML) if configured
    # For now: saved to DB, visible in conversation

    return RedirectResponse(url=f"/admin/ui/conversations/{conv_id}", status_code=302)


@router.post("/conversations/{conv_id}/takeover")
async def conversation_takeover(conv_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Switch to manager mode."""
    redir = _auth_check(request)
    if redir:
        return redir

    stmt = select(Conversation).where(Conversation.id == conv_id)
    r = await db.execute(stmt)
    conv = r.scalar_one_or_none()
    if conv:
        conv.mode = "manager"
        conv.handoff_reason = "manual_takeover"
        conv.last_handoff_at = datetime.utcnow()
    return RedirectResponse(url=f"/admin/ui/conversations/{conv_id}", status_code=302)


@router.post("/conversations/{conv_id}/return-bot")
async def conversation_return_bot(conv_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Return to bot mode."""
    redir = _auth_check(request)
    if redir:
        return redir

    stmt = select(Conversation).where(Conversation.id == conv_id)
    r = await db.execute(stmt)
    conv = r.scalar_one_or_none()
    if conv:
        conv.mode = "bot"
        conv.handoff_reason = None
        state = dict(conv.state or {})
        state["stage"] = "BROWSING"
        state["unhelpful_count"] = 0
        conv.state = state
    return RedirectResponse(url=f"/admin/ui/conversations/{conv_id}", status_code=302)


# === Settings ===

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    stmt = select(Dealership).where(Dealership.id == settings.default_dealership_id)
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
    redir = _auth_check(request)
    if redir:
        return redir

    form = await request.form()
    stmt = select(Dealership).where(Dealership.id == settings.default_dealership_id)
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
    redir = _auth_check(request)
    if redir:
        return redir

    wa_configured = bool(settings.whatsapp_cloud_token and settings.whatsapp_phone_number_id)
    ml_configured = bool(settings.ml_access_token and settings.ml_user_id)

    # ML linked cars
    stmt = select(InventoryItem).where(
        InventoryItem.dealership_id == settings.default_dealership_id,
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


# === ML Import by URL ===

@router.post("/cars/import-ml-url")
async def import_ml_url(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Import a car from a MercadoLibre URL.
    Parses the URL for MLA ID + brand/model from slug,
    then redirects to the car form pre-filled with data.
    """
    redir = _auth_check(request)
    if redir:
        return redir

    form = await request.form()
    ml_url = (form.get("ml_url") or "").strip()
    if not ml_url:
        return RedirectResponse(url="/admin/ui/cars?error=no_url", status_code=302)

    from src.adapters.mercadolibre import parse_ml_url

    parsed = parse_ml_url(ml_url)
    if not parsed:
        return RedirectResponse(url="/admin/ui/cars?error=invalid_url", status_code=302)

    did = settings.default_dealership_id
    ml_id = parsed["ml_item_id"]

    # Check if already exists
    stmt = select(InventoryItem).where(
        InventoryItem.dealership_id == did,
        InventoryItem.ml_item_id == ml_id,
    )
    r = await db.execute(stmt)
    existing = r.scalar_one_or_none()
    if existing:
        return RedirectResponse(url=f"/admin/ui/cars/{existing.id}/edit?info=already_exists", status_code=302)

    # Redirect to the new car form, pre-filled via query params
    from urllib.parse import urlencode
    params = urlencode({
        "brand": parsed.get("brand", ""),
        "model": parsed.get("model", ""),
        "trim": parsed.get("trim", ""),
        "ml_item_id": ml_id,
        "ml_url": parsed.get("permalink", ml_url),
    })
    return RedirectResponse(url=f"/admin/ui/cars/new?{params}", status_code=302)


@router.post("/cars/import-ml-url-save")
async def import_ml_url_save(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Save a car imported from ML URL. Receives full form data.
    """
    redir = _auth_check(request)
    if redir:
        return redir

    form = await request.form()
    did = settings.default_dealership_id

    brand = (form.get("brand") or "").strip()
    model_name = (form.get("model") or "").strip()
    trim = (form.get("trim") or "").strip()
    year = int(form.get("year") or 0) or 0
    km = int(form.get("km") or 0) or None
    price = form.get("price", "0").strip().replace(",", "").replace(".", "")
    try:
        price_dec = Decimal(price) if price else Decimal(0)
    except Exception:
        price_dec = Decimal(0)

    condition = form.get("condition", "used")
    try:
        cond = ConditionEnum(condition)
    except ValueError:
        cond = ConditionEnum.used

    photos_raw = (form.get("photos") or "").strip()
    photos = [url.strip() for url in photos_raw.split("\n") if url.strip().startswith("http")]

    ml_item_id = (form.get("ml_item_id") or "").strip()
    description = (form.get("description") or "").strip()
    location = (form.get("location") or "").strip()
    ml_url = (form.get("ml_url") or "").strip()

    # Build title
    title = f"{brand} {model_name} {trim}".strip() or f"Car {ml_item_id}"

    # Check if already exists
    if ml_item_id:
        stmt = select(InventoryItem).where(
            InventoryItem.dealership_id == did,
            InventoryItem.ml_item_id == ml_item_id,
        )
        r = await db.execute(stmt)
        existing = r.scalar_one_or_none()
        if existing:
            # Update
            existing.brand = brand or existing.brand
            existing.model = model_name or existing.model
            existing.trim = trim or existing.trim
            existing.year = year or existing.year
            existing.km = km or existing.km
            existing.price = price_dec or existing.price
            existing.condition = cond
            existing.photos = photos or existing.photos
            existing.title = title
            existing.description = description or existing.description
            existing.location = location or existing.location
            existing.updated_at = datetime.utcnow()
            await db.flush()
            return RedirectResponse(url=f"/admin/ui/cars/{existing.id}?saved=1", status_code=302)

    car = InventoryItem(
        dealership_id=did,
        brand=brand,
        model=model_name,
        trim=trim,
        year=year,
        km=km,
        price=price_dec,
        currency="ARS",
        condition=cond,
        status=StatusEnum.available,
        photos=photos,
        title=title,
        description=description or f"MercadoLibre: {ml_item_id}",
        location=location,
        ml_item_id=ml_item_id or None,
        source="mercadolibre" if ml_item_id else "manual",
        tags=["mercadolibre"] if ml_item_id else [],
    )
    db.add(car)
    await db.flush()

    return RedirectResponse(url=f"/admin/ui/cars/{car.id}?saved=1", status_code=302)


# === Test Chat ===

@router.get("/test", response_class=HTMLResponse)
async def test_chat_page(request: Request):
    redir = _auth_check(request)
    if redir:
        return redir
    return templates.TemplateResponse("admin/test_chat.html", {"request": request})


@router.post("/test/send")
async def test_chat_send(request: Request, db: AsyncSession = Depends(get_db)):
    """Process test message through conversation engine."""
    session_cookie = request.cookies.get("admin_session")
    if not is_authenticated(session_cookie):
        return {"error": "not_authenticated"}

    body = await request.json()
    phone = body.get("phone", "+5491100000000")
    text = body.get("text", "")
    channel = body.get("channel", "admin_test")

    if not text.strip():
        return {"error": "empty message"}

    try:
        result = await process_message(
            session=db,
            dealership_id=settings.default_dealership_id,
            phone=phone,
            text=text,
            channel=channel,
        )
        return result.to_dict()
    except Exception as e:
        logger.exception("Test chat error: %s", e)
        await db.rollback()
        return {"error": str(e), "text": f"Error: {e}", "intent": "ERROR", "mode": "bot",
                "stage": "ERROR", "matched_cars": [], "photo_urls": [], "state": {}}


# === Metrics ===

@router.get("/metrics", response_class=HTMLResponse)
async def metrics_page(request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    did = settings.default_dealership_id
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())

    # Conversations today
    r = await db.execute(select(func.count(Conversation.id)).where(
        Conversation.dealership_id == did,
        Conversation.last_message_at >= today_start,
    ))
    convs_today = r.scalar() or 0

    # Leads today
    r = await db.execute(select(func.count(Lead.id)).where(
        Lead.dealership_id == did,
        Lead.created_at >= today_start,
    ))
    leads_today = r.scalar() or 0

    # Leads by source
    r = await db.execute(
        select(Lead.source, func.count(Lead.id))
        .where(Lead.dealership_id == did)
        .group_by(Lead.source)
    )
    leads_by_source = [{"source": row[0] or "unknown", "count": row[1]} for row in r.all()]

    # Top searched models (last 7 days)
    model_col = Event.payload["model"].astext
    brand_col = Event.payload["brand"].astext
    try:
        r = await db.execute(
            select(
                model_col.label("model"),
                brand_col.label("brand"),
                func.count(Event.id).label("cnt"),
            ).where(
                Event.dealership_id == did,
                Event.type == "search_performed",
                Event.created_at >= today_start - timedelta(days=7),
            ).group_by(model_col, brand_col)
            .order_by(func.count(Event.id).desc())
            .limit(10)
        )
        top_searches = [{"brand": row.brand or "?", "model": row.model or "?", "count": row.cnt} for row in r.all()]
    except Exception:
        top_searches = []

    # Handoffs today
    r = await db.execute(select(func.count(Event.id)).where(
        Event.dealership_id == did,
        Event.type == "handoff",
        Event.created_at >= today_start,
    ))
    handoffs_today = r.scalar() or 0

    # Conversion rate
    r = await db.execute(select(func.count(Conversation.id)).where(Conversation.dealership_id == did))
    total_convs = r.scalar() or 1
    r = await db.execute(select(func.count(Lead.id)).where(Lead.dealership_id == did))
    total_leads = r.scalar() or 0
    conversion = round(total_leads / total_convs * 100, 1) if total_convs else 0

    return templates.TemplateResponse("admin/metrics.html", {
        "request": request,
        "convs_today": convs_today,
        "leads_today": leads_today,
        "leads_by_source": leads_by_source,
        "top_searches": top_searches,
        "handoffs_today": handoffs_today,
        "conversion": conversion,
    })


# === CSV Import (kept for backward compat) ===

@router.post("/cars/import")
async def cars_import(request: Request, db: AsyncSession = Depends(get_db)):
    redir = _auth_check(request)
    if redir:
        return redir

    form = await request.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        return RedirectResponse(url="/admin/ui/cars?error=no_file", status_code=302)

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    added = 0

    for row in reader:
        brand = (row.get("brand") or row.get("marca") or "").strip()
        model_name = (row.get("model") or row.get("modelo") or "").strip()
        year_str = row.get("year") or row.get("año") or row.get("anio") or ""
        price_str = row.get("price") or row.get("precio") or ""
        if not brand or not model_name:
            continue
        try:
            year = int(year_str)
            price = Decimal(price_str.replace(",", "").replace("$", "").strip())
        except (ValueError, TypeError):
            continue

        item = InventoryItem(
            dealership_id=settings.default_dealership_id,
            brand=brand, model=model_name, year=year, price=price,
            condition=ConditionEnum.used, status=StatusEnum.available,
            currency="ARS", source="csv",
        )
        db.add(item)
        added += 1

    return RedirectResponse(url=f"/admin/ui/cars?imported={added}", status_code=302)
