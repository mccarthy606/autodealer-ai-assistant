"""Admin dashboard routes -- home, auth, test chat, metrics."""

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.rate_limit import check_rate_limit
import bcrypt
from sqlalchemy import select

from src.api.auth import (
    create_session, clear_session, remove_session, _check_password,
)
from src.api.routes.admin_common import auth_check, templates
from src.config import settings
from src.db.models import (
    Dealership, InventoryItem, Lead, Conversation, Event,
    StatusEnum, LeadIntentEnum, LeadStatusEnum, Message, MessageDirectionEnum,
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
async def login_submit(request: Request, db: AsyncSession = Depends(get_db)):
    # Rate limit: 5 attempts per 60s per IP (per D-08)
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = await check_rate_limit(
        key=client_ip, limit=5, window_seconds=60, prefix="rate:login"
    )
    if not allowed:
        return JSONResponse(
            {"error": "rate limited"},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )

    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", "")).strip()

    # Try per-dealership login first (D-05)
    if username:
        stmt = select(Dealership).where(Dealership.admin_username == username)
        result = await db.execute(stmt)
        dealer = result.scalar_one_or_none()
        if dealer and dealer.admin_password_hash and bcrypt.checkpw(
            password.encode("utf-8"), dealer.admin_password_hash.encode("utf-8")
        ):
            resp = RedirectResponse(url="/admin/ui", status_code=302)
            await create_session(resp, dealer.id)
            return resp

    # Superadmin fallback: settings-level password, dealership_id=default (D-08)
    if not settings.admin_password and not settings.admin_password_hash:
        resp = RedirectResponse(url="/admin/ui", status_code=302)
        await create_session(resp, settings.default_dealership_id)
        return resp

    if _check_password(password):
        resp = RedirectResponse(url="/admin/ui", status_code=302)
        await create_session(resp, settings.default_dealership_id)
        return resp

    return RedirectResponse(url="/admin/ui/login?error=1", status_code=302)


@router.get("/logout")
async def logout_page(request: Request):
    session = request.cookies.get("admin_session")
    await remove_session(session)
    resp = RedirectResponse(url="/admin/ui/login" if settings.admin_password else "/admin/ui", status_code=302)
    clear_session(resp)
    return resp


# === Dashboard ===

@router.get("", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    did = await auth_check(request)
    if not isinstance(did, int):
        return did
    today = datetime.now(UTC).date()
    today_start = datetime.combine(today, datetime.min.time())

    # Active conversations (bot mode, last 7 days)
    seven_days_ago = datetime.now(UTC) - timedelta(days=7)
    r = await db.execute(select(func.count(Conversation.id)).where(
        Conversation.dealership_id == did,
        Conversation.mode == "bot",
        Conversation.last_message_at >= seven_days_ago,
    ))
    active_conversations = r.scalar() or 0

    # Leads today
    r = await db.execute(select(func.count(Lead.id)).where(
        Lead.dealership_id == did,
        Lead.created_at >= today_start,
    ))
    leads_today = r.scalar() or 0

    # Pending visits
    r = await db.execute(select(func.count(Lead.id)).where(
        Lead.dealership_id == did,
        Lead.intent == LeadIntentEnum.visit,
        Lead.status.in_([LeadStatusEnum.new, LeadStatusEnum.qualified]),
    ))
    pending_visits = r.scalar() or 0

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
        "active_conversations": active_conversations,
        "leads_today": leads_today,
        "pending_visits": pending_visits,
        "top_searches": top_searches,
        "cars_available": cars_available,
    })


# === Test Chat ===

@router.get("/test", response_class=HTMLResponse)
async def test_chat_page(request: Request):
    did = await auth_check(request)
    if not isinstance(did, int):
        return did
    return templates.TemplateResponse("admin/test_chat.html", {"request": request})


@router.post("/test/send")
async def test_chat_send(request: Request, db: AsyncSession = Depends(get_db)):
    """Process test message through conversation engine."""
    did = await auth_check(request)
    if not isinstance(did, int):
        return did

    body = await request.json()
    phone = body.get("phone", "+5491100000000")
    text = body.get("text", "")
    channel = body.get("channel", "admin_test")

    if not text.strip():
        return {"error": "empty message"}

    try:
        result = await process_message(
            session=db,
            dealership_id=did,
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
    did = await auth_check(request)
    if not isinstance(did, int):
        return did
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

    # Avg bot response time (last 30 days, Python-side computation, per D-07/D-08/D-13)
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    r = await db.execute(
        select(Conversation.id).where(Conversation.dealership_id == did)
    )
    conv_ids = [row[0] for row in r.all()]
    avg_response_str = "\u2014"
    if conv_ids:
        r = await db.execute(
            select(Message.conversation_id, Message.direction, Message.created_at)
            .where(
                Message.conversation_id.in_(conv_ids),
                Message.created_at >= thirty_days_ago,
            )
            .order_by(Message.conversation_id, Message.created_at)
        )
        rows = r.all()
        by_conv: dict = defaultdict(list)
        for conv_id, direction, created_at in rows:
            by_conv[conv_id].append((direction, created_at))
        deltas: list = []
        for msgs in by_conv.values():
            i = 0
            while i < len(msgs):
                if msgs[i][0] == MessageDirectionEnum.inbound:
                    j = i + 1
                    while j < len(msgs) and msgs[j][0] != MessageDirectionEnum.outbound:
                        j += 1
                    if j < len(msgs):
                        delta = (msgs[j][1] - msgs[i][1]).total_seconds()
                        if delta >= 0:
                            deltas.append(delta)
                    i = j + 1
                else:
                    i += 1
        if deltas:
            avg_secs = sum(deltas) / len(deltas)
            if avg_secs < 60:
                avg_response_str = f"{int(avg_secs)}s"
            else:
                mins = int(avg_secs // 60)
                secs = int(avg_secs % 60)
                avg_response_str = f"{mins}m {secs}s"

    return templates.TemplateResponse("admin/metrics.html", {
        "request": request,
        "convs_today": convs_today,
        "leads_today": leads_today,
        "leads_by_source": leads_by_source,
        "top_searches": top_searches,
        "handoffs_today": handoffs_today,
        "conversion": conversion,
        "avg_response_str": avg_response_str,
    })
