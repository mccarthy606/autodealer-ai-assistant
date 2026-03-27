"""Import routes - CSV and Google Sheets."""

import csv
import io
import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.config import settings
from src.db.models import InventoryItem, Dealership, ConditionEnum, StatusEnum, Event

router = APIRouter(tags=["import"])
logger = logging.getLogger(__name__)


def _norm(s: str) -> str:
    return (s or "").strip()


def _parse_condition(s: str) -> ConditionEnum:
    s = (s or "").lower().strip()
    if s in ("new", "nuevo", "0km", "0 km"):
        return ConditionEnum.new
    if s in ("used", "usado", "usada"):
        return ConditionEnum.used
    if s in ("zero_km", "zero km", "zerokm"):
        return ConditionEnum.zero_km
    return ConditionEnum.used


def _parse_status(s: str) -> StatusEnum:
    s = (s or "").lower().strip()
    if s in ("available", "disponible", "en stock"):
        return StatusEnum.available
    if s in ("in_transit", "en tránsito", "en transito"):
        return StatusEnum.in_transit
    if s in ("preorder", "preorden"):
        return StatusEnum.preorder
    if s in ("sold", "vendido"):
        return StatusEnum.sold
    return StatusEnum.available


def _parse_int(s: str) -> int | None:
    if not s:
        return None
    s = "".join(c for c in str(s) if c.isdigit() or c == "-")
    return int(s) if s else None


def _parse_decimal(s: str) -> Decimal | None:
    if not s:
        return None
    s = str(s).replace(",", ".").replace(" ", "")
    try:
        return Decimal(s)
    except Exception:
        return None


@router.post("/csv")
async def import_csv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    dealership_id: int | None = None,
) -> dict[str, Any]:
    """
    Import inventory from CSV.
    Expected columns: brand, model, year, condition, price [, trim, km, status, external_id, location ]
    """
    did = dealership_id or settings.default_dealership_id
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    added = 0
    updated = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            brand = _norm(row.get("brand", row.get("marca", "")))
            model = _norm(row.get("model", row.get("modelo", "")))
            year = _parse_int(row.get("year", row.get("año", row.get("anio", ""))))
            price = _parse_decimal(row.get("price", row.get("precio", "")))

            if not brand or not model or not year or price is None:
                errors.append(f"Row {row_num}: missing brand/model/year/price")
                continue

            external_id = _norm(row.get("external_id", row.get("external id", "")))
            if not external_id:
                external_id = f"{brand}_{model}_{year}_{row_num}"

            # Upsert by external_id
            stmt = select(InventoryItem).where(
                InventoryItem.dealership_id == did,
                InventoryItem.external_id == external_id,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            condition = _parse_condition(row.get("condition", row.get("condicion", "used")))
            status = _parse_status(row.get("status", row.get("estado", "available")))
            trim = _norm(row.get("trim", "")) or None
            km = _parse_int(row.get("km", row.get("kilometraje", "")))
            location = _norm(row.get("location", row.get("ubicacion", ""))) or None

            if existing:
                existing.brand = brand
                existing.model = model
                existing.trim = trim
                existing.year = year
                existing.condition = condition
                existing.km = km
                existing.price = price
                existing.status = status
                existing.location = location
                existing.source = "csv"
                updated += 1
            else:
                item = InventoryItem(
                    dealership_id=did,
                    brand=brand,
                    model=model,
                    trim=trim,
                    year=year,
                    condition=condition,
                    km=km,
                    price=price,
                    currency="ARS",
                    status=status,
                    location=location,
                    external_id=external_id,
                    source="csv",
                )
                session.add(item)
                added += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {e}")

    # Log event
    ev = Event(
        dealership_id=did,
        type="inventory_import",
        payload={"source": "csv", "added": added, "updated": updated, "errors": len(errors)},
    )
    session.add(ev)

    return {"added": added, "updated": updated, "errors": errors}
