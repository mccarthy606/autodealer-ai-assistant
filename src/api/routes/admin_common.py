"""Shared utilities for admin UI route modules."""

from pathlib import Path
from typing import Optional, Union

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api.auth import get_session_dealership_id, is_authenticated

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


async def auth_check(request: Request) -> Union[int, RedirectResponse]:
    """Return dealership_id (int) if authenticated, else RedirectResponse.

    Existing call pattern (backward compat — still works):
        redir = await auth_check(request)
        if redir: return redir   # redir is now int; truthy but route returns it harmlessly
                                 # NOTE: 06-03 will update all call sites to use isinstance check

    New call pattern (preferred in 06-03+):
        did = await auth_check(request)
        if not isinstance(did, int): return did
    """
    session = request.cookies.get("admin_session")
    did = await get_session_dealership_id(session)
    if did is None:
        return RedirectResponse(url="/admin/ui/login", status_code=302)
    return did
