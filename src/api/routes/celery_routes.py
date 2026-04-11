"""Endpoints para disparar tareas Celery (import Google Sheets)."""

from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth import is_authenticated
from src.tasks.import_tasks import import_from_google_sheet


async def _require_admin(admin_session: str = Cookie(default=None)) -> None:
    if not await is_authenticated(admin_session):
        raise HTTPException(status_code=401, detail="Not authenticated")


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(_require_admin)])


class GoogleSheetImportRequest(BaseModel):
    dealership_id: int
    sheet_csv_url: str


@router.post("/import/google-sheet")
async def trigger_google_sheet_import(data: GoogleSheetImportRequest) -> dict[str, Any]:
    """
    Dispara importación desde Google Sheets (publicado como CSV).
    Ejecuta en background vía Celery.
    """
    result = import_from_google_sheet.delay(data.dealership_id, data.sheet_csv_url)
    return {"task_id": result.id, "status": "queued"}
