"""Shared utilities for admin UI route modules."""

from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api.auth import is_authenticated

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def auth_check(request: Request) -> Optional[RedirectResponse]:
    """Return redirect to login if not authenticated, else None."""
    session = request.cookies.get("admin_session")
    if not is_authenticated(session):
        return RedirectResponse(url="/admin/ui/login", status_code=302)
    return None
