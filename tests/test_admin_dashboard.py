"""Unit tests for admin dashboard query logic (07-01).

Tests validate the query/computation logic used by dashboard() and metrics_page()
directly — without calling route functions — to avoid mocking Request, auth, and templates.
"""

import pytest
from datetime import UTC, datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Conversation, Lead, Message,
    LeadIntentEnum, LeadStatusEnum, MessageDirectionEnum,
)


# ---------------------------------------------------------------------------
# Task 1 tests: pending_visits and active_conversations query logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pending_visits_counts_visit_new(db_session: AsyncSession, dealership):
    """Only Lead(intent=visit, status=new) counts; info-intent and handed_off do not."""
    db_session.add(Lead(
        dealership_id=1, phone="+1111111111",
        intent=LeadIntentEnum.visit, status=LeadStatusEnum.new,
    ))
    db_session.add(Lead(
        dealership_id=1, phone="+2222222222",
        intent=LeadIntentEnum.info, status=LeadStatusEnum.new,
    ))
    db_session.add(Lead(
        dealership_id=1, phone="+3333333333",
        intent=LeadIntentEnum.visit, status=LeadStatusEnum.handed_off,
    ))
    await db_session.flush()

    r = await db_session.execute(
        select(func.count(Lead.id)).where(
            Lead.dealership_id == 1,
            Lead.intent == LeadIntentEnum.visit,
            Lead.status.in_([LeadStatusEnum.new, LeadStatusEnum.qualified]),
        )
    )
    count = r.scalar() or 0
    assert count == 1


@pytest.mark.asyncio
async def test_pending_visits_counts_visit_qualified(db_session: AsyncSession, dealership):
    """Lead(intent=visit, status=qualified) is counted."""
    db_session.add(Lead(
        dealership_id=1, phone="+4444444444",
        intent=LeadIntentEnum.visit, status=LeadStatusEnum.qualified,
    ))
    await db_session.flush()

    r = await db_session.execute(
        select(func.count(Lead.id)).where(
            Lead.dealership_id == 1,
            Lead.intent == LeadIntentEnum.visit,
            Lead.status.in_([LeadStatusEnum.new, LeadStatusEnum.qualified]),
        )
    )
    count = r.scalar() or 0
    assert count == 1


@pytest.mark.asyncio
async def test_active_conversations_bot_mode_7days(db_session: AsyncSession, dealership):
    """Only mode='bot' conversations within the last 7 days are counted."""
    three_days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=3)
    ten_days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=10)
    seven_days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=7)

    # Should be counted
    db_session.add(Conversation(
        dealership_id=1, user_phone="+1000000001",
        mode="bot", last_message_at=three_days_ago,
    ))
    # mode=manager — not counted
    db_session.add(Conversation(
        dealership_id=1, user_phone="+1000000002",
        mode="manager", last_message_at=three_days_ago,
    ))
    # bot but older than 7 days — not counted
    db_session.add(Conversation(
        dealership_id=1, user_phone="+1000000003",
        mode="bot", last_message_at=ten_days_ago,
    ))
    await db_session.flush()

    r = await db_session.execute(
        select(func.count(Conversation.id)).where(
            Conversation.dealership_id == 1,
            Conversation.mode == "bot",
            Conversation.last_message_at >= seven_days_ago,
        )
    )
    count = r.scalar() or 0
    assert count == 1


@pytest.mark.asyncio
async def test_active_conversations_excludes_other_dealership(
    db_session: AsyncSession, dealership, dealership2
):
    """Conversations belonging to dealership_id=2 are not counted when querying did=1."""
    three_days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=3)
    seven_days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=7)

    db_session.add(Conversation(
        dealership_id=2, user_phone="+9000000001",
        mode="bot", last_message_at=three_days_ago,
    ))
    await db_session.flush()

    r = await db_session.execute(
        select(func.count(Conversation.id)).where(
            Conversation.dealership_id == 1,
            Conversation.mode == "bot",
            Conversation.last_message_at >= seven_days_ago,
        )
    )
    count = r.scalar() or 0
    assert count == 0


# ---------------------------------------------------------------------------
# Task 3 tests: avg_response_str computation logic
# ---------------------------------------------------------------------------

from collections import defaultdict


