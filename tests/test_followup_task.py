"""Tests for followup_task logic."""

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

# Import pure logic functions and the task at module level (per BLOCKER 6 fix --
# importing inside test functions makes assertion on MagicMock properties unreliable)
from src.tasks.followup_task import _should_followup, send_followups, FOLLOWUP_1_HOURS, FOLLOWUP_2_HOURS


def _make_conv(
    stage="PRESENTING",
    mode="bot",
    followup_count=0,
    opted_out=False,
    hours_since_last_msg=30,
    last_message_at=None,
    selected_car_id=None,
):
    """Helper: build a mock Conversation with controllable state."""
    now = datetime.now(UTC)
    if last_message_at is None:
        last_message_at = now - timedelta(hours=hours_since_last_msg)
    # SQLAlchemy typically stores naive datetimes; simulate that
    last_message_at_naive = last_message_at.replace(tzinfo=None)

    conv = MagicMock()
    conv.mode = mode
    conv.user_phone = "+5491155550001"
    conv.last_message_at = last_message_at_naive
    # Use a real dict for state so assertions on conv.state["key"] are reliable
    conv.state = {
        "stage": stage,
        "followup_count": followup_count,
        "opted_out": opted_out,
        "selected_car_id": selected_car_id,
    }
    return conv


class TestShouldFollowup:
    """_should_followup() returns correct (bool, int) for all cases."""

    def test_first_followup_after_24h(self):
        conv = _make_conv(followup_count=0, hours_since_last_msg=25)
        should, num = _should_followup(conv, datetime.now(UTC))
        assert should is True
        assert num == 1

    def test_no_followup_before_24h(self):
        conv = _make_conv(followup_count=0, hours_since_last_msg=20)
        should, num = _should_followup(conv, datetime.now(UTC))
        assert should is False
        assert num == 0

    def test_second_followup_after_72h_and_48h_gap(self):
        now = datetime.now(UTC)
        # last_followup_at was 50 hours ago (satisfies 48h minimum gap)
        last_followup_at = (now - timedelta(hours=50)).isoformat()
        conv = _make_conv(followup_count=1, hours_since_last_msg=73)
        conv.state["last_followup_at"] = last_followup_at
        should, num = _should_followup(conv, now)
        assert should is True
        assert num == 2

    def test_no_second_followup_gap_too_small(self):
        now = datetime.now(UTC)
        # last_followup_at was only 10 hours ago -- gap < 48h minimum
        last_followup_at = (now - timedelta(hours=10)).isoformat()
        conv = _make_conv(followup_count=1, hours_since_last_msg=73)
        conv.state["last_followup_at"] = last_followup_at
        should, num = _should_followup(conv, now)
        assert should is False

    def test_no_second_followup_before_72h(self):
        conv = _make_conv(followup_count=1, hours_since_last_msg=50)
        should, num = _should_followup(conv, datetime.now(UTC))
        assert should is False

    def test_max_followups_reached(self):
        conv = _make_conv(followup_count=2, hours_since_last_msg=100)
        should, num = _should_followup(conv, datetime.now(UTC))
        assert should is False
        assert num == 0

    def test_opted_out_blocked(self):
        conv = _make_conv(opted_out=True, hours_since_last_msg=30)
        should, num = _should_followup(conv, datetime.now(UTC))
        assert should is False

    def test_wrong_stage_blocked(self):
        conv = _make_conv(stage="HANDOFF", hours_since_last_msg=30)
        should, num = _should_followup(conv, datetime.now(UTC))
        assert should is False

    def test_closing_stage_blocked(self):
        conv = _make_conv(stage="CLOSING", hours_since_last_msg=30)
        should, num = _should_followup(conv, datetime.now(UTC))
        assert should is False

    def test_browsing_stage_without_selected_car_blocked(self):
        # BROWSING with no selected car produces unprofessional generic template -- skip
        conv = _make_conv(stage="BROWSING", hours_since_last_msg=25, selected_car_id=None)
        should, num = _should_followup(conv, datetime.now(UTC))
        assert should is False

    def test_browsing_stage_with_selected_car_eligible(self):
        # BROWSING with a car selected is fine to follow up
        conv = _make_conv(stage="BROWSING", hours_since_last_msg=25, selected_car_id=42)
        should, num = _should_followup(conv, datetime.now(UTC))
        assert should is True

    def test_outbound_init_stage_eligible(self):
        conv = _make_conv(stage="OUTBOUND_INIT", hours_since_last_msg=25)
        should, num = _should_followup(conv, datetime.now(UTC))
        assert should is True

    def test_manager_mode_not_checked_here(self):
        # _should_followup does not check mode -- _get_candidates filters mode=bot at DB level
        # This is fine; task architecture separates concerns
        conv = _make_conv(stage="PRESENTING", hours_since_last_msg=25)
        conv.mode = "manager"
        # _should_followup itself does not block on mode -- that's a DB-level filter
        should, num = _should_followup(conv, datetime.now(UTC))
        assert should is True  # logic correct; DB filter handles mode


