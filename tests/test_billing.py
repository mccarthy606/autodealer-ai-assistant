"""Billing service, webhook_lemon handler, and subscription gate tests.

Coverage targets:
- is_subscription_active(): 11 tests (all branches including naive datetime normalization)
- map_ls_status(): 4 tests
- webhook_lemon route: 7 integration tests
- webhook_cloud subscription gate: 2 tests
- followup_task subscription gate: 1 test
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import Conversation, Dealership
from src.services.billing import is_subscription_active, map_ls_status


# ---------------------------------------------------------------------------
# Stub for unit tests — no DB, no fixtures
# ---------------------------------------------------------------------------

class StubDealer:
    """Minimal stand-in for Dealership for pure-unit tests of is_subscription_active()."""

    def __init__(self, **kw):
        self.subscription_status = kw.get("subscription_status")
        self.grace_period_ends_at = kw.get("grace_period_ends_at")
        self.trial_ends_at = kw.get("trial_ends_at")


# ---------------------------------------------------------------------------
# Helper: sign a payload for lemon-squeezy webhook tests
# ---------------------------------------------------------------------------

_TEST_WEBHOOK_SECRET = "test-webhook-secret"


def _sign(payload_bytes: bytes, secret: str = _TEST_WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Group 1: is_subscription_active() — 11 unit tests
# ---------------------------------------------------------------------------

def test_active_returns_true():
    assert is_subscription_active(StubDealer(subscription_status="active")) is True


def test_trial_returns_true():
    assert is_subscription_active(StubDealer(subscription_status="trial")) is True


def test_past_due_in_grace_returns_true():
    dealer = StubDealer(
        subscription_status="past_due",
        grace_period_ends_at=datetime.now(UTC) + timedelta(days=3),
    )
    assert is_subscription_active(dealer) is True


def test_past_due_grace_expired_returns_false():
    dealer = StubDealer(
        subscription_status="past_due",
        grace_period_ends_at=datetime.now(UTC) - timedelta(days=1),
    )
    assert is_subscription_active(dealer) is False


def test_past_due_no_grace_returns_false():
    dealer = StubDealer(subscription_status="past_due", grace_period_ends_at=None)
    assert is_subscription_active(dealer) is False


def test_cancelled_returns_false():
    assert is_subscription_active(StubDealer(subscription_status="cancelled")) is False


def test_expired_returns_false():
    assert is_subscription_active(StubDealer(subscription_status="expired")) is False


def test_none_status_with_future_trial_returns_true():
    """D-19 exception: no subscription_status but trial_ends_at in the future."""
    dealer = StubDealer(
        subscription_status=None,
        trial_ends_at=datetime.now(UTC) + timedelta(days=5),
    )
    assert is_subscription_active(dealer) is True


def test_none_status_no_trial_returns_false():
    dealer = StubDealer(subscription_status=None, trial_ends_at=None)
    assert is_subscription_active(dealer) is False


def test_none_dealership_returns_false():
    """is_subscription_active(None) must return False, not raise."""
    assert is_subscription_active(None) is False


def test_naive_datetime_no_typeerror():
    """Billing.py normalizes naive datetimes via .replace(tzinfo=UTC).
    Feeding a naive future datetime must return True without raising TypeError.
    """
    naive_future = (datetime.now(UTC) + timedelta(days=3)).replace(tzinfo=None)
    dealer = StubDealer(subscription_status="past_due", grace_period_ends_at=naive_future)
    # Must not raise TypeError; must return True (future grace period)
    result = is_subscription_active(dealer)
    assert result is True


# ---------------------------------------------------------------------------
# Group 2: map_ls_status() — 4 unit tests
# ---------------------------------------------------------------------------

def test_on_trial_maps_to_trial():
    assert map_ls_status("on_trial") == "trial"


def test_paused_maps_to_past_due():
    assert map_ls_status("paused") == "past_due"


def test_unpaid_maps_to_past_due():
    assert map_ls_status("unpaid") == "past_due"


def test_unknown_maps_to_expired():
    """Unknown LS statuses must map to 'expired' — most restrictive safe default."""
    assert map_ls_status("some_future_status_we_dont_know") == "expired"


# ---------------------------------------------------------------------------
# App fixture for route integration tests
# Overrides get_db to inject the test db_session instead of real Postgres.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def app_client(db_session: AsyncSession):
    """AsyncClient bound to the FastAPI app with test DB injected."""
    from src.main import app
    from src.api.deps import get_db

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Group 3: webhook_lemon integration tests — 7 tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_subscription_created_writes_fields(
    app_client: AsyncClient,
    dealership: Dealership,
    db_session: AsyncSession,
    monkeypatch,
):
    """subscription_created event must write all 5 fields to the dealership row."""
    monkeypatch.setattr(settings, "lemon_squeezy_webhook_secret", _TEST_WEBHOOK_SECRET)

    payload = {
        "meta": {
            "event_name": "subscription_created",
            "custom_data": {"dealership_id": str(dealership.id)},
        },
        "data": {
            "type": "subscriptions",
            "id": "sub_999",
            "attributes": {
                "status": "on_trial",
                "customer_id": 555,
                "variant_name": "basic",
                "trial_ends_at": "2026-04-03T13:43:48.000000Z",
            },
        },
    }
    payload_bytes = json.dumps(payload).encode()
    sig = _sign(payload_bytes)

    resp = await app_client.post(
        "/webhooks/lemon-squeezy",
        content=payload_bytes,
        headers={"x-signature": sig, "content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Reload from DB to verify all 5 fields
    await db_session.refresh(dealership)
    assert dealership.subscription_id == "sub_999"
    assert dealership.subscription_status == "trial"
    assert dealership.ls_customer_id == "555"
    assert dealership.plan == "basic"
    assert dealership.trial_ends_at is not None


@pytest.mark.asyncio
async def test_webhook_subscription_payment_failed_uses_attrs_subscription_id(
    app_client: AsyncClient,
    dealership: Dealership,
    db_session: AsyncSession,
    monkeypatch,
):
    """payment_failed handler must read data.attributes.subscription_id (integer), NOT data.id.

    data.id = "invoice_888"  <- invoice ID (wrong field)
    data.attributes.subscription_id = 999  <- real subscription ID (correct field)
    """
    monkeypatch.setattr(settings, "lemon_squeezy_webhook_secret", _TEST_WEBHOOK_SECRET)

    payload = {
        "meta": {
            "event_name": "subscription_payment_failed",
            "custom_data": {"dealership_id": str(dealership.id)},
        },
        "data": {
            "type": "subscription_invoices",
            "id": "invoice_888",  # invoice ID — must NOT be used as subscription_id
            "attributes": {
                "subscription_id": 999,  # integer — this is the real subscription ID
                "customer_id": 555,
                "status": "failed",
            },
        },
    }
    payload_bytes = json.dumps(payload).encode()
    sig = _sign(payload_bytes)

    resp = await app_client.post(
        "/webhooks/lemon-squeezy",
        content=payload_bytes,
        headers={"x-signature": sig, "content-type": "application/json"},
    )
    assert resp.status_code == 200

    await db_session.refresh(dealership)
    # Must use attributes.subscription_id (999), not data.id ("invoice_888")
    assert dealership.subscription_id == "999"
    assert dealership.subscription_status == "past_due"
    # grace_period_ends_at must be approx now+7d (within ±60 seconds)
    assert dealership.grace_period_ends_at is not None
    expected_grace = datetime.now(UTC) + timedelta(days=7)
    grace = dealership.grace_period_ends_at
    if grace.tzinfo is None:
        grace = grace.replace(tzinfo=UTC)
    diff = abs((grace - expected_grace).total_seconds())
    assert diff < 60, f"grace_period_ends_at too far from now+7d: diff={diff}s"


@pytest.mark.asyncio
async def test_webhook_subscription_cancelled(
    app_client: AsyncClient,
    dealership: Dealership,
    db_session: AsyncSession,
    monkeypatch,
):
    """subscription_cancelled must set status='cancelled'."""
    monkeypatch.setattr(settings, "lemon_squeezy_webhook_secret", _TEST_WEBHOOK_SECRET)

    payload = {
        "meta": {
            "event_name": "subscription_cancelled",
            "custom_data": {"dealership_id": str(dealership.id)},
        },
        "data": {
            "type": "subscriptions",
            "id": "sub_999",
            "attributes": {"status": "cancelled"},
        },
    }
    payload_bytes = json.dumps(payload).encode()
    resp = await app_client.post(
        "/webhooks/lemon-squeezy",
        content=payload_bytes,
        headers={"x-signature": _sign(payload_bytes), "content-type": "application/json"},
    )
    assert resp.status_code == 200
    await db_session.refresh(dealership)
    assert dealership.subscription_status == "cancelled"


@pytest.mark.asyncio
async def test_webhook_subscription_expired_clears_grace(
    app_client: AsyncClient,
    dealership: Dealership,
    db_session: AsyncSession,
    monkeypatch,
):
    """subscription_expired must set status='expired' and clear grace_period_ends_at."""
    monkeypatch.setattr(settings, "lemon_squeezy_webhook_secret", _TEST_WEBHOOK_SECRET)

    # Pre-set a grace date to confirm it is cleared
    dealership.grace_period_ends_at = datetime.now(UTC) + timedelta(days=3)
    await db_session.flush()

    payload = {
        "meta": {
            "event_name": "subscription_expired",
            "custom_data": {"dealership_id": str(dealership.id)},
        },
        "data": {
            "type": "subscriptions",
            "id": "sub_999",
            "attributes": {"status": "expired"},
        },
    }
    payload_bytes = json.dumps(payload).encode()
    resp = await app_client.post(
        "/webhooks/lemon-squeezy",
        content=payload_bytes,
        headers={"x-signature": _sign(payload_bytes), "content-type": "application/json"},
    )
    assert resp.status_code == 200
    await db_session.refresh(dealership)
    assert dealership.subscription_status == "expired"
    assert dealership.grace_period_ends_at is None


@pytest.mark.asyncio
async def test_webhook_missing_custom_data_returns_200(
    app_client: AsyncClient,
    monkeypatch,
):
    """Missing custom_data.dealership_id must return 200 ok without raising."""
    monkeypatch.setattr(settings, "lemon_squeezy_webhook_secret", _TEST_WEBHOOK_SECRET)

    payload = {
        "meta": {
            "event_name": "subscription_created",
            # no custom_data
        },
        "data": {
            "type": "subscriptions",
            "id": "sub_xxx",
            "attributes": {"status": "on_trial", "customer_id": 1, "variant_name": "basic"},
        },
    }
    payload_bytes = json.dumps(payload).encode()
    resp = await app_client.post(
        "/webhooks/lemon-squeezy",
        content=payload_bytes,
        headers={"x-signature": _sign(payload_bytes), "content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_unknown_dealership_returns_200(
    app_client: AsyncClient,
    monkeypatch,
):
    """Unknown dealership_id (99999) must return 200 ok, not raise."""
    monkeypatch.setattr(settings, "lemon_squeezy_webhook_secret", _TEST_WEBHOOK_SECRET)

    payload = {
        "meta": {
            "event_name": "subscription_created",
            "custom_data": {"dealership_id": "99999"},
        },
        "data": {
            "type": "subscriptions",
            "id": "sub_xxx",
            "attributes": {"status": "active", "customer_id": 1, "variant_name": "basic"},
        },
    }
    payload_bytes = json.dumps(payload).encode()
    resp = await app_client.post(
        "/webhooks/lemon-squeezy",
        content=payload_bytes,
        headers={"x-signature": _sign(payload_bytes), "content-type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_webhook_invalid_signature_returns_401(
    app_client: AsyncClient,
    monkeypatch,
):
    """Wrong X-Signature header must result in 401."""
    monkeypatch.setattr(settings, "lemon_squeezy_webhook_secret", _TEST_WEBHOOK_SECRET)

    payload = {"meta": {"event_name": "subscription_created"}, "data": {}}
    payload_bytes = json.dumps(payload).encode()
    resp = await app_client.post(
        "/webhooks/lemon-squeezy",
        content=payload_bytes,
        headers={"x-signature": "badsignature", "content-type": "application/json"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Group 4: webhook_cloud subscription gate — 2 tests
# ---------------------------------------------------------------------------

def _build_wa_payload(phone_number_id: str = "3333333333") -> dict:
    """Minimal WhatsApp Cloud webhook payload with one inbound text message."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "0",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": phone_number_id},
                            "messages": [
                                {
                                    "from": "5491100000001",
                                    "id": "wamid_test_001",
                                    "type": "text",
                                    "text": {"body": "Hola, tienen Hilux?"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_gate_inactive_subscription_drops_message(
    app_client: AsyncClient,
    expired_dealership: Dealership,
    monkeypatch,
):
    """Expired subscription must cause the WA message to be silently dropped (200 ok)."""
    with (
        patch(
            "src.api.routes.webhook_cloud.get_dealership_by_wa",
            new=AsyncMock(return_value=expired_dealership),
        ),
        patch(
            "src.api.routes.webhook_cloud.process_message",
            new=AsyncMock(),
        ) as mock_process,
    ):
        payload = _build_wa_payload(phone_number_id=expired_dealership.whatsapp_phone_number_id)
        resp = await app_client.post(
            "/webhooks/whatsapp_cloud",
            json=payload,
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_gate_active_subscription_processes_message(
    app_client: AsyncClient,
    active_dealership: Dealership,
    monkeypatch,
):
    """Active subscription must allow message processing."""
    mock_result = MagicMock()
    mock_result.text = None  # no reply text, keeps test simple
    mock_result.photo_urls = []

    with (
        patch(
            "src.api.routes.webhook_cloud.get_dealership_by_wa",
            new=AsyncMock(return_value=active_dealership),
        ),
        patch(
            "src.api.routes.webhook_cloud.process_message",
            new=AsyncMock(return_value=mock_result),
        ) as mock_process,
        patch(
            "src.api.routes.webhook_cloud.check_rate_limit",
            new=AsyncMock(return_value=(True, 0)),
        ),
    ):
        payload = _build_wa_payload(phone_number_id=active_dealership.whatsapp_phone_number_id)
        resp = await app_client.post(
            "/webhooks/whatsapp_cloud",
            json=payload,
        )
    assert resp.status_code == 200
    mock_process.assert_called_once()


# ---------------------------------------------------------------------------
# Group 5: followup_task subscription gate — 1 test
# ---------------------------------------------------------------------------

def test_followup_skips_inactive_dealership(
    db_session: AsyncSession,
    expired_dealership: Dealership,
):
    """send_followups() must skip conversations for expired dealerships.

    The task uses a synchronous SQLAlchemy session (sync_engine from session.py).
    We patch _SyncSession and the WhatsApp adapter to isolate the test.
    """
    from src.tasks import followup_task

    # Build a Conversation in PRESENTING stage, last_message_at = now - 48h (followup_1 eligible)
    now = datetime.now(UTC)
    conv = Conversation(
        id=9001,
        dealership_id=expired_dealership.id,
        user_phone="5491199999001",
        mode="bot",
        last_message_at=(now - timedelta(hours=48)).replace(tzinfo=None),
        state={
            "stage": "PRESENTING",
            "followup_count": 0,
            "selected_car_title": "Toyota Hilux 2023",
            "selected_car_price": "18000000",
            "selected_car_id": 42,
        },
    )

    # Sync session mock: get_candidates returns [conv]; session.get returns expired_dealership
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value.filter.return_value.all.return_value = [conv]
    mock_session.get.return_value = expired_dealership

    # Context-manager factory (_SyncSession() returns mock_session)
    mock_session_factory = MagicMock(return_value=mock_session)

    mock_send_template = MagicMock()

    with (
        patch.object(followup_task, "_SyncSession", mock_session_factory),
        patch(
            "src.tasks.followup_task.WhatsAppCloudAdapter.send_template",
            new=mock_send_template,
        ),
    ):
        result = followup_task.send_followups()

    # Expired dealership's conversation must be skipped — send_template not called
    mock_send_template.assert_not_called()
    assert result["skipped"] >= 1
