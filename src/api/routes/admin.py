"""Admin API routes."""

from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.auth import is_authenticated, get_admin_did
from src.db.models import (
    Dealership,
    InventoryItem,
    Conversation,
    Message,
    Lead,
    Event,
    ConditionEnum,
    StatusEnum,
    LeadStatusEnum,
)
async def _require_admin(admin_session: str = Cookie(default=None)) -> None:
    """Dependency: rejects unauthenticated callers with 401."""
    if not await is_authenticated(admin_session):
        raise HTTPException(status_code=401, detail="Not authenticated")


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(_require_admin)],
)


# --- Schemas ---
class DealershipCreate(BaseModel):
    name: str
    timezone: str = "America/Argentina/Buenos_Aires"
    default_language: str = "es"
    address: Optional[str] = None
    phone: Optional[str] = None


class InventoryItemCreate(BaseModel):
    brand: str
    model: str
    trim: Optional[str] = None
    year: int
    condition: str
    km: Optional[int] = None
    price: float
    currency: str = "ARS"
    status: str = "available"
    location: Optional[str] = None
    vin: Optional[str] = None
    external_id: Optional[str] = None
    source: str = "manual"


# --- Endpoints ---
@router.post("/dealerships")
async def create_dealership(
    data: DealershipCreate,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    d = Dealership(
        name=data.name,
        timezone=data.timezone,
        default_language=data.default_language,
        address=data.address,
        phone=data.phone,
    )
    session.add(d)
    await session.flush()
    return {"id": d.id, "name": d.name}


@router.get("/inventory")
async def list_inventory(
    session: AsyncSession = Depends(get_db),
    did: int = Depends(get_admin_did),
    status: Optional[str] = None,
    limit: int = Query(100, le=500),
) -> dict[str, Any]:
    stmt = select(InventoryItem).where(InventoryItem.dealership_id == did)
    if status:
        stmt = stmt.where(InventoryItem.status == StatusEnum(status))
    stmt = stmt.order_by(InventoryItem.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    items = result.scalars().all()
    return {
        "items": [
            {
                "id": i.id,
                "brand": i.brand,
                "model": i.model,
                "year": i.year,
                "condition": i.condition.value,
                "km": i.km,
                "price": float(i.price),
                "status": i.status.value,
            }
            for i in items
        ],
    }


@router.post("/inventory")
async def create_inventory_item(
    data: InventoryItemCreate,
    session: AsyncSession = Depends(get_db),
    did: int = Depends(get_admin_did),
) -> dict[str, Any]:
    item = InventoryItem(
        dealership_id=did,
        brand=data.brand,
        model=data.model,
        trim=data.trim,
        year=data.year,
        condition=ConditionEnum(data.condition),
        km=data.km,
        price=Decimal(str(data.price)),
        currency=data.currency,
        status=StatusEnum(data.status),
        location=data.location,
        vin=data.vin,
        external_id=data.external_id,
        source=data.source,
    )
    session.add(item)
    await session.flush()
    return {"id": item.id, "brand": item.brand, "model": item.model}


@router.get("/leads")
async def list_leads(
    session: AsyncSession = Depends(get_db),
    did: int = Depends(get_admin_did),
    status: Optional[str] = None,
    limit: int = Query(100, le=500),
) -> dict[str, Any]:
    stmt = select(Lead).where(Lead.dealership_id == did)
    if status:
        stmt = stmt.where(Lead.status == LeadStatusEnum(status))
    stmt = stmt.order_by(Lead.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    leads = result.scalars().all()
    return {
        "leads": [
            {
                "id": l.id,
                "phone": l.phone,
                "name": l.name,
                "intent": l.intent.value,
                "status": l.status.value,
                "created_at": l.created_at.isoformat(),
            }
            for l in leads
        ],
    }


@router.get("/conversations/{conv_id}")
async def get_conversation(
    conv_id: int,
    session: AsyncSession = Depends(get_db),
    did: int = Depends(get_admin_did),
) -> dict[str, Any]:
    stmt = select(Conversation).where(
        Conversation.id == conv_id,
        Conversation.dealership_id == did,
    )
    result = await session.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        return {"error": "not_found"}

    msg_stmt = select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at)
    msg_res = await session.execute(msg_stmt)
    messages = msg_res.scalars().all()

    return {
        "id": conv.id,
        "user_phone": conv.user_phone,
        "state": conv.state,
        "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
        "messages": [
            {
                "direction": m.direction.value,
                "text": m.text,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.get("/metrics")
async def get_metrics(
    session: AsyncSession = Depends(get_db),
    did: int = Depends(get_admin_did),
) -> dict[str, Any]:

    # Conversations per day (last 7 days)
    from datetime import UTC, datetime, timedelta
    today = datetime.now(UTC).date()
    conv_per_day = []
    for i in range(7):
        d = today - timedelta(days=i)
        stmt = select(func.count(Conversation.id)).where(
            Conversation.dealership_id == did,
            func.date(Conversation.last_message_at) == d,
        )
        r = await session.execute(stmt)
        conv_per_day.append({"date": str(d), "count": r.scalar() or 0})

    # Leads per day
    leads_per_day = []
    for i in range(7):
        d = today - timedelta(days=i)
        stmt = select(func.count(Lead.id)).where(
            Lead.dealership_id == did,
            func.date(Lead.created_at) == d,
        )
        r = await session.execute(stmt)
        leads_per_day.append({"date": str(d), "count": r.scalar() or 0})

    # Top brands
    stmt = (
        select(InventoryItem.brand, func.count(InventoryItem.id))
        .where(InventoryItem.dealership_id == did, InventoryItem.status != StatusEnum.sold)
        .group_by(InventoryItem.brand)
        .order_by(func.count(InventoryItem.id).desc())
        .limit(10)
    )
    r = await session.execute(stmt)
    top_brands = [{"brand": row[0], "count": row[1]} for row in r.all()]

    return {
        "conversations_per_day": conv_per_day,
        "leads_per_day": leads_per_day,
        "top_brands": top_brands,
    }
