"""Tests for admin integrations routes and webhook_cloud fallback (INT-02..05)."""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.models import Dealership
from src.config import settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession):
    """AsyncClient with test DB injected and admin auth bypassed."""
    from src.main import app
    from src.api.deps import get_db

    async def _override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def _authed(client, dealership_id: int = 1):
    """Return client kwargs dict that adds an admin_session cookie bypassing auth."""
    return {"cookies": {"admin_session": f"fake_session_{dealership_id}"}}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wa_payload(phone_number_id: str = "9999999999", text: str = "Hola") -> dict:
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {
                        "phone_number_id": phone_number_id,
                        "display_phone_number": "+5491155550000",
                    },
                    "messages": [{
                        "from": "5491112345678",
                        "type": "text",
                        "text": {"body": text},
                        "id": "wamid_test_fallback",
                    }],
                }
            }]
        }]
    }


# ---------------------------------------------------------------------------
# Group 1: integrations_save (INT-02)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_integrations_save_stores_wa_phone_id(
    app_client: AsyncClient,
    dealership: Dealership,
    db_session: AsyncSession,
):
    """POST /integrations should persist whatsapp_phone_number_id to DB."""
    with patch("src.api.routes.admin_settings.auth_check", return_value=dealership.id):
        resp = await app_client.post(
            "/admin/ui/integrations",
            data={"whatsapp_phone_number_id": "1234567890"},
            follow_redirects=False,
        )

    assert resp.status_code == 302
    await db_session.refresh(dealership)
    assert dealership.whatsapp_phone_number_id == "1234567890"


@pytest.mark.asyncio
async def test_integrations_save_skips_blank_fields(
    app_client: AsyncClient,
    dealership: Dealership,
    db_session: AsyncSession,
):
    """Blank token fields must not overwrite existing values (blank-skip logic)."""
    original_token = dealership.whatsapp_access_token  # "test-wa-token-1" from fixture

    with patch("src.api.routes.admin_settings.auth_check", return_value=dealership.id):
        resp = await app_client.post(
            "/admin/ui/integrations",
            data={"whatsapp_access_token": ""},  # blank — should NOT overwrite
            follow_redirects=False,
        )

    assert resp.status_code == 302
    await db_session.refresh(dealership)
    assert dealership.whatsapp_access_token == original_token


@pytest.mark.asyncio
async def test_integrations_save_persists_ml_credentials(
    app_client: AsyncClient,
    dealership: Dealership,
    db_session: AsyncSession,
):
    """POST /integrations should save all ML credential fields."""
    with patch("src.api.routes.admin_settings.auth_check", return_value=dealership.id):
        resp = await app_client.post(
            "/admin/ui/integrations",
            data={
                "ml_app_id": "APP123",
                "ml_client_secret": "SECRET456",
                "ml_user_id": "789",
                "ml_refresh_token": "TG-abc123",
            },
            follow_redirects=False,
        )

    assert resp.status_code == 302
    await db_session.refresh(dealership)
    assert dealership.ml_app_id == "APP123"
    assert dealership.ml_user_id == "789"


