"""Admin authentication — Redis sessions + bcrypt passwords."""

import hashlib
import json
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

# Fallback when Redis unavailable: maps token_hash -> dealership_id
_admin_sessions: dict[str, int] = {}


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


async def create_session(response: Response, dealership_id: int) -> None:
    """Create admin session in Redis (or fallback to in-memory).

    Session value is stored as JSON: {"dealership_id": N}.
    """
    token = _make_token()
    token_hash = _hash_token(token)
    r = await get_redis()
    if r:
        value = json.dumps({"dealership_id": dealership_id})
        await r.set(f"admin:session:{token_hash}", value, ex=86400)
    else:
        _admin_sessions[token_hash] = dealership_id
    secure = "localhost" not in settings.database_url
    response.set_cookie(
        ADMIN_COOKIE, token, httponly=True, samesite="lax",
        max_age=86400, secure=secure,
    )


async def get_session_dealership_id(session_token: Optional[str]) -> Optional[int]:
    """Return dealership_id from session, or None if invalid/missing."""
    if not session_token:
        return None
    token_hash = _hash_token(session_token)
    r = await get_redis()
    if r:
        raw = await r.get(f"admin:session:{token_hash}")
        if raw is None:
            return None
        # raw may be bytes or str depending on redis client decode setting
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return json.loads(raw)["dealership_id"]
        except (json.JSONDecodeError, KeyError, TypeError):
            # Backward compat: old sessions stored plain "1"
            return 1
    return _admin_sessions.get(token_hash)


async def is_authenticated(session: Optional[str] = None) -> bool:
    """Check if session token is valid in Redis (or fallback)."""
    if not settings.admin_password and not settings.admin_password_hash:
        return True
    result = await get_session_dealership_id(session)
    return result is not None


def clear_session(response: Response) -> None:
    response.delete_cookie(ADMIN_COOKIE)


async def remove_session(session: Optional[str]) -> None:
    """Remove session from Redis (and fallback dict)."""
    if session:
        token_hash = _hash_token(session)
        r = await get_redis()
        if r:
            await r.delete(f"admin:session:{token_hash}")
        _admin_sessions.pop(token_hash, None)
