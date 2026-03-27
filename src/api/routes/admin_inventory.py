"""Admin inventory routes -- car CRUD, CSV import, ML URL import."""

import csv
import io
import logging
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.routes.admin_common import auth_check, templates
from src.config import settings
from src.db.models import (
    InventoryItem, Event,
    StatusEnum, ConditionEnum,
)
from src.services.responder import format_car_whatsapp_message

router = APIRouter(prefix="/admin/ui", tags=["admin-ui"])
logger = logging.getLogger(__name__)


# --- Car List ---

@router.get("/cars", response_class=HTMLResponse)
async def cars_list(request: Request, db: AsyncSession = Depends(get_db)):
    redir = auth_check(request)
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


# --- Car Create ---

@router.get("/cars/new", response_class=HTMLResponse)
async def car_new(request: Request):
    redir = auth_check(request)
    if redir:
        return redir
    return templates.TemplateResponse("admin/car_form.html", {
        "request": request,
        "car": None,
        "is_edit": False,
    })


@router.post("/cars/new")
async def car_create(request: Request, db: AsyncSession = Depends(get_db)):
    redir = auth_check(request)
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


# --- Car Detail ---

@router.get("/cars/{car_id}", response_class=HTMLResponse)
async def car_detail(car_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    redir = auth_check(request)
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


# --- Car Edit ---

@router.get("/cars/{car_id}/edit", response_class=HTMLResponse)
async def car_edit(car_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    redir = auth_check(request)
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
    redir = auth_check(request)
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


# --- Car Actions ---

@router.post("/cars/{car_id}/sold")
async def car_mark_sold(car_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    redir = auth_check(request)
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
    redir = auth_check(request)
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


# --- CSV Import ---

@router.post("/cars/import")
async def cars_import(request: Request, db: AsyncSession = Depends(get_db)):
    redir = auth_check(request)
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


# --- ML Import by URL ---

@router.post("/cars/import-ml-url")
async def import_ml_url(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Import a car from a MercadoLibre URL.
    Parses the URL for MLA ID + brand/model from slug,
    then redirects to the car form pre-filled with data.
    """
    redir = auth_check(request)
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
    redir = auth_check(request)
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
