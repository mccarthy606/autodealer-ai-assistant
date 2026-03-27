"""Celery tasks for inventory import."""

import logging
from decimal import Decimal

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.db.models import InventoryItem, ConditionEnum, StatusEnum, Base
from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

sync_engine = create_engine(settings.database_url)
SyncSession = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)


@celery_app.task
def import_from_google_sheet(dealership_id: int, sheet_csv_url: str) -> dict:
    """
    Import inventory from Google Sheets CSV export URL.
    Sheet must be published to web as CSV.
    """
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(sheet_csv_url)
            resp.raise_for_status()
            content = resp.text
    except Exception as e:
        logger.error("Failed to fetch sheet: %s", e)
        return {"error": str(e), "added": 0, "updated": 0}

    import csv
    import io

    reader = csv.DictReader(io.StringIO(content))
    added = 0
    updated = 0

    def _norm(s):
        return (s or "").strip()

    def _parse_int(s):
        if not s:
            return None
        s = "".join(c for c in str(s) if c.isdigit() or c == "-")
        return int(s) if s else None

    def _parse_decimal(s):
        if not s:
            return None
        s = str(s).replace(",", ".").replace(" ", "")
        try:
            return Decimal(s)
        except Exception:
            return None

    def _parse_condition(s):
        s = (s or "").lower().strip()
        if s in ("new", "nuevo", "0km", "0 km"):
            return ConditionEnum.new
        if s in ("used", "usado"):
            return ConditionEnum.used
        if s in ("zero_km", "zero km"):
            return ConditionEnum.zero_km
        return ConditionEnum.used

    def _parse_status(s):
        s = (s or "").lower().strip()
        if s in ("sold", "vendido"):
            return StatusEnum.sold
        if s in ("in_transit", "en tránsito"):
            return StatusEnum.in_transit
        if s in ("preorder",):
            return StatusEnum.preorder
        return StatusEnum.available

    session = SyncSession()
    try:
        for row_num, row in enumerate(reader, start=2):
            try:
                brand = _norm(row.get("brand", row.get("marca", "")))
                model = _norm(row.get("model", row.get("modelo", "")))
                year = _parse_int(row.get("year", row.get("año", "")))
                price = _parse_decimal(row.get("price", row.get("precio", "")))

                if not brand or not model or not year or price is None:
                    continue

                external_id = _norm(row.get("external_id", "")) or f"{brand}_{model}_{year}_{row_num}"

                existing = (
                    session.query(InventoryItem)
                    .filter(
                        InventoryItem.dealership_id == dealership_id,
                        InventoryItem.external_id == external_id,
                    )
                    .first()
                )

                condition = _parse_condition(row.get("condition", "used"))
                status = _parse_status(row.get("status", "available"))
                trim = _norm(row.get("trim", "")) or None
                km = _parse_int(row.get("km", row.get("kilometraje", "")))
                location = _norm(row.get("location", "")) or None

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
                    existing.source = "sheet"
                    updated += 1
                else:
                    item = InventoryItem(
                        dealership_id=dealership_id,
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
                        source="sheet",
                    )
                    session.add(item)
                    added += 1
            except Exception as e:
                logger.warning("Row %s: %s", row_num, e)

        session.commit()
    finally:
        session.close()

    logger.info("Sheet import: added=%s updated=%s", added, updated)
    return {"added": added, "updated": updated}