class TestSendFollowupsTask:
    """send_followups task sends templates and updates state correctly."""

    def test_sends_first_followup_and_updates_state(self):
        # Use a real dict for conv.state so assertions on key values are reliable
        # (per BLOCKER 6 fix -- MagicMock property never actually asserts increments)
        initial_state = {
            "stage": "PRESENTING",
            "followup_count": 0,
            "opted_out": False,
            "selected_car_id": None,
        }

        now = datetime.now(UTC)
        last_message_at_naive = (now - timedelta(hours=25)).replace(tzinfo=None)

        conv = MagicMock()
        conv.mode = "bot"
        conv.user_phone = "+5491155550001"
        conv.last_message_at = last_message_at_naive

        # Use a list to hold the "current" state value so we can track assignments
        state_holder = [dict(initial_state)]
        captured_state = {}

        def state_getter(self_inner):
            return state_holder[0]

        def state_setter(self_inner, val):
            state_holder[0] = val
            captured_state.update(val)

        type(conv).state = property(state_getter, state_setter)

        with patch("src.tasks.followup_task._SyncSession") as mock_session_cls, \
             patch("src.tasks.followup_task.asyncio.run") as mock_asyncio_run, \
             patch("src.tasks.followup_task.settings") as mock_settings:

            mock_settings.whatsapp_cloud_token = "fake_token"
            mock_settings.whatsapp_phone_number_id = "123"
            mock_settings.database_url = "sqlite://"
            # asyncio.run() wraps the coroutine call -- return a success response
            mock_asyncio_run.return_value = {"messages": [{"id": "wamid.abc"}]}

            mock_dealer = MagicMock()
            mock_dealer.subscription_status = "active"
            mock_dealer.whatsapp_phone_number_id = "111"
            mock_dealer.whatsapp_access_token = "tok"

            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.query.return_value.filter.return_value.all.return_value = [conv]
            mock_session.get.return_value = mock_dealer
            mock_session_cls.return_value = mock_session

            result = send_followups()

        assert result["sent"] == 1
        assert result["errors"] == 0
        mock_asyncio_run.assert_called_once()
        # followup_count must have been incremented to 1
        assert captured_state.get("followup_count") == 1
        # last_followup_at must have been written
        assert "last_followup_at" in captured_state

    def test_skips_opted_out_conversation(self):
        conv = _make_conv(opted_out=True, hours_since_last_msg=30)

        with patch("src.tasks.followup_task._SyncSession") as mock_session_cls, \
             patch("src.tasks.followup_task.asyncio.run") as mock_asyncio_run, \
             patch("src.tasks.followup_task.settings") as mock_settings:

            mock_settings.whatsapp_cloud_token = "fake_token"
            mock_settings.whatsapp_phone_number_id = "123"
            mock_settings.database_url = "sqlite://"

            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.query.return_value.filter.return_value.all.return_value = [conv]
            mock_session_cls.return_value = mock_session

            result = send_followups()

        assert result["sent"] == 0
        assert result["skipped"] == 1
        mock_asyncio_run.assert_not_called()

    def test_api_error_increments_errors_not_sent(self):
        conv = _make_conv(followup_count=0, hours_since_last_msg=25)

        with patch("src.tasks.followup_task._SyncSession") as mock_session_cls, \
             patch("src.tasks.followup_task.asyncio.run") as mock_asyncio_run, \
             patch("src.tasks.followup_task.settings") as mock_settings:

            mock_settings.whatsapp_cloud_token = "fake_token"
            mock_settings.whatsapp_phone_number_id = "123"
            mock_settings.database_url = "sqlite://"
            mock_asyncio_run.return_value = {"error": "network timeout"}

            mock_dealer = MagicMock()
            mock_dealer.subscription_status = "active"
            mock_dealer.whatsapp_phone_number_id = "111"
            mock_dealer.whatsapp_access_token = "tok"

            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.query.return_value.filter.return_value.all.return_value = [conv]
            mock_session.get.return_value = mock_dealer
            mock_session_cls.return_value = mock_session

            result = send_followups()

        assert result["sent"] == 0
        assert result["errors"] == 1
