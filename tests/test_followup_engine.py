"""Integration tests for OPT_OUT handling in the conversation engine."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Conversation, Dealership
from src.services import conversation_engine
from src.services.intent import OPT_OUT


@pytest.mark.asyncio
class TestOptOutInEngine:
    """OPT_OUT intent in process_message() sets opted_out and returns acknowledgment."""

    async def test_opt_out_sets_flag(self, db_session: AsyncSession, dealership: Dealership):
        result = await conversation_engine.process_message(
            session=db_session,
            dealership_id=dealership.id,
            phone="+5491155550099",
            text="no me interesa",
            channel="whatsapp",
        )
        assert result.intent == OPT_OUT
        assert result.state.get("opted_out") is True

    async def test_opt_out_returns_acknowledgment_es(
        self, db_session: AsyncSession, dealership: Dealership
    ):
        result = await conversation_engine.process_message(
            session=db_session,
            dealership_id=dealership.id,
            phone="+5491155550098",
            text="no gracias",
            channel="whatsapp",
        )
        assert result.intent == OPT_OUT
        assert "no te vamos a molestar" in result.text

    async def test_bare_no_opt_out(self, db_session: AsyncSession, dealership: Dealership):
        result = await conversation_engine.process_message(
            session=db_session,
            dealership_id=dealership.id,
            phone="+5491155550097",
            text="no",
            channel="whatsapp",
        )
        assert result.intent == OPT_OUT
        assert result.state.get("opted_out") is True

    async def test_opted_out_conv_returns_empty_on_next_message(
        self, db_session: AsyncSession, dealership: Dealership
    ):
        phone = "+5491155550096"

        # First: opt out
        await conversation_engine.process_message(
            session=db_session,
            dealership_id=dealership.id,
            phone=phone,
            text="no",
            channel="whatsapp",
        )
        # Flush within the transaction -- do NOT commit mid-test; the db_session fixture
        # uses a nested transaction approach and commit would break isolation (per WARNING 3 fix)
        await db_session.flush()

        # Second: send another message -- should get empty response (silently ignored)
        result2 = await conversation_engine.process_message(
            session=db_session,
            dealership_id=dealership.id,
            phone=phone,
            text="hola igual mando mensaje",
            channel="whatsapp",
        )
        assert result2.text == ""
        assert result2.state.get("opted_out") is True

    async def test_normal_message_not_opt_out(
        self, db_session: AsyncSession, dealership: Dealership
    ):
        result = await conversation_engine.process_message(
            session=db_session,
            dealership_id=dealership.id,
            phone="+5491155550095",
            text="hola, busco una hilux",
            channel="whatsapp",
        )
        assert result.intent != OPT_OUT
        assert not result.state.get("opted_out")
