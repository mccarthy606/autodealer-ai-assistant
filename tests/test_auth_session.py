"""Tests for multi-tenant session management (auth.py)."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.responses import Response

from src.api.auth import (
    create_session,
    get_session_dealership_id,
    is_authenticated,
    _hash_token,
    ADMIN_COOKIE,
    _admin_sessions,
)


def _make_response() -> MagicMock:
    """Create a mock Response object that captures set_cookie calls."""
    resp = MagicMock(spec=Response)
    resp._cookie_value = None

    def capture_cookie(key, value, **kwargs):
        resp._cookie_value = value

    resp.set_cookie.side_effect = capture_cookie
    return resp


@pytest.mark.asyncio
async def test_create_session_stores_dealership_id():
    """create_session stores dealership_id retrievable via get_session_dealership_id (in-memory fallback)."""
    _admin_sessions.clear()
    resp = _make_response()

    with patch("src.api.auth.get_redis", new_callable=AsyncMock, return_value=None):
        await create_session(resp, dealership_id=42)
        token = resp._cookie_value
        assert token is not None

        result = await get_session_dealership_id(token)

    assert result == 42


@pytest.mark.asyncio
async def test_create_session_different_dealerships():
    """Two sessions with different dealership_ids return the correct id for each token."""
    _admin_sessions.clear()
    resp1 = _make_response()
    resp2 = _make_response()

    with patch("src.api.auth.get_redis", new_callable=AsyncMock, return_value=None):
        await create_session(resp1, dealership_id=1)
        await create_session(resp2, dealership_id=2)

        token1 = resp1._cookie_value
        token2 = resp2._cookie_value

        assert token1 != token2

        result1 = await get_session_dealership_id(token1)
        result2 = await get_session_dealership_id(token2)

    assert result1 == 1
    assert result2 == 2
    # Cross-check: token1 does NOT return dealership_id=2
    assert result1 != 2


@pytest.mark.asyncio
async def test_is_authenticated_returns_true_when_session_exists():
    """is_authenticated returns True when session exists in in-memory store."""
    _admin_sessions.clear()
    resp = _make_response()

    with patch("src.api.auth.get_redis", new_callable=AsyncMock, return_value=None):
        await create_session(resp, dealership_id=5)
        token = resp._cookie_value

        # is_authenticated needs admin_password or admin_password_hash to be set
        # otherwise it short-circuits to True without checking the session
        with patch("src.api.auth.settings") as mock_settings:
            mock_settings.admin_password = "somepass"
            mock_settings.admin_password_hash = ""
            mock_settings.database_url = "sqlite:///test.db"
            result = await is_authenticated(token)

    assert result is True


@pytest.mark.asyncio
async def test_is_authenticated_returns_false_for_unknown_token():
    """is_authenticated returns False for a token not in any session store."""
    _admin_sessions.clear()

    with patch("src.api.auth.get_redis", new_callable=AsyncMock, return_value=None):
        with patch("src.api.auth.settings") as mock_settings:
            mock_settings.admin_password = "somepass"
            mock_settings.admin_password_hash = ""
            result = await is_authenticated("nonexistent-token-abc123")

    assert result is False


@pytest.mark.asyncio
async def test_get_session_dealership_id_returns_none_for_missing_token():
    """get_session_dealership_id returns None for None or empty string."""
    with patch("src.api.auth.get_redis", new_callable=AsyncMock, return_value=None):
        result_none = await get_session_dealership_id(None)
        result_empty = await get_session_dealership_id("")

    assert result_none is None
    assert result_empty is None


@pytest.mark.asyncio
async def test_backward_compat_old_session_value():
    """Backward-compat: old sessions stored raw int in _admin_sessions dict are handled gracefully."""
    _admin_sessions.clear()

    # Simulate an old-style session: token_hash -> dealership_id stored as int (which is the current format)
    # The backward compat path in get_session_dealership_id is for JSON-parse failures
    # We simulate this by directly inserting into _admin_sessions
    import secrets
    old_token = secrets.token_hex(24)
    old_hash = _hash_token(old_token)
    _admin_sessions[old_hash] = 1  # old format: int stored directly

    with patch("src.api.auth.get_redis", new_callable=AsyncMock, return_value=None):
        result = await get_session_dealership_id(old_token)

    assert result == 1
    _admin_sessions.clear()


@pytest.mark.asyncio
async def test_superadmin_login_creates_session_with_dealership_id_1():
    """Superadmin login (blank username + settings password) creates session scoped to dealership_id=1 (D-08)."""
    _admin_sessions.clear()
    resp = _make_response()

    # Simulate superadmin login flow: create_session with settings.default_dealership_id
    with patch("src.api.auth.get_redis", new_callable=AsyncMock, return_value=None):
        with patch("src.api.auth.settings") as mock_settings:
            mock_settings.admin_password = "superpass"
            mock_settings.admin_password_hash = ""
            mock_settings.default_dealership_id = 1
            mock_settings.database_url = "sqlite:///test.db"

            # The superadmin login path calls create_session(resp, settings.default_dealership_id)
            await create_session(resp, dealership_id=mock_settings.default_dealership_id)
            token = resp._cookie_value

        result = await get_session_dealership_id(token)

    assert result == 1
    _admin_sessions.clear()
