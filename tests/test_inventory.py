"""Tests for InventoryService."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.inventory import InventoryService
from src.db.models import InventoryItem, Dealership, ConditionEnum, StatusEnum


@pytest.mark.asyncio
async def test_search_by_brand(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    items = await InventoryService.search(db_session, dealership_id=dealership.id, brand="Toyota")
    assert len(items) >= 1
    assert all(i["brand"] == "Toyota" for i in items)


@pytest.mark.asyncio
async def test_search_by_model(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    items = await InventoryService.search(db_session, dealership_id=dealership.id, model="Hilux")
    assert len(items) >= 1
    assert all("Hilux" in i["model"] for i in items)


@pytest.mark.asyncio
async def test_search_by_budget(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    items = await InventoryService.search(
        db_session, dealership_id=dealership.id,
        budget_min=10_000_000, budget_max=20_000_000,
    )
    assert len(items) >= 1
    for i in items:
        assert 10_000_000 <= i["price"] <= 20_000_000


@pytest.mark.asyncio
async def test_search_returns_photos(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    items = await InventoryService.search(db_session, dealership_id=dealership.id, brand="Toyota")
    assert len(items) >= 1
    assert "photos" in items[0]
    assert len(items[0]["photos"]) > 0


@pytest.mark.asyncio
async def test_search_empty_dealership(db_session: AsyncSession, dealership: Dealership):
    items = await InventoryService.search(db_session, dealership_id=999, limit=5)
    assert items == []


@pytest.mark.asyncio
async def test_search_limit(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    items = await InventoryService.search(db_session, dealership_id=dealership.id, limit=1)
    assert len(items) <= 1
