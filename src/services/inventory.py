"""Inventory search and management service."""

from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import InventoryItem, ConditionEnum, StatusEnum


class InventoryService:
    """Service for searching and managing inventory."""

    @staticmethod
    async def search(
        session: AsyncSession,
        dealership_id: int,
        *,
        brand: Optional[str] = None,
        model: Optional[str] = None,
        year: Optional[int] = None,
        condition: Optional[str] = None,
        status: Optional[str] = None,
        budget_min: Optional[float] = None,
        budget_max: Optional[float] = None,
        max_km: Optional[int] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search inventory with filters. Returns up to `limit` items as dicts."""
        conditions = [
            InventoryItem.dealership_id == dealership_id,
            InventoryItem.status != StatusEnum.sold,
        ]

        if brand:
            conditions.append(InventoryItem.brand.ilike(f"%{brand}%"))
        if model:
            conditions.append(InventoryItem.model.ilike(f"%{model}%"))
        if year:
            conditions.append(InventoryItem.year == year)
        if condition:
            try:
                cond_enum = ConditionEnum(condition.replace(" ", "_").lower())
                conditions.append(InventoryItem.condition == cond_enum)
            except ValueError:
                pass
        if status:
            try:
                status_enum = StatusEnum(status.replace(" ", "_").lower())
                conditions.append(InventoryItem.status == status_enum)
            except ValueError:
                pass
        if budget_min is not None:
            conditions.append(InventoryItem.price >= Decimal(str(budget_min)))
        if budget_max is not None:
            conditions.append(InventoryItem.price <= Decimal(str(budget_max)))
        if max_km is not None:
            conditions.append(
                or_(
                    InventoryItem.km.is_(None),
                    InventoryItem.km <= max_km,
                )
            )

        stmt = (
            select(InventoryItem)
            .where(and_(*conditions))
            .order_by(InventoryItem.price.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        return [
            {
                "id": i.id,
                "brand": i.brand,
                "model": i.model,
                "trim": i.trim,
                "year": i.year,
                "condition": i.condition.value,
                "km": i.km,
                "price": float(i.price),
                "currency": i.currency,
                "status": i.status.value,
                "location": i.location,
                "photos": i.photos or [],
                "description": i.description,
                "title": i.display_title,
                "tags": i.tags or [],
            }
            for i in items
        ]

    @staticmethod
    async def get_by_id(session: AsyncSession, item_id: int) -> Optional[dict[str, Any]]:
        """Get single inventory item by ID."""
        stmt = select(InventoryItem).where(InventoryItem.id == item_id)
        r = await session.execute(stmt)
        i = r.scalar_one_or_none()
        if not i:
            return None
        return {
            "id": i.id,
            "brand": i.brand,
            "model": i.model,
            "trim": i.trim,
            "year": i.year,
            "condition": i.condition.value,
            "km": i.km,
            "price": float(i.price),
            "currency": i.currency,
            "status": i.status.value,
            "location": i.location,
            "photos": i.photos or [],
            "description": i.description,
            "title": i.display_title,
            "tags": i.tags or [],
        }
