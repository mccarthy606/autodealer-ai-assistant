"""Unit tests for ML inventory sync task."""
import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tasks.import_tasks import _sync_dealer_inventory
from src.db.models import InventoryItem, StatusEnum, ConditionEnum, Event


def _make_dealer(dealer_id=1, ml_access_token="test_token", ml_user_id="123456"):
    dealer = MagicMock()
    dealer.id = dealer_id
    dealer.ml_access_token = ml_access_token
    dealer.ml_user_id = ml_user_id
    return dealer


def _make_ml_item(ml_item_id="MLA123", brand="Toyota", model="Corolla", year=2022, price=5000000, condition="used"):
    return {
        "ml_item_id": ml_item_id,
        "brand": brand,
        "model": model,
        "year": year,
        "km": 50000,
        "price": price,
        "currency": "ARS",
        "condition": condition,
        "status": "available",
        "photos": [],
        "title": f"{brand} {model} {year}",
        "location": "",
        "description": "",
    }


class TestSyncSkipsUnconfiguredDealer:
    def test_sync_skips_unconfigured_dealer(self):
        from src.tasks.import_tasks import sync_ml_inventory_all_dealers
        with patch("src.tasks.import_tasks.SyncSession") as MockSession:
            session = MagicMock()
            MockSession.return_value = session
            session.query.return_value.filter.return_value.all.return_value = []
            result = sync_ml_inventory_all_dealers()
        assert result["dealers"] == 0
        assert result["added"] == 0
        assert result["updated"] == 0
        assert result["sold"] == 0


class TestSyncAddsNewItems:
    def test_sync_adds_new_items(self):
        dealer = _make_dealer()
        session = MagicMock()
        added_items = []
        session.add.side_effect = added_items.append
        session.query.return_value.filter.return_value.first.return_value = None
        session.query.return_value.filter.return_value.all.return_value = []
        ml_items = [_make_ml_item(ml_item_id="MLA123")]
        with patch("src.tasks.import_tasks.asyncio.run", return_value=ml_items):
            result = _sync_dealer_inventory(session, dealer)
        assert result["added"] == 1
        assert result["updated"] == 0
        inv_items = [x for x in added_items if isinstance(x, InventoryItem)]
        assert len(inv_items) == 1
        assert inv_items[0].ml_item_id == "MLA123"
        assert inv_items[0].source == "mercadolibre"
        assert inv_items[0].status == StatusEnum.available


class TestSyncUpdatesExistingItem:
    def test_sync_updates_existing_item(self):
        dealer = _make_dealer()
        session = MagicMock()
        existing = InventoryItem(
            dealership_id=1, ml_item_id="MLA123", brand="Toyota", model="Corolla",
            year=2022, condition=ConditionEnum.used, price=Decimal("4000000"),
            km=50000, source="mercadolibre", status=StatusEnum.available,
        )
        def _query(model):
            q = MagicMock()
            if model is InventoryItem:
                q.filter.return_value = q
                q.first.return_value = existing
                q.all.return_value = [existing]
            return q
        session.query.side_effect = _query
        session.add = MagicMock()
        ml_items = [_make_ml_item(ml_item_id="MLA123", price=5500000)]
        with patch("src.tasks.import_tasks.asyncio.run", return_value=ml_items):
            result = _sync_dealer_inventory(session, dealer)
        assert result["updated"] == 1
        assert result["added"] == 0
        assert existing.price == Decimal("5500000")


class TestSyncMarksSold:
    def test_sync_marks_sold(self):
        dealer = _make_dealer()
        session = MagicMock()
        stale = InventoryItem(
            dealership_id=1, ml_item_id="MLA999", brand="Ford", model="Focus",
            year=2019, condition=ConditionEnum.used, price=Decimal("3000000"),
            source="mercadolibre", status=StatusEnum.available,
        )
        call_count = [0]
        def _query(model):
            q = MagicMock()
            if model is InventoryItem:
                q.filter.return_value = q
                call_count[0] += 1
                if call_count[0] <= 1:
                    q.first.return_value = None
                    q.all.return_value = [stale]
                else:
                    q.first.return_value = None
                    q.all.return_value = [stale]
            return q
        session.query.side_effect = _query
        session.add = MagicMock()
        with patch("src.tasks.import_tasks.asyncio.run", return_value=[]):
            result = _sync_dealer_inventory(session, dealer)
        assert result["sold"] == 1
        assert stale.status == StatusEnum.sold


class TestSyncDoesNotMarkCsvItemsSold:
    def test_sync_does_not_mark_csv_items_sold(self):
        dealer = _make_dealer()
        session = MagicMock()
        csv_item = InventoryItem(
            dealership_id=1, ml_item_id="MLA888", brand="Fiat", model="Cronos",
            year=2021, condition=ConditionEnum.used, price=Decimal("2500000"),
            source="csv", status=StatusEnum.available,
        )
        def _query(model):
            q = MagicMock()
            if model is InventoryItem:
                q.filter.return_value = q
                q.first.return_value = None
                q.all.return_value = []  # source filter returns empty for csv items
            return q
        session.query.side_effect = _query
        session.add = MagicMock()
        with patch("src.tasks.import_tasks.asyncio.run", return_value=[]):
            result = _sync_dealer_inventory(session, dealer)
        assert result["sold"] == 0
        assert csv_item.status == StatusEnum.available


class TestSyncLogsEvent:
    def test_sync_logs_event(self):
        dealer = _make_dealer()
        session = MagicMock()
        added_items = []
        session.add.side_effect = added_items.append
        session.query.return_value.filter.return_value.first.return_value = None
        session.query.return_value.filter.return_value.all.return_value = []
        with patch("src.tasks.import_tasks.asyncio.run", return_value=[_make_ml_item()]):
            _sync_dealer_inventory(session, dealer)
        events = [x for x in added_items if isinstance(x, Event)]
        assert len(events) == 1
        assert events[0].type == "ml_sync"
        assert "added" in events[0].payload
        assert "updated" in events[0].payload
        assert "sold" in events[0].payload
        assert "duration_seconds" in events[0].payload
