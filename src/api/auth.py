"""Admin authentication — Redis sessions + bcrypt passwords."""

import hashlib
import logging
import secrets
from typing import Optional

import bcrypt
from fastapi import Cookie, Request, Response
from fastapi.responses import RedirectResponse

from src.api.rate_limit import get_redis
from src.config import settings

logger = logging.getLogger(__name__)

ADMIN_COOKIE = "admin_session"
SESSION_LENGTH = 24  # bytes

# Fallback when Redis unavailable
_admin_sessions: set[str] = set()


def _check_password(password: str) -> bool:
    """Check password against bcrypt hash or plaintext fallback."""
    if settings.admin_password_hash:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            settings.admin_password_hash.encode("utf-8"),
        )
    if settings.admin_password:
        logger.warning(
            "ADMIN_PASSWORD (plaintext) is set without ADMIN_PASSWORD_HASH. "
            "Generate a hash: python -c \"import bcrypt; print(bcrypt.hashpw(b'PASSWORD', bcrypt.gensalt()).decode())\""
        )
        return secrets.compare_digest(password, settings.admin_password)
    return True  # no password configured


def _make_token() -> str:
    return secrets.token_hex(SESSION_LENGTH)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(response: Response) -> None:
    """Create admin session in Redis (or fallback to in-memory)."""
    token = _make_token()
    token_hash = _hash_token(token)
    r = await get_redis()
    if r:
        await r.set(f"admin:session:{token_hash}", "1", ex=86400)
    else:
        _admin_sessions.add(token_hash)
    secure = "localhost" not in settings.database_url
    response.set_cookie(
        ADMIN_COOKIE, token, httponly=True, samesite="lax",
        max_age=86400, secure=secure,
    )


async def is_authenticated(session: Optional[str] = None) -> bool:
    """Check if session token is valid in Redis (or fallback)."""
    if not settings.admin_password and not settings.admin_password_hash:
        return True
    if not session:
        return False
    token_hash = _hash_token(session)
    r = await get_redis()
    if r:
        return await r.exists(f"admin:session:{token_hash}") > 0
    return token_hash in _admin_sessions


def clear_session(response: Response) -> None:
    response.delete_cookie(ADMIN_COOKIE)


async def remove_session(session: Optional[str]) -> None:
    """Remove session from Redis (and fallback set)."""
    if session:
        token_hash = _hash_token(session)
        r = await get_redis()
        if r:
            await r.delete(f"admin:session:{token_hash}")
        _admin_sessions.discard(token_hash)