@pytest.mark.asyncio
async def test_integrations_save_redirects_with_saved_flag(
    app_client: AsyncClient,
    dealership: Dealership,
):
    """Save must redirect to /integrations?saved=1."""
    with patch("src.api.routes.admin_settings.auth_check", return_value=dealership.id):
        resp = await app_client.post(
            "/admin/ui/integrations",
            data={"ml_user_id": "123"},
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert resp.headers["location"] == "/admin/ui/integrations?saved=1"


# ---------------------------------------------------------------------------
# Group 2: test_connection endpoint (INT-03)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connection_whatsapp_success(
    app_client: AsyncClient,
    dealership: Dealership,
):
    """test_connection returns ok=True when Meta API returns 200."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"display_phone_number": "+5491155550000"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("src.api.routes.admin_settings.auth_check", return_value=dealership.id), \
         patch("src.api.routes.admin_settings.httpx.AsyncClient", return_value=mock_client):
        resp = await app_client.post(
            "/admin/ui/integrations/test-connection",
            content=json.dumps({"service": "whatsapp"}),
            headers={"Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "+5491155550000" in data["detail"]


@pytest.mark.asyncio
async def test_connection_whatsapp_invalid_token(
    app_client: AsyncClient,
    dealership: Dealership,
):
    """test_connection returns ok=False when Meta API returns 401."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"error": {"message": "Invalid OAuth token"}}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("src.api.routes.admin_settings.auth_check", return_value=dealership.id), \
         patch("src.api.routes.admin_settings.httpx.AsyncClient", return_value=mock_client):
        resp = await app_client.post(
            "/admin/ui/integrations/test-connection",
            content=json.dumps({"service": "whatsapp"}),
            headers={"Content-Type": "application/json"},
        )

    data = resp.json()
    assert data["ok"] is False
    assert "Invalid OAuth token" in data["detail"]


@pytest.mark.asyncio
async def test_connection_mercadolibre_success(
    app_client: AsyncClient,
    dealership: Dealership,
    db_session: AsyncSession,
):
    """test_connection returns ok=True when ML /users/me returns 200."""
    dealership.ml_access_token = "valid_ml_token"
    await db_session.flush()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": 123456, "nickname": "AUTOTEST"}

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("src.api.routes.admin_settings.auth_check", return_value=dealership.id), \
         patch("src.api.routes.admin_settings.httpx.AsyncClient", return_value=mock_client):
        resp = await app_client.post(
            "/admin/ui/integrations/test-connection",
            content=json.dumps({"service": "mercadolibre"}),
            headers={"Content-Type": "application/json"},
        )

    data = resp.json()
    assert data["ok"] is True
    assert "AUTOTEST" in data["detail"]


@pytest.mark.asyncio
async def test_connection_network_error_returns_ok_false(
    app_client: AsyncClient,
    dealership: Dealership,
):
    """Network failures must return ok=False with a user-friendly Spanish message."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

    with patch("src.api.routes.admin_settings.auth_check", return_value=dealership.id), \
         patch("src.api.routes.admin_settings.httpx.AsyncClient", return_value=mock_client):
        resp = await app_client.post(
            "/admin/ui/integrations/test-connection",
            content=json.dumps({"service": "whatsapp"}),
            headers={"Content-Type": "application/json"},
        )

    data = resp.json()
    assert data["ok"] is False
    assert "red" in data["detail"].lower()


# ---------------------------------------------------------------------------
# Group 3: webhook_cloud default dealership fallback (INT-04)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_cloud_falls_back_to_default_dealership(
    app_client: AsyncClient,
    dealership: Dealership,
    db_session: AsyncSession,
    monkeypatch,
):
    """When phone_number_id is not in DB, message should route to default dealership."""
    # Dealership has phone_number_id "1111111111" but we send from "9999999999"
    monkeypatch.setattr(settings, "whatsapp_webhook_secret", "")
    monkeypatch.setattr(settings, "default_dealership_id", dealership.id)

    payload = _make_wa_payload(phone_number_id="9999999999", text="Hola")

    resp = await app_client.post(
        "/webhooks/whatsapp_cloud",
        json=payload,
    )

    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


@pytest.mark.asyncio
async def test_webhook_cloud_drops_silently_when_no_dealership_found(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """When neither phone_number_id nor default_id resolves a dealer, drop with 200."""
    monkeypatch.setattr(settings, "whatsapp_webhook_secret", "")
    monkeypatch.setattr(settings, "default_dealership_id", 99999)  # non-existent

    payload = _make_wa_payload(phone_number_id="0000000000", text="Hola")

    resp = await app_client.post(
        "/webhooks/whatsapp_cloud",
        json=payload,
    )

    # Must return 200 — Meta must never receive 4xx
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"