async def _compute_avg_response(db: AsyncSession, did: int) -> str:
    """Mirror of the avg_response_str computation block in metrics_page().

    Uses naive datetimes for SQLite compatibility (same as test rows).
    """
    thirty_days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)

    r = await db.execute(
        select(Conversation.id).where(Conversation.dealership_id == did)
    )
    conv_ids = [row[0] for row in r.all()]
    avg_response_str = "\u2014"
    if conv_ids:
        r = await db.execute(
            select(Message.conversation_id, Message.direction, Message.created_at)
            .where(
                Message.conversation_id.in_(conv_ids),
                Message.created_at >= thirty_days_ago,
            )
            .order_by(Message.conversation_id, Message.created_at)
        )
        rows = r.all()
        by_conv: dict = defaultdict(list)
        for conv_id, direction, created_at in rows:
            by_conv[conv_id].append((direction, created_at))
        deltas: list = []
        for msgs in by_conv.values():
            i = 0
            while i < len(msgs):
                if msgs[i][0] == MessageDirectionEnum.inbound:
                    j = i + 1
                    while j < len(msgs) and msgs[j][0] != MessageDirectionEnum.outbound:
                        j += 1
                    if j < len(msgs):
                        delta = (msgs[j][1] - msgs[i][1]).total_seconds()
                        if delta >= 0:
                            deltas.append(delta)
                    i = j + 1
                else:
                    i += 1
        if deltas:
            avg_secs = sum(deltas) / len(deltas)
            if avg_secs < 60:
                avg_response_str = f"{int(avg_secs)}s"
            else:
                mins = int(avg_secs // 60)
                secs = int(avg_secs % 60)
                avg_response_str = f"{mins}m {secs}s"
    return avg_response_str


@pytest.mark.asyncio
async def test_avg_response_str_basic_seconds(db_session: AsyncSession, dealership):
    """One inbound at T0, one outbound at T0+30s → avg_response_str == '30s'."""
    now = datetime.now(UTC).replace(tzinfo=None)
    conv = Conversation(dealership_id=1, user_phone="+5000000001", mode="bot", last_message_at=now)
    db_session.add(conv)
    await db_session.flush()

    db_session.add(Message(
        conversation_id=conv.id,
        direction=MessageDirectionEnum.inbound,
        created_at=now,
        text="hi",
    ))
    db_session.add(Message(
        conversation_id=conv.id,
        direction=MessageDirectionEnum.outbound,
        created_at=now + timedelta(seconds=30),
        text="hello",
    ))
    await db_session.flush()

    result = await _compute_avg_response(db_session, 1)
    assert result == "30s"


@pytest.mark.asyncio
async def test_avg_response_str_minutes(db_session: AsyncSession, dealership):
    """One inbound at T0, one outbound at T0+90s → avg_response_str == '1m 30s'."""
    now = datetime.now(UTC).replace(tzinfo=None)
    conv = Conversation(dealership_id=1, user_phone="+5000000002", mode="bot", last_message_at=now)
    db_session.add(conv)
    await db_session.flush()

    db_session.add(Message(
        conversation_id=conv.id,
        direction=MessageDirectionEnum.inbound,
        created_at=now,
        text="hi",
    ))
    db_session.add(Message(
        conversation_id=conv.id,
        direction=MessageDirectionEnum.outbound,
        created_at=now + timedelta(seconds=90),
        text="hello",
    ))
    await db_session.flush()

    result = await _compute_avg_response(db_session, 1)
    assert result == "1m 30s"


@pytest.mark.asyncio
async def test_avg_response_str_no_data(db_session: AsyncSession, dealership):
    """No messages for dealership → avg_response_str == '—'."""
    result = await _compute_avg_response(db_session, 1)
    assert result == "\u2014"


@pytest.mark.asyncio
async def test_avg_response_str_old_messages_excluded(db_session: AsyncSession, dealership):
    """Message pair older than 30 days → not included → result == '—'."""
    old_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=31)
    conv = Conversation(dealership_id=1, user_phone="+5000000003", mode="bot", last_message_at=old_time)
    db_session.add(conv)
    await db_session.flush()

    db_session.add(Message(
        conversation_id=conv.id,
        direction=MessageDirectionEnum.inbound,
        created_at=old_time,
        text="hi",
    ))
    db_session.add(Message(
        conversation_id=conv.id,
        direction=MessageDirectionEnum.outbound,
        created_at=old_time + timedelta(seconds=30),
        text="hello",
    ))
    await db_session.flush()

    result = await _compute_avg_response(db_session, 1)
    assert result == "\u2014"
