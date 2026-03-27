"""Simple password auth for admin UI."""

import hashlib
import secrets
from typing import Optional

from fastapi import Cookie, Request, Response
from fastapi.responses import RedirectResponse

from src.config import settings

ADMIN_COOKIE = "admin_session"
SESSION_LENGTH = 24  # bytes

_admin_sessions: set[str] = set()


def _check_password(password: str) -> bool:
    if not settings.admin_password:
        return True
    return secrets.compare_digest(password, settings.admin_password)


def _make_token() -> str:
    return secrets.token_hex(SESSION_LENGTH)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(response: Response) -> None:
    token = _make_token()
    _admin_sessions.add(_hash_token(token))
    response.set_cookie(ADMIN_COOKIE, token, httponly=True, samesite="lax", max_age=86400)


def is_authenticated(session: Optional[str] = None) -> bool:
    if not settings.admin_password:
        return True
    if not session:
        return False
    return _hash_token(session) in _admin_sessions


def clear_session(response: Response) -> None:
    response.delete_cookie(ADMIN_COOKIE)


def remove_session(session: Optional[str]) -> None:
    if session:
        _admin_sessions.discard(_hash_token(session))
