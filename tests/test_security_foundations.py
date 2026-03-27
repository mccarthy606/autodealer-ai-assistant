"""Tests for security foundations: CORS, rate limiter, config."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.config import Settings


class TestCorsConfig:
    """Tests for CORS origin configuration."""

    def test_empty_allowed_origins_produces_empty_list(self):
        """CORS with empty ALLOWED_ORIGINS results in empty origins list."""
        s = Settings(allowed_origins="")
        origins = [o.strip() for o in s.allowed_origins.split(",") if o.strip()]
        assert origins == []

    def test_allowed_origins_parsed_correctly(self):
        """CORS with configured origins parses comma-separated list."""
        s = Settings(allowed_origins="https://example.com, https://admin.example.com")
        origins = [o.strip() for o in s.allowed_origins.split(",") if o.strip()]
        assert origins == ["https://example.com", "https://admin.example.com"]


class TestConfigSecurityFields:
    """Tests for new security config fields."""

    def test_config_has_allowed_origins(self):
        s = Settings(allowed_origins="a.com,b.com")
        assert s.allowed_origins == "a.com,b.com"

    def test_config_has_admin_password_hash(self):
        s = Settings(admin_password_hash="$2b$12$test")
        assert s.admin_password_hash == "$2b$12$test"

    def test_config_has_lemon_squeezy_webhook_secret(self):
        s = Settings(lemon_squeezy_webhook_secret="whsec_test123")
        assert s.lemon_squeezy_webhook_secret == "whsec_test123"


class TestRateLimiter:
    """Tests for generic rate limiter."""

    @pytest.mark.asyncio
    async def test_check_rate_limit_returns_tuple(self):
        """check_rate_limit returns (bool, int) tuple."""
        from src.api.rate_limit import check_rate_limit

        # With no Redis, should return (True, 0) as fallback
        with patch("src.api.rate_limit.get_redis", return_value=None):
            result = await check_rate_limit("testkey")
            assert isinstance(result, tuple)
            assert len(result) == 2
            assert result == (True, 0)

    @pytest.mark.asyncio
    async def test_check_rate_limit_custom_prefix(self):
        """check_rate_limit uses custom prefix in Redis key."""
        from src.api.rate_limit import check_rate_limit

        mock_pipe = MagicMock()
        mock_pipe.incr = MagicMock(return_value=mock_pipe)
        mock_pipe.expire = MagicMock(return_value=mock_pipe)
        mock_pipe.ttl = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=[1, True, 55])

        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("src.api.rate_limit.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            result = await check_rate_limit("user123", prefix="api")
            # Verify that the key used includes the custom prefix
            mock_pipe.incr.assert_called_once_with("api:user123")

    @pytest.mark.asyncio
    async def test_check_rate_limit_denied_returns_retry_after(self):
        """check_rate_limit returns (False, retry_after>0) when limit exceeded."""
        from src.api.rate_limit import check_rate_limit

        mock_pipe = MagicMock()
        mock_pipe.incr = MagicMock(return_value=mock_pipe)
        mock_pipe.expire = MagicMock(return_value=mock_pipe)
        mock_pipe.ttl = MagicMock(return_value=mock_pipe)
        # count=21 (over limit of 20), expire ok, ttl=45
        mock_pipe.execute = AsyncMock(return_value=[21, True, 45])

        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipe

        with patch("src.api.rate_limit.get_redis", new_callable=AsyncMock, return_value=mock_redis):
            allowed, retry_after = await check_rate_limit("user123", limit=20)
            assert allowed is False
            assert retry_after > 0
