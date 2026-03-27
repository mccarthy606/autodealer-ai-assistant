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


# === Language switching tests ===


@pytest.mark.asyncio
async def test_language_es_to_en_switch(db_session: AsyncSession, dealership: Dealership):
    """Language switches from Spanish to English when user switches."""
    # Start in Spanish
    r1 = await process_message(db_session, dealership.id, "+5491100020001", "Hola!", "admin_test")
    assert r1.language.startswith("es")

    # Switch to English
    r2 = await process_message(db_session, dealership.id, "+5491100020001", "Hi, do you have any cars?", "admin_test")
    assert r2.language == "en"


@pytest.mark.asyncio
async def test_language_en_to_es_switch(db_session: AsyncSession, dealership: Dealership):
    """Language switches from English to Spanish when user switches (was buggy)."""
    # Start in English (use clear English phrase)
    r1 = await process_message(db_session, dealership.id, "+5491100020002", "Hi, do you have any cars available?", "admin_test")
    assert r1.language == "en"

    # Switch to Spanish
    r2 = await process_message(db_session, dealership.id, "+5491100020002", "Hola, tienen autos disponibles?", "admin_test")
    assert r2.language.startswith("es"), f"Expected language to switch to 'es' but got '{r2.language}'"


@pytest.mark.asyncio
async def test_language_sticky_spanish(db_session: AsyncSession, dealership: Dealership):
    """Language stays Spanish across 3 consecutive Spanish messages."""
    phone = "+5491100020003"
    r1 = await process_message(db_session, dealership.id, phone, "Hola!", "admin_test")
    assert r1.language.startswith("es")

    r2 = await process_message(db_session, dealership.id, phone, "Busco un auto usado", "admin_test")
    assert r2.language.startswith("es")

    r3 = await process_message(db_session, dealership.id, phone, "Algo en buen precio", "admin_test")
    assert r3.language.startswith("es")


