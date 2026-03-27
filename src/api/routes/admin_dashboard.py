"""Admin dashboard routes -- home, auth, test chat, metrics."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.auth import (
    create_session, clear_session, remove_session, is_authenticated, _check_password,
)
from src.api.routes.admin_common import auth_check, templates
from src.config import settings
from src.db.models import (
    InventoryItem, Lead, Conversation, Event,
    StatusEnum,
)
from src.services.conversation_engine import process_message

router = APIRouter(prefix="/admin/ui", tags=["admin-ui"])
logger = logging.getLogger(__name__)


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
    redir = auth_check(request)
    if redir:
        return redir

    did = settings.default_dealership_id
    today = datetime.now(UTC).date()
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


# === Test Chat ===

@router.get("/test", response_class=HTMLResponse)
async def test_chat_page(request: Request):
    redir = auth_check(request)
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
    redir = auth_check(request)
    if redir:
        return redir

    did = settings.default_dealership_id
    today = datetime.now(UTC).date()
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
