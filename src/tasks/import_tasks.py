"""Celery tasks for inventory import."""

import asyncio
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.db.models import Dealership, InventoryItem, ConditionEnum, StatusEnum, Base, Event
from src.db.session import sync_engine
from src.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

SyncSession = sessionmaker(bind=sync_engine, autoflush=False, autocommit=False)


def _validate_sheet_url(url: str) -> bool:
    """Allow only HTTPS Google Sheets CSV export URLs to prevent SSRF."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in ("docs.google.com", "spreadsheets.google.com")
        )
    except Exception:
        return False


@celery_app.task
def import_from_google_sheet(dealership_id: int, sheet_csv_url: str) -> dict:
    """
    Import inventory from Google Sheets CSV export URL.
    Sheet must be published to web as CSV.
    """
    if not _validate_sheet_url(sheet_csv_url):
        logger.warning("import_from_google_sheet: rejected invalid URL=%r", sheet_csv_url)
        return {"error": "invalid URL — only HTTPS Google Sheets CSV export URLs allowed"}
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(sheet_csv_url, follow_redirects=False)
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


@celery_app.task(name="src.tasks.import_tasks.sync_ml_inventory_all_dealers")
def sync_ml_inventory_all_dealers() -> dict:
    from src.adapters.mercadolibre import MercadoLibreAdapter
    session = SyncSession()
    try:
        dealers = session.query(Dealership).filter(
            Dealership.ml_access_token.isnot(None),
            Dealership.ml_user_id.isnot(None),
        ).all()
        total_added = total_updated = total_sold = 0
        for dealer in dealers:
            try:
                result = _sync_dealer_inventory(session, dealer)
                total_added += result["added"]
                total_updated += result["updated"]
                total_sold += result["sold"]
            except Exception as e:
                logger.error("[ML sync] dealer=%s error: %s", dealer.id, e)
        session.commit()
        return {"dealers": len(dealers), "added": total_added, "updated": total_updated, "sold": total_sold}
    finally:
        session.close()


def _sync_dealer_inventory(session, dealer) -> dict:
    from src.adapters.mercadolibre import MercadoLibreAdapter
    start = time.monotonic()
    adapter = MercadoLibreAdapter()
    items: list[dict] = asyncio.run(adapter.sync_all_listings(dealer.id, dealer))

    added = updated = 0
    active_ml_ids: set[str] = set()

    for item_data in items:
        ml_id = item_data.get("ml_item_id")
        if not ml_id:
            continue
        active_ml_ids.add(ml_id)

        existing = session.query(InventoryItem).filter(
            InventoryItem.dealership_id == dealer.id,
            InventoryItem.ml_item_id == ml_id,
        ).first()

        cond_str = item_data.get("condition", "used")
        try:
            condition = ConditionEnum(cond_str)
        except ValueError:
            condition = ConditionEnum.used

        raw_price = item_data.get("price") or 0
        from decimal import Decimal as _Dec
        try:
            price = _Dec(str(raw_price))
        except Exception:
            price = _Dec("0")

        if existing:
            existing.price = price
            existing.km = item_data.get("km")
            existing.photos = item_data.get("photos") or []
            existing.title = item_data.get("title") or existing.title
            existing.brand = item_data.get("brand") or existing.brand
            existing.model = item_data.get("model") or existing.model
            existing.year = item_data.get("year") or existing.year
            existing.condition = condition
            existing.status = StatusEnum.available
            existing.source = "mercadolibre"
            existing.updated_at = datetime.now(UTC)
            updated += 1
        else:
            year = item_data.get("year") or 2000
            brand = item_data.get("brand") or "Desconocido"
            model = item_data.get("model") or "Desconocido"
            new_item = InventoryItem(
                dealership_id=dealer.id,
                ml_item_id=ml_id,
                title=item_data.get("title"),
                brand=brand,
                model=model,
                year=year,
                km=item_data.get("km"),
                price=price,
                currency=item_data.get("currency", "ARS"),
                condition=condition,
                status=StatusEnum.available,
                photos=item_data.get("photos") or [],
                location=item_data.get("location") or None,
                description=item_data.get("description") or None,
                source="mercadolibre",
            )
            session.add(new_item)
            added += 1

    # D-03: Mark sold — CRITICAL: filter source == "mercadolibre" only
    db_available = session.query(InventoryItem).filter(
        InventoryItem.dealership_id == dealer.id,
        InventoryItem.source == "mercadolibre",
        InventoryItem.status == StatusEnum.available,
    ).all()

    sold = 0
    for db_item in db_available:
        if db_item.ml_item_id and db_item.ml_item_id not in active_ml_ids:
            db_item.status = StatusEnum.sold
            db_item.updated_at = datetime.now(UTC)
            sold += 1

    dealer.ml_last_sync_at = datetime.now(UTC)
    dealer.ml_last_sync_added = added
    dealer.ml_last_sync_updated = updated
    dealer.ml_last_sync_sold = sold

    duration = round(time.monotonic() - start, 1)
    event = Event(
        dealership_id=dealer.id,
        type="ml_sync",
        payload={"added": added, "updated": updated, "sold": sold, "duration_seconds": duration, "errors": []},
    )
    session.add(event)

    logger.info("[ML sync] dealer=%s added=%d updated=%d sold=%d duration=%.1fs", dealer.id, added, updated, sold, duration)
    return {"added": added, "updated": updated, "sold": sold}
