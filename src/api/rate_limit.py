"""Rate limiting via Redis."""

import logging
from typing import Optional

import redis.asyncio as redis

from src.config import settings

logger = logging.getLogger(__name__)

_redis: Optional[redis.Redis] = None


async def get_redis() -> Optional[redis.Redis]:
    global _redis
    if _redis is None and settings.redis_url:
        try:
            _redis = redis.from_url(settings.redis_url, decode_responses=True)
        except Exception as e:
            logger.warning("Redis connection failed: %s", e)
    return _redis


async def check_rate_limit(key: str, limit: int = 20, window_seconds: int = 60, prefix: str = "rate") -> tuple[bool, int]:
    """
    Check if key is within rate limit.
    Returns (allowed, retry_after) where retry_after is TTL remaining when denied, 0 when allowed.
    """
    r = await get_redis()
    if not r:
        return (True, 0)
    redis_key = f"{prefix}:{key}"
    try:
        pipe = r.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds)
        pipe.ttl(redis_key)
        results = await pipe.execute()
        count = results[0]
        ttl = results[2]
        if count <= limit:
            return (True, 0)
        retry_after = max(ttl, 1)
        return (False, retry_after)
    except Exception as e:
        logger.warning("Rate limit check failed: %s", e)
        return (True, 0)
