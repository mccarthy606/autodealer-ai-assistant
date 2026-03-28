"""MercadoLibre OAuth token manager — auto-refresh, Redis-backed for multi-worker safety."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
REFRESH_BUFFER_SECONDS = 1800  # Refresh 30 min before expiry (token lives 6h)


def _ml_keys(did: int) -> tuple[str, str, str, str]:
    """Return (token_key, refresh_key, expires_key, lock_key) for a dealer."""
    return (
        f"ml:{did}:access_token",
        f"ml:{did}:refresh_token",
        f"ml:{did}:token_expires_at",
        f"ml:{did}:refresh_lock",
    )


async def get_valid_token(dealership_id: int = 1, dealer=None) -> str:
    """
    Return a valid ML access token for the given dealership.

    Token state is stored in Redis so all uvicorn workers share the same
    value and only one worker performs the refresh (distributed lock via SET NX).
    Falls back to dealer credentials, then in-process settings values when Redis is unavailable.
    """
    redis = await _get_redis()

    if redis:
        token, expires_at = await _read_from_redis(redis, dealership_id)
    else:
        token = (dealer.ml_access_token if dealer else None) or settings.ml_access_token
        expires_at = None  # unknown age — assume needs refresh check

    if _needs_refresh(token, expires_at):
        token = await _refresh_with_lock(redis, dealership_id, dealer) or token

    return token or (dealer.ml_access_token if dealer else None) or settings.ml_access_token


def _needs_refresh(token: str, expires_at: Optional[datetime]) -> bool:
    if not token:
        return True
    if expires_at is None:
        return True
    now = datetime.now(UTC)
    return now >= (expires_at - timedelta(seconds=REFRESH_BUFFER_SECONDS))


async def _read_from_redis(redis, did: int) -> tuple[str, Optional[datetime]]:
    try:
        token_key, _, expires_key, _ = _ml_keys(did)
        token = await redis.get(token_key) or ""
        expires_raw = await redis.get(expires_key)
        expires_at = None
        if expires_raw:
            expires_at = datetime.fromisoformat(expires_raw)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
        return token, expires_at
    except Exception as e:
        logger.warning("ml_token_manager: Redis read error — %s", e)
        return settings.ml_access_token, None


async def _refresh_with_lock(redis, did: int, dealer=None) -> Optional[str]:
    """
    Acquire a short Redis lock to ensure only one worker performs the refresh.
    Other workers wait briefly then re-read the fresh token from Redis.
    """
    if redis:
        _, _, _, lock_key = _ml_keys(did)
        # SET NX PX — atomic distributed lock, 30s TTL
        acquired = await redis.set(lock_key, "1", nx=True, px=30_000)
        if not acquired:
            # Another worker is refreshing — wait and re-read
            await asyncio.sleep(2)
            token, _ = await _read_from_redis(redis, did)
            return token or None

    return await _do_refresh(redis, did, dealer)


async def _do_refresh(redis, did: int, dealer=None) -> Optional[str]:
    token_key, refresh_key, expires_key, lock_key = _ml_keys(did)

    # DB-first credential reads: prefer dealer-specific values before global settings
    refresh_token = (dealer.ml_refresh_token if dealer else None) or settings.ml_refresh_token
    app_id = (dealer.ml_app_id if dealer else None) or settings.ml_app_id
    client_secret = (dealer.ml_client_secret if dealer else None) or settings.ml_client_secret

    if redis:
        # Prefer token stored in Redis (may be newer than settings after previous refresh)
        stored = await redis.get(refresh_key)
        if stored:
            refresh_token = stored

    if not refresh_token:
        logger.warning("ml_token_manager: token needs refresh but ML_REFRESH_TOKEN not set")
        return None
    if not app_id or not client_secret:
        logger.warning("ml_token_manager: ML_APP_ID / ML_CLIENT_SECRET not configured")
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                ML_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": app_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code != 200:
            logger.error("ml_token_manager: refresh HTTP %s — %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()

        if "access_token" not in data:
            logger.error("ml_token_manager: refresh failed — %s", data.get("message", data))
            return None

        new_access: str = data["access_token"]
        new_refresh: str = data.get("refresh_token", refresh_token)
        expires_in: int = data.get("expires_in", 21600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

        # Persist to Redis — all workers share this, survives process restarts
        if redis:
            pipe = redis.pipeline()
            pipe.set(token_key, new_access, ex=expires_in)
            pipe.set(refresh_key, new_refresh, ex=60 * 60 * 24 * 60)  # 60-day TTL
            pipe.set(expires_key, expires_at.isoformat(), ex=expires_in)
            pipe.delete(lock_key)
            await pipe.execute()

        logger.info(
            "ml_token_manager: token refreshed, expires %s",
            expires_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        return new_access

    except Exception as e:
        logger.error("ml_token_manager: refresh error — %s", e)
        if redis:
            try:
                await redis.delete(lock_key)
            except Exception:
                pass
        return None


async def _get_redis():
    """Return Redis client from the shared pool, or None if unavailable."""
    try:
        from src.api.rate_limit import get_redis
        return await get_redis()
    except Exception:
        return None
