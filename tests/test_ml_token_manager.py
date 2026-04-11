"""Tests for ml_token_manager per-dealer Redis key namespacing and refresh logic."""

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _ml_keys
# ---------------------------------------------------------------------------

def test_ml_keys_namespaced_by_dealer():
    from src.services.ml_token_manager import _ml_keys

    token_key, refresh_key, expires_key, lock_key = _ml_keys(42)
    assert token_key == "ml:42:access_token"
    assert refresh_key == "ml:42:refresh_token"
    assert expires_key == "ml:42:token_expires_at"
    assert lock_key == "ml:42:refresh_lock"


def test_ml_keys_different_dealers_dont_collide():
    from src.services.ml_token_manager import _ml_keys

    keys_1 = _ml_keys(1)
    keys_2 = _ml_keys(2)
    for k1, k2 in zip(keys_1, keys_2):
        assert k1 != k2


# ---------------------------------------------------------------------------
# _needs_refresh
# ---------------------------------------------------------------------------

def test_needs_refresh_no_token():
    from src.services.ml_token_manager import _needs_refresh
    assert _needs_refresh("", None) is True


def test_needs_refresh_no_expiry():
    from src.services.ml_token_manager import _needs_refresh
    assert _needs_refresh("sometoken", None) is True


def test_needs_refresh_fresh_token():
    from src.services.ml_token_manager import _needs_refresh
    expires_at = datetime.now(UTC) + timedelta(hours=4)
    assert _needs_refresh("sometoken", expires_at) is False


def test_needs_refresh_within_buffer():
    """Token expiring in 20 minutes (< 30min buffer) should trigger refresh."""
    from src.services.ml_token_manager import _needs_refresh
    expires_at = datetime.now(UTC) + timedelta(minutes=20)
    assert _needs_refresh("sometoken", expires_at) is True


def test_needs_refresh_expired():
    from src.services.ml_token_manager import _needs_refresh
    expires_at = datetime.now(UTC) - timedelta(hours=1)
    assert _needs_refresh("sometoken", expires_at) is True


# ---------------------------------------------------------------------------
# get_valid_token — Redis available, token fresh
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_valid_token_returns_cached_redis_token():
    """When Redis has a fresh token, return it without refreshing."""
    from src.services.ml_token_manager import get_valid_token

    fresh_expires = (datetime.now(UTC) + timedelta(hours=3)).isoformat()

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=lambda key: {
        "ml:1:access_token": "fresh_token_123",
        "ml:1:token_expires_at": fresh_expires,
    }.get(key, None))

    with patch("src.services.ml_token_manager._get_redis", new=AsyncMock(return_value=mock_redis)):
        token = await get_valid_token(dealership_id=1)

    assert token == "fresh_token_123"


@pytest.mark.asyncio
async def test_get_valid_token_fallback_to_settings_when_redis_unavailable():
    """When Redis is unavailable, fall back to settings.ml_access_token."""
    from src.services.ml_token_manager import get_valid_token

    with patch("src.services.ml_token_manager._get_redis", return_value=AsyncMock(return_value=None)), \
         patch("src.services.ml_token_manager.settings") as mock_settings, \
         patch("src.services.ml_token_manager._refresh_with_lock", return_value=AsyncMock(return_value=None)):
        mock_settings.ml_access_token = "settings_fallback_token"
        # Fresh expires_at = None triggers _needs_refresh(token, None) = True
        # but _refresh_with_lock returns None so we fall back to settings token
        with patch("src.services.ml_token_manager._needs_refresh", return_value=False):
            token = await get_valid_token(dealership_id=1)

    assert token == "settings_fallback_token"


# ---------------------------------------------------------------------------
# _do_refresh — HTTP error paths
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_do_refresh_logs_non_200_response():
    """_do_refresh returns None and logs error when ML API returns non-200."""
    from src.services.ml_token_manager import _do_refresh

    mock_dealer = MagicMock()
    mock_dealer.ml_refresh_token = "refresh_tok"
    mock_dealer.ml_app_id = "app123"
    mock_dealer.ml_client_secret = "secret123"

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = '{"message": "Unauthorized"}'

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("src.services.ml_token_manager.httpx.AsyncClient", return_value=mock_client), \
         patch("src.services.ml_token_manager.settings") as mock_settings:
        mock_settings.ml_refresh_token = ""
        mock_settings.ml_app_id = ""
        mock_settings.ml_client_secret = ""

        result = await _do_refresh(redis=None, did=1, dealer=mock_dealer)

    assert result is None


@pytest.mark.asyncio
async def test_do_refresh_returns_access_token_on_success():
    """_do_refresh returns new access token on successful ML response."""
    from src.services.ml_token_manager import _do_refresh

    mock_dealer = MagicMock()
    mock_dealer.ml_refresh_token = "refresh_tok"
    mock_dealer.ml_app_id = "app123"
    mock_dealer.ml_client_secret = "secret123"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "access_token": "new_access_tok",
        "refresh_token": "new_refresh_tok",
        "expires_in": 21600,
    })

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("src.services.ml_token_manager.httpx.AsyncClient", return_value=mock_client), \
         patch("src.services.ml_token_manager.settings") as mock_settings:
        mock_settings.ml_refresh_token = ""
        mock_settings.ml_app_id = ""
        mock_settings.ml_client_secret = ""

        result = await _do_refresh(redis=None, did=1, dealer=mock_dealer)

    assert result == "new_access_tok"


# ---------------------------------------------------------------------------
# _refresh_with_lock — concurrent worker path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_with_lock_waits_when_lock_not_acquired():
    """When lock is already held, wait and re-read token from Redis."""
    from src.services.ml_token_manager import _refresh_with_lock

    fresh_expires = (datetime.now(UTC) + timedelta(hours=3)).isoformat()

    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=None)  # lock not acquired (None = already held)
    mock_redis.get = AsyncMock(side_effect=lambda key: {
        "ml:1:access_token": "refreshed_by_other_worker",
        "ml:1:token_expires_at": fresh_expires,
    }.get(key))

    with patch("src.services.ml_token_manager.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await _refresh_with_lock(redis=mock_redis, did=1, dealer=None)

    mock_sleep.assert_awaited_once_with(2)
    assert result == "refreshed_by_other_worker"
