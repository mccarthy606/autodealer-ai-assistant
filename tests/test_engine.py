"""Tests for the conversation engine — key scenarios."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Conversation, Lead, InventoryItem, Dealership,
    ConditionEnum, StatusEnum, LeadIntentEnum,
)
from src.services.conversation_engine import process_message


@pytest.mark.asyncio
async def test_english_response_language_set(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    """E: When customer writes in English, bot responds in English and sets language."""
    result = await process_message(db_session, dealership.id, "+5491100001111", "Hi, do you have a Toyota Hilux?", "admin_test")

    assert result.text  # Non-empty response
    assert result.state.get("language") == "en"
    # Should contain English words (not Spanish)
    text_lower = result.text.lower()
    assert any(w in text_lower for w in ["we have", "options", "details", "would you"]) or len(result.matched_cars) > 0


@pytest.mark.asyncio
async def test_photos_request_sends_urls(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    """F: When photos are requested and car has photos, send URLs."""
    # First search for a car to set context
    await process_message(db_session, dealership.id, "+5491100002222", "Tienen Toyota Hilux?", "admin_test")
    # Then ask for photos
    result = await process_message(db_session, dealership.id, "+5491100002222", "Mandame fotos", "admin_test")

    assert result.photo_urls
    assert len(result.photo_urls) > 0
    assert "example.com" in result.photo_urls[0]


@pytest.mark.asyncio
async def test_photos_request_handoffs_if_missing(db_session: AsyncSession, dealership: Dealership, sample_car_no_photos: InventoryItem):
    """F: When photos are requested but car has none, handoff to manager."""
    # Search for Ford Ranger (no photos)
    await process_message(db_session, dealership.id, "+5491100003333", "Tienen Ford Ranger?", "admin_test")
    # Ask for photos
    result = await process_message(db_session, dealership.id, "+5491100003333", "Can you send me photos?", "admin_test")

    assert result.mode == "manager"
    assert result.handoff_reason == "photos_missing"


@pytest.mark.asyncio
async def test_visit_creates_lead_and_switches_to_manager(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    """E/J: Visit intent creates lead automatically and switches to manager."""
    # First search
    await process_message(db_session, dealership.id, "+5491100004444", "Tienen Hilux?", "admin_test")
    # Then visit
    result = await process_message(
        db_session, dealership.id, "+5491100004444",
        "Quiero pasar mañana a la tarde. Me llamo Juan.",
        "admin_test",
    )

    # Lead should be created
    assert result.lead_id is not None

    # Mode should be manager
    assert result.mode == "manager"
    assert result.handoff_reason == "visit_scheduling"

    # Verify lead in DB
    stmt = select(Lead).where(Lead.id == result.lead_id)
    r = await db_session.execute(stmt)
    lead = r.scalar_one()
    assert lead.intent == LeadIntentEnum.visit
    assert lead.phone == "+5491100004444"


@pytest.mark.asyncio
async def test_handoff_on_financing(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    """J: Financing intent triggers handoff."""
    result = await process_message(
        db_session, dealership.id, "+5491100005555",
        "Me interesa financiar un auto en cuotas",
        "admin_test",
    )

    assert result.mode == "manager"
    assert result.handoff_reason == "financing"
    assert result.lead_id is not None


@pytest.mark.asyncio
async def test_search_then_visit_does_not_search_again(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    """E: After showing a car, visit intent does NOT trigger a new search."""
    # Step 1: search
    r1 = await process_message(db_session, dealership.id, "+5491100006666", "Tienen Hilux?", "admin_test")
    assert len(r1.matched_cars) > 0

    # Step 2: visit — should NOT re-search, should handoff
    r2 = await process_message(db_session, dealership.id, "+5491100006666", "Quiero pasar mañana", "admin_test")

    # Should be in manager mode, not another search
    assert r2.mode == "manager"
    assert r2.handoff_reason == "visit_scheduling"
    # The response should mention the address, not a new car listing
    assert "Av. Test 123" in r2.text or "esperamos" in r2.text.lower()


@pytest.mark.asyncio
async def test_greeting_response(db_session: AsyncSession, dealership: Dealership):
    """Greeting should get a friendly response."""
    result = await process_message(db_session, dealership.id, "+5491100007777", "Hola!", "admin_test")
    assert result.text
    assert "hola" in result.text.lower() or "hi" in result.text.lower()


@pytest.mark.asyncio
async def test_trade_in_triggers_handoff(db_session: AsyncSession, dealership: Dealership):
    """Trade-in intent triggers handoff."""
    result = await process_message(
        db_session, dealership.id, "+5491100008888",
        "Quiero hacer una permuta con mi auto actual",
        "admin_test",
    )
    assert result.mode == "manager"
    assert result.handoff_reason == "trade_in"


@pytest.mark.asyncio
async def test_human_request_triggers_handoff(db_session: AsyncSession, dealership: Dealership):
    """Explicit human request triggers handoff."""
    result = await process_message(
        db_session, dealership.id, "+5491100009999",
        "Quiero hablar con un vendedor",
        "admin_test",
    )
    assert result.mode == "manager"
    assert result.handoff_reason == "requested_human"


@pytest.mark.asyncio
async def test_manager_mode_no_auto_reply(db_session: AsyncSession, dealership: Dealership):
    """Once in manager mode, bot does not auto-reply."""
    # Trigger handoff
    await process_message(db_session, dealership.id, "+5491100010101", "Quiero hablar con un vendedor", "admin_test")

    # Send another message — should get empty response
    result = await process_message(db_session, dealership.id, "+5491100010101", "Hola, estás ahí?", "admin_test")
    assert result.text == ""
    assert result.mode == "manager"
