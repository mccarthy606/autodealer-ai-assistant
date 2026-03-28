"""Test fixtures."""

import asyncio
import json
from datetime import datetime, UTC, timedelta
from typing import AsyncGenerator

import bcrypt
import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event, text, JSON
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB

from src.db.session import Base
from src.db.models import *  # noqa - import all models

# Computed once at module load — bcrypt is slow per-call
_DEALER1_HASH: str = bcrypt.hashpw(b"pass1", bcrypt.gensalt()).decode()
_DEALER2_HASH: str = bcrypt.hashpw(b"pass2", bcrypt.gensalt()).decode()


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
    """Create a test dealership with multi-tenant fields."""
    d = Dealership(
        id=1,
        name="Test Dealership",
        address="Av. Test 123, CABA",
        business_hours="Lun-Vie 9-18",
        timezone="America/Argentina/Buenos_Aires",
        default_language="es-AR",
        whatsapp_phone_number_id="1111111111",
        whatsapp_access_token="test-wa-token-1",
        whatsapp_verify_token="test-verify-token-1",
        ml_user_id="123456789",
        admin_username="dealer1",
        admin_password_hash=_DEALER1_HASH,
    )
    db_session.add(d)
    await db_session.flush()
    return d


@pytest_asyncio.fixture
async def dealership2(db_session: AsyncSession) -> Dealership:
    """Second dealership for isolation tests."""
    d = Dealership(
        id=2,
        name="Second Dealership",
        address="Av. Segunda 456, CABA",
        whatsapp_phone_number_id="2222222222",
        whatsapp_access_token="test-wa-token-2",
        whatsapp_verify_token="test-verify-token-2",
        ml_user_id="987654321",
        admin_username="dealer2",
        admin_password_hash=_DEALER2_HASH,
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


# ---------------------------------------------------------------------------
# Billing fixtures (ids 10-14) — used by tests/test_billing.py
# IDs chosen to avoid collision with existing fixtures (1, 2).
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def active_dealership(db_session: AsyncSession) -> Dealership:
    """Dealership with an active subscription."""
    d = Dealership(
        id=10,
        name="Active Dealership",
        whatsapp_phone_number_id="3333333333",
        whatsapp_access_token="test-wa-token-10",
        whatsapp_verify_token="test-verify-token-10",
        admin_username="dealer_active",
        admin_password_hash=_DEALER1_HASH,
        subscription_status="active",
        subscription_id="sub_active_001",
        ls_customer_id="cust_001",
        plan="basic",
    )
    db_session.add(d)
    await db_session.flush()
    return d


@pytest_asyncio.fixture
async def trial_dealership(db_session: AsyncSession) -> Dealership:
    """Dealership on a trial subscription with trial_ends_at in the future."""
    d = Dealership(
        id=11,
        name="Trial Dealership",
        whatsapp_phone_number_id="4444444444",
        whatsapp_access_token="test-wa-token-11",
        whatsapp_verify_token="test-verify-token-11",
        admin_username="dealer_trial",
        admin_password_hash=_DEALER1_HASH,
        subscription_status="trial",
        subscription_id="sub_trial_001",
        ls_customer_id="cust_002",
        plan="basic",
        trial_ends_at=datetime.now(UTC) + timedelta(days=5),
    )
    db_session.add(d)
    await db_session.flush()
    return d


@pytest_asyncio.fixture
async def past_due_in_grace_dealership(db_session: AsyncSession) -> Dealership:
    """Dealership that is past_due but still within the 7-day grace period."""
    d = Dealership(
        id=12,
        name="Past Due Grace Dealership",
        whatsapp_phone_number_id="5555555555",
        whatsapp_access_token="test-wa-token-12",
        whatsapp_verify_token="test-verify-token-12",
        admin_username="dealer_grace",
        admin_password_hash=_DEALER1_HASH,
        subscription_status="past_due",
        subscription_id="sub_grace_001",
        ls_customer_id="cust_003",
        grace_period_ends_at=datetime.now(UTC) + timedelta(days=3),
    )
    db_session.add(d)
    await db_session.flush()
    return d


@pytest_asyncio.fixture
async def expired_dealership(db_session: AsyncSession) -> Dealership:
    """Dealership with an expired subscription — service must be blocked."""
    d = Dealership(
        id=13,
        name="Expired Dealership",
        whatsapp_phone_number_id="6666666666",
        whatsapp_access_token="test-wa-token-13",
        whatsapp_verify_token="test-verify-token-13",
        admin_username="dealer_expired",
        admin_password_hash=_DEALER1_HASH,
        subscription_status="expired",
        subscription_id="sub_expired_001",
        ls_customer_id="cust_004",
    )
    db_session.add(d)
    await db_session.flush()
    return d


@pytest_asyncio.fixture
async def no_subscription_dealership(db_session: AsyncSession) -> Dealership:
    """Dealership with no subscription at all — all subscription fields None."""
    d = Dealership(
        id=14,
        name="No Subscription Dealership",
        whatsapp_phone_number_id="7777777777",
        whatsapp_access_token="test-wa-token-14",
        whatsapp_verify_token="test-verify-token-14",
        admin_username="dealer_nosub",
        admin_password_hash=_DEALER1_HASH,
    )
    db_session.add(d)
    await db_session.flush()
    return d
