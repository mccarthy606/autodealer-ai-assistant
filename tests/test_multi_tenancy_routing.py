"""Tests for multi-tenant webhook routing and Redis key isolation."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.adapters.whatsapp_cloud import (
    parse_incoming_message,
    get_dealership_by_wa,
    WhatsAppCloudAdapter,
)
from src.adapters.mercadolibre import (
    parse_incoming_question,
    get_dealership_by_ml,
)
from src.db.models import Dealership, InventoryItem, ConditionEnum, StatusEnum


# ---------------------------------------------------------------------------
# Section A: parse_incoming_message 4-tuple (MT-03)
# ---------------------------------------------------------------------------

def _make_wa_payload(phone_number_id: str = "1111111111", text: str = "Hola") -> dict:
    """Build a minimal Meta WhatsApp Cloud webhook POST payload."""
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "phone_number_id": phone_number_id,
                                "display_phone_number": "+5491155550000",
                            },
                            "messages": [
                                {
                                    "from": "5491112345678",
                                    "type": "text",
                                    "text": {"body": text},
                                    "id": "wamid_test_001",
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def test_parse_incoming_message_returns_4tuple():
    """parse_incoming_message returns a 4-tuple with phone_number_id as 4th element."""
    payload = _make_wa_payload(phone_number_id="1111111111")
    result = parse_incoming_message(payload)

    assert result is not None
    assert len(result) == 4
    assert result[3] == "1111111111"


def test_parse_incoming_message_returns_none_for_no_message():
    """parse_incoming_message returns None when payload has no messages."""
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "1111111111"},
                            "messages": [],
                        }
                    }
                ]
            }
        ]
    }
    result = parse_incoming_message(payload)
    assert result is None


def test_parse_incoming_message_missing_phone_number_id():
    """parse_incoming_message returns 4th element as None when metadata is absent."""
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "5491112345678",
                                    "type": "text",
                                    "text": {"body": "test"},
                                    "id": "wamid_test_002",
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    result = parse_incoming_message(payload)
    # May be None (no metadata -> phone_number_id is None, but phone+text exist)
    # The function returns a tuple only if phone and text are truthy; phone_number_id can be None
    assert result is None or result[3] is None


# ---------------------------------------------------------------------------
# Section B: get_dealership_by_wa lookup (MT-03)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_dealership_by_wa_finds_correct_dealer(db_session, dealership):
    """get_dealership_by_wa returns the correct dealership for a known phone_number_id."""
    result = await get_dealership_by_wa(db_session, "1111111111")

    assert result is not None
    assert result.id == 1


@pytest.mark.asyncio
async def test_get_dealership_by_wa_returns_none_for_unknown(db_session, dealership):
    """get_dealership_by_wa returns None for an unknown phone_number_id."""
    result = await get_dealership_by_wa(db_session, "9999999999")

    assert result is None


# ---------------------------------------------------------------------------
# Section C: get_dealership_by_ml lookup (MT-03)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_dealership_by_ml_finds_correct_dealer(db_session, dealership):
    """get_dealership_by_ml returns the correct dealership for a known ml_user_id."""
    result = await get_dealership_by_ml(db_session, "123456789")

    assert result is not None
    assert result.id == 1


@pytest.mark.asyncio
async def test_get_dealership_by_ml_returns_none_for_unknown(db_session, dealership):
    """get_dealership_by_ml returns None for an unknown ml_user_id."""
    result = await get_dealership_by_ml(db_session, "000000000")

    assert result is None


def test_parse_incoming_question_extracts_user_id():
    """parse_incoming_question returns a dict with question_id and user_id."""
    payload = {
        "topic": "questions",
        "resource": "/questions/12345",
        "user_id": 123456789,
    }
    result = parse_incoming_question(payload)

    assert result is not None
    assert result["user_id"] == 123456789
    assert result["question_id"] == "12345"


# ---------------------------------------------------------------------------
# Section D: WhatsAppCloudAdapter per-tenant credentials (MT-01, MT-02)
# ---------------------------------------------------------------------------

def test_adapter_uses_provided_credentials():
    """WhatsAppCloudAdapter uses explicitly provided credentials."""
    adapter = WhatsAppCloudAdapter(phone_number_id="custom_pid", token="custom_tok")

    assert adapter.phone_number_id == "custom_pid"
    assert adapter.token == "custom_tok"
    assert adapter.is_configured is True


def test_adapter_falls_back_to_settings_when_no_args():
    """WhatsAppCloudAdapter falls back to settings when no args provided."""
    with patch("src.adapters.whatsapp_cloud.settings") as mock_settings:
        mock_settings.whatsapp_phone_number_id = "settings_pid"
        mock_settings.whatsapp_cloud_token = "settings_tok"
        adapter = WhatsAppCloudAdapter()

    assert adapter.phone_number_id == "settings_pid"


def test_adapter_is_not_configured_when_no_token():
    """WhatsAppCloudAdapter.is_configured is False when both token sources are empty."""
    with patch("src.adapters.whatsapp_cloud.settings") as mock_settings:
        mock_settings.whatsapp_phone_number_id = ""
        mock_settings.whatsapp_cloud_token = ""
        adapter = WhatsAppCloudAdapter()

    assert adapter.is_configured is False


# ---------------------------------------------------------------------------
# Section E: Data isolation (MT-01)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dealership_data_isolation(db_session, dealership, dealership2):
    """FK-based isolation: queries scoped to dealership_id return only that dealer's rows."""
    # Create inventory items for each dealership
    item1 = InventoryItem(
        dealership_id=1,
        brand="Toyota",
        model="Hilux",
        year=2022,
        condition=ConditionEnum.used,
        price=15000000,
        currency="ARS",
        status=StatusEnum.available,
        location="CABA",
        photos=[],
    )
    item2 = InventoryItem(
        dealership_id=2,
        brand="Ford",
        model="Ranger",
        year=2021,
        condition=ConditionEnum.used,
        price=12000000,
        currency="ARS",
        status=StatusEnum.available,
        location="Córdoba",
        photos=[],
    )
    db_session.add(item1)
    db_session.add(item2)
    await db_session.flush()

    # Query dealership 1 items
    result1 = await db_session.execute(
        select(InventoryItem).where(InventoryItem.dealership_id == 1)
    )
    items1 = result1.scalars().all()

    # Query dealership 2 items
    result2 = await db_session.execute(
        select(InventoryItem).where(InventoryItem.dealership_id == 2)
    )
    items2 = result2.scalars().all()

    assert len(items1) == 1
    assert items1[0].brand == "Toyota"

    assert len(items2) == 1
    assert items2[0].brand == "Ford"


