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


async def check_rate_limit(phone: str, limit: int = 20, window_seconds: int = 60) -> bool:
    """
    Check if phone is within rate limit.
    Returns True if allowed, False if rate limited.
    """
    r = await get_redis()
    if not r:
        return True
    key = f"rate:whatsapp:{phone}"
    try:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds)
        results = await pipe.execute()
        count = results[0]
        return count <= limit
    except Exception as e:
        logger.warning("Rate limit check failed: %s", e)
        return True
