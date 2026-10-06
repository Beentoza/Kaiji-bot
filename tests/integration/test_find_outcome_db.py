import pytest
from database.models.Bets import Bet
from database.models.models import BetStatus

pytestmark = pytest.mark.integration


async def test_find_outcome_finds_existing_bet(db_session, uow):
    bet = Bet(
        theme="test_theme",
        server_id=123,
        channel_id=456,
        message_id=789,
        status=BetStatus.CLOSED.value,
        end_timestamp=1000,
        options=["yes", "no"],
    )
    db_session.add(bet)
    await db_session.commit()


    async with uow:
        result = await uow.settlement.find_outcome("test_theme", 123)

    # === ASSERT === a pure lookup: no validation, just the row
    assert result["id"] == bet.id
    assert result["opts"] == ["yes", "no"]
    assert result["end_timestamp"] == 1000
    assert result["channel_id"] == 456
    assert result["message_id"] == 789


async def test_find_outcome_returns_none_when_missing(uow):
    async with uow:
        assert await uow.settlement.find_outcome("doesnt_exist", 123) is None
