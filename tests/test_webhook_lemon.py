"""Tests for Lemon Squeezy webhook with HMAC signature verification."""

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch


VALID_PAYLOAD = json.dumps({"meta": {"event_name": "subscription_created"}, "data": {}}).encode()
SECRET = "test_webhook_secret_123"


def _sign(payload: bytes, secret: str) -> str:
    """Create HMAC-SHA256 signature."""
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


@pytest.fixture
def app_with_secret():
    """Get FastAPI app with webhook secret configured."""
    with patch("src.config.settings") as mock_settings:
        # Copy all real settings attributes
        from src.config import Settings
        real = Settings()
        for field in real.model_fields:
            setattr(mock_settings, field, getattr(real, field))
        mock_settings.lemon_squeezy_webhook_secret = SECRET
        # Need to reimport to pick up patched settings
        # Instead, patch at the route module level
    return None  # We'll use a different approach


class TestLemonWebhookSignatureVerification:
    """Tests for _verify_signature helper."""

    def test_valid_signature_accepted(self):
        from src.api.routes.webhook_lemon import _verify_signature
        sig = _sign(VALID_PAYLOAD, SECRET)
        assert _verify_signature(VALID_PAYLOAD, sig, SECRET) is True

    def test_invalid_signature_rejected(self):
        from src.api.routes.webhook_lemon import _verify_signature
        assert _verify_signature(VALID_PAYLOAD, "badsig", SECRET) is False

    def test_empty_signature_rejected(self):
        from src.api.routes.webhook_lemon import _verify_signature
        assert _verify_signature(VALID_PAYLOAD, "", SECRET) is False


class TestLemonWebhookEndpoint:
    """Tests for the /webhooks/lemon-squeezy POST endpoint."""

    @pytest.mark.asyncio
    async def test_valid_signature_returns_200(self):
        with patch("src.api.routes.webhook_lemon.settings") as mock_s:
            mock_s.lemon_squeezy_webhook_secret = SECRET
            from src.main import app
            sig = _sign(VALID_PAYLOAD, SECRET)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/webhooks/lemon-squeezy",
                    content=VALID_PAYLOAD,
                    headers={"x-signature": sig, "content-type": "application/json"},
                )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
            assert resp.json()["event"] == "subscription_created"

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self):
        with patch("src.api.routes.webhook_lemon.settings") as mock_s:
            mock_s.lemon_squeezy_webhook_secret = SECRET
            from src.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/webhooks/lemon-squeezy",
                    content=VALID_PAYLOAD,
                    headers={"x-signature": "invalidsig", "content-type": "application/json"},
                )
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_signature_returns_401(self):
        with patch("src.api.routes.webhook_lemon.settings") as mock_s:
            mock_s.lemon_squeezy_webhook_secret = SECRET
            from src.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/webhooks/lemon-squeezy",
                    content=VALID_PAYLOAD,
                    headers={"content-type": "application/json"},
                )
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_no_secret_configured_returns_200(self):
        with patch("src.api.routes.webhook_lemon.settings") as mock_s:
            mock_s.lemon_squeezy_webhook_secret = ""
            from src.main import app
            sig = _sign(VALID_PAYLOAD, SECRET)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/webhooks/lemon-squeezy",
                    content=VALID_PAYLOAD,
                    headers={"x-signature": sig, "content-type": "application/json"},
                )
            assert resp.status_code == 200  # 200 to prevent retry storms

    @pytest.mark.asyncio
    async def test_invalid_json_returns_400(self):
        bad_body = b"not valid json at all"
        with patch("src.api.routes.webhook_lemon.settings") as mock_s:
            mock_s.lemon_squeezy_webhook_secret = SECRET
            from src.main import app
            sig = _sign(bad_body, SECRET)
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/webhooks/lemon-squeezy",
                    content=bad_body,
                    headers={"x-signature": sig, "content-type": "application/json"},
                )
            assert resp.status_code == 400