# ---------------------------------------------------------------------------
# Section F: Redis key namespacing (MT-04)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_key_includes_dealership_id():
    """Rate limiter Redis key includes dealership_id prefix for namespace isolation (MT-04)."""
    from src.api.rate_limit import check_rate_limit

    mock_pipe = MagicMock()
    mock_pipe.incr = MagicMock(return_value=mock_pipe)
    mock_pipe.expire = MagicMock(return_value=mock_pipe)
    mock_pipe.ttl = MagicMock(return_value=mock_pipe)
    mock_pipe.execute = AsyncMock(return_value=[1, True, 59])

    mock_redis = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    # Test with dealership 1 prefix
    with patch("src.api.rate_limit.get_redis", new_callable=AsyncMock, return_value=mock_redis):
        await check_rate_limit(
            key="5491112345678",
            limit=20,
            window_seconds=60,
            prefix="rate:wa:1",
        )

    mock_pipe.incr.assert_called_once_with("rate:wa:1:5491112345678")

    # Reset mocks and test with dealership 2 prefix
    mock_pipe.incr.reset_mock()
    mock_pipe.execute = AsyncMock(return_value=[1, True, 59])

    with patch("src.api.rate_limit.get_redis", new_callable=AsyncMock, return_value=mock_redis):
        await check_rate_limit(
            key="5491112345678",
            limit=20,
            window_seconds=60,
            prefix="rate:wa:2",
        )

    mock_pipe.incr.assert_called_once_with("rate:wa:2:5491112345678")
