"""Tests for the deep /health endpoint (DEP-05)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from src.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    async def test_health_all_ok(self, client: AsyncClient):
        """All components healthy: HTTP 200, status=ok."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_inspect = MagicMock()
        mock_inspect.ping = MagicMock(return_value={"worker1@host": {"ok": "pong"}})
        mock_celery = MagicMock()
        mock_celery.control.inspect = MagicMock(return_value=mock_inspect)

        with (
            patch("src.api.rate_limit.get_redis", AsyncMock(return_value=mock_redis)),
            patch("src.db.session.AsyncSessionLocal", return_value=mock_session_ctx),
            patch("src.tasks.celery_app.celery_app", mock_celery),
        ):
            response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"
        assert body["redis"] == "ok"
        assert body["celery"] == "ok"

    async def test_health_db_error(self, client: AsyncClient):
        """DB failure: HTTP 503, status=degraded, db=error."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("connection refused"))
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_inspect = MagicMock()
        mock_inspect.ping = MagicMock(return_value={"worker1@host": {"ok": "pong"}})
        mock_celery = MagicMock()
        mock_celery.control.inspect = MagicMock(return_value=mock_inspect)

        with (
            patch("src.api.rate_limit.get_redis", AsyncMock(return_value=mock_redis)),
            patch("src.db.session.AsyncSessionLocal", return_value=mock_session_ctx),
            patch("src.tasks.celery_app.celery_app", mock_celery),
        ):
            response = await client.get("/health")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["db"] == "error"
        assert body["redis"] == "ok"

    async def test_health_redis_error(self, client: AsyncClient):
        """Redis failure: HTTP 503, status=degraded, redis=error."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=Exception("redis down"))

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_inspect = MagicMock()
        mock_inspect.ping = MagicMock(return_value={"worker1@host": {"ok": "pong"}})
        mock_celery = MagicMock()
        mock_celery.control.inspect = MagicMock(return_value=mock_inspect)

        with (
            patch("src.api.rate_limit.get_redis", AsyncMock(return_value=mock_redis)),
            patch("src.db.session.AsyncSessionLocal", return_value=mock_session_ctx),
            patch("src.tasks.celery_app.celery_app", mock_celery),
        ):
            response = await client.get("/health")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["redis"] == "error"
        assert body["db"] == "ok"

    async def test_health_celery_timeout(self, client: AsyncClient):
        """Celery timeout: HTTP 200 still, status=ok, celery=timeout (best-effort per D-21)."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock())
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_inspect = MagicMock()
        # inspect.ping() returns None when no workers respond within timeout
        mock_inspect.ping = MagicMock(return_value=None)
        mock_celery = MagicMock()
        mock_celery.control.inspect = MagicMock(return_value=mock_inspect)

        with (
            patch("src.api.rate_limit.get_redis", AsyncMock(return_value=mock_redis)),
            patch("src.db.session.AsyncSessionLocal", return_value=mock_session_ctx),
            patch("src.tasks.celery_app.celery_app", mock_celery),
        ):
            response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["celery"] == "timeout"
        assert body["db"] == "ok"
        assert body["redis"] == "ok"