@pytest.mark.asyncio
async def test_language_sticky_english(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    """Language stays English across 3 consecutive English messages."""
    phone = "+5491100020004"
    r1 = await process_message(db_session, dealership.id, phone, "Good morning, I need help", "admin_test")
    assert r1.language == "en"

    r2 = await process_message(db_session, dealership.id, phone, "Do you have a Toyota Hilux?", "admin_test")
    assert r2.language == "en"

    r3 = await process_message(db_session, dealership.id, phone, "Can you tell me more details about it?", "admin_test")
    assert r3.language == "en"


@pytest.mark.asyncio
async def test_first_message_sets_language_spanish(db_session: AsyncSession, dealership: Dealership):
    """First message in Spanish sets language to es."""
    r = await process_message(db_session, dealership.id, "+5491100020005", "Buenas tardes", "admin_test")
    assert r.language.startswith("es")


@pytest.mark.asyncio
async def test_first_message_sets_language_english(db_session: AsyncSession, dealership: Dealership):
    """First message in English sets language to en."""
    r = await process_message(db_session, dealership.id, "+5491100020006", "Good morning, I need help", "admin_test")
    assert r.language == "en"


# === State machine tests ===


@pytest.mark.asyncio
async def test_state_new_to_browsing_on_greeting(db_session: AsyncSession, dealership: Dealership):
    """NEW -> BROWSING on GREETING intent."""
    r = await process_message(db_session, dealership.id, "+5491100030001", "Hola!", "admin_test")
    assert r.stage == "BROWSING"
    assert r.intent == "GREETING"


@pytest.mark.asyncio
async def test_state_browsing_to_presenting_on_search(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    """BROWSING -> PRESENTING on SEARCH_CAR with matching car."""
    # First go to BROWSING
    await process_message(db_session, dealership.id, "+5491100030002", "Hola!", "admin_test")
    # Search
    r = await process_message(db_session, dealership.id, "+5491100030002", "Tienen Toyota Hilux?", "admin_test")
    assert r.stage == "PRESENTING"
    assert len(r.matched_cars) > 0


@pytest.mark.asyncio
async def test_state_presenting_to_details_on_ask_details(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    """PRESENTING -> DETAILS on ASK_DETAILS."""
    phone = "+5491100030003"
    # Search to get to PRESENTING
    await process_message(db_session, dealership.id, phone, "Tienen Toyota Hilux?", "admin_test")
    # Ask for details
    r = await process_message(db_session, dealership.id, phone, "Contame más detalles", "admin_test")
    assert r.stage == "DETAILS"
    assert r.selected_car is not None


@pytest.mark.asyncio
async def test_any_state_to_handoff_on_human(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    """Any state -> HANDOFF on HUMAN intent."""
    phone = "+5491100030004"
    # Go to PRESENTING first
    await process_message(db_session, dealership.id, phone, "Tienen Toyota Hilux?", "admin_test")
    # Request human from PRESENTING state
    r = await process_message(db_session, dealership.id, phone, "Quiero hablar con un vendedor", "admin_test")
    assert r.stage == "HANDOFF"
    assert r.mode == "manager"
    assert r.handoff_reason == "requested_human"


@pytest.mark.asyncio
async def test_visit_intent_triggers_lead_and_handoff(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    """VISIT intent creates lead and triggers HANDOFF."""
    phone = "+5491100030005"
    await process_message(db_session, dealership.id, phone, "Tienen Hilux?", "admin_test")
    r = await process_message(db_session, dealership.id, phone, "Quiero pasar a verlo mañana", "admin_test")
    assert r.lead_id is not None
    assert r.mode == "manager"
    assert r.handoff_reason == "visit_scheduling"


@pytest.mark.asyncio
async def test_financing_intent_triggers_handoff(db_session: AsyncSession, dealership: Dealership):
    """FINANCING intent triggers HANDOFF with lead creation."""
    r = await process_message(
        db_session, dealership.id, "+5491100030006",
        "Quiero financiar, tienen planes de cuotas?",
        "admin_test",
    )
    assert r.mode == "manager"
    assert r.handoff_reason == "financing"
    assert r.lead_id is not None


@pytest.mark.asyncio
async def test_trade_in_intent_triggers_handoff(db_session: AsyncSession, dealership: Dealership):
    """TRADE_IN intent triggers HANDOFF with lead creation."""
    r = await process_message(
        db_session, dealership.id, "+5491100030007",
        "Quiero entregar mi auto como parte de pago, permuta",
        "admin_test",
    )
    assert r.mode == "manager"
    assert r.handoff_reason == "trade_in"
    assert r.lead_id is not None


@pytest.mark.asyncio
async def test_full_flow_new_to_handoff(db_session: AsyncSession, dealership: Dealership, sample_car: InventoryItem):
    """Full flow: NEW -> BROWSING -> PRESENTING -> DETAILS -> HANDOFF."""
    phone = "+5491100030008"

    # NEW -> BROWSING
    r1 = await process_message(db_session, dealership.id, phone, "Hola!", "admin_test")
    assert r1.stage == "BROWSING"

    # BROWSING -> PRESENTING
    r2 = await process_message(db_session, dealership.id, phone, "Tienen Toyota Hilux?", "admin_test")
    assert r2.stage == "PRESENTING"
    assert len(r2.matched_cars) > 0

    # PRESENTING -> DETAILS
    r3 = await process_message(db_session, dealership.id, phone, "Contame más detalles", "admin_test")
    assert r3.stage == "DETAILS"
    assert r3.selected_car is not None

    # DETAILS -> HANDOFF (via human request)
    r4 = await process_message(db_session, dealership.id, phone, "Quiero hablar con un vendedor", "admin_test")
    assert r4.stage == "HANDOFF"
    assert r4.mode == "manager"


@pytest.mark.asyncio
async def test_error_recovery_invalid_dealership(db_session: AsyncSession, dealership: Dealership):
    """process_message with invalid dealership_id returns graceful result."""
    # Use dealership_id=99999 which does not exist
    r = await process_message(db_session, 99999, "+5491100030009", "Hola!", "admin_test")
    # Should still return a result (not crash)
    assert r is not None
    assert isinstance(r.text, str)


# === Channel verification tests ===


@pytest.mark.asyncio
async def test_channel_whatsapp(db_session: AsyncSession, dealership: Dealership):
    """process_message works with channel='whatsapp'."""
    r = await process_message(db_session, dealership.id, "+5491100040001", "Hola!", "whatsapp")
    assert r.text
    assert r.conversation_id > 0


@pytest.mark.asyncio
async def test_channel_admin_test(db_session: AsyncSession, dealership: Dealership):
    """process_message works with channel='admin_test'."""
    r = await process_message(db_session, dealership.id, "+5491100040002", "Hola!", "admin_test")
    assert r.text
    assert r.conversation_id > 0
