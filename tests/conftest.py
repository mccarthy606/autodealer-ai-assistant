"""Test fixtures."""

import asyncio
import json
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event, text, JSON
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB

from src.db.session import Base
from src.db.models import *  # noqa - import all models


# Use SQLite for tests (async via aiosqlite)
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


# Map PostgreSQL JSONB to generic JSON for SQLite compatibility
from sqlalchemy.ext.compiler import compiles

@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with SQLite."""
    engine = create_async_engine(TEST_DB_URL, echo=False, json_serializer=json.dumps, json_deserializer=json.loads)

    # SQLite JSON support
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_json(dbapi_conn, connection_record):
        # Enable JSON functions in SQLite
        pass

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def dealership(db_session: AsyncSession) -> Dealership:
    """Create a test dealership."""
    d = Dealership(
        id=1,
        name="Test Dealership",
        address="Av. Test 123, CABA",
        business_hours="Lun-Vie 9-18",
        timezone="America/Argentina/Buenos_Aires",
        default_language="es-AR",
    )
    db_session.add(d)
    await db_session.flush()
    return d


@pytest_asyncio.fixture
async def sample_car(db_session: AsyncSession, dealership: Dealership) -> InventoryItem:
    """Create a sample car with photos."""
    car = InventoryItem(
        dealership_id=dealership.id,
        brand="Toyota",
        model="Hilux",
        trim="SRV 4x4",
        year=2023,
        condition=ConditionEnum.used,
        km=45000,
        price=18000000,
        currency="ARS",
        status=StatusEnum.available,
        location="Buenos Aires",
        description="Excelente estado, unico dueno.",
        photos=["https://example.com/hilux1.jpg", "https://example.com/hilux2.jpg"],
        tags=["offer"],
    )
    db_session.add(car)
    await db_session.flush()
    return car


@pytest_asyncio.fixture
async def sample_car_with_ml_id(db_session: AsyncSession, dealership: Dealership) -> InventoryItem:
    """Create a sample car with ml_item_id for outbound tests."""
    car = InventoryItem(
        dealership_id=dealership.id,
        brand="Toyota",
        model="Hilux",
        trim="SRV 4x4",
        year=2023,
        condition=ConditionEnum.used,
        km=45000,
        price=18000000,
        currency="ARS",
        status=StatusEnum.available,
        location="Buenos Aires",
        description="Excelente estado",
        photos=["https://example.com/hilux1.jpg"],
        ml_item_id="MLA1234567890",
    )
    db_session.add(car)
    await db_session.flush()
    return car


@pytest_asyncio.fixture
async def sample_car_no_photos(db_session: AsyncSession, dealership: Dealership) -> InventoryItem:
    """Create a car without photos."""
    car = InventoryItem(
        dealership_id=dealership.id,
        brand="Ford",
        model="Ranger",
        year=2024,
        condition=ConditionEnum.zero_km,
        price=25000000,
        currency="ARS",
        status=StatusEnum.available,
        location="Cordoba",
        photos=[],
    )
    db_session.add(car)
    await db_session.flush()
    return car
