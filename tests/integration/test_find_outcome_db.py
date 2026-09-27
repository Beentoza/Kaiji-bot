import pytest

from database.models.Bets import Bet
from database.models.models import BetStatus
from database.db_functions.db_outcome_logic import find_outcome


pytestmark = pytest.mark.integration


async def test_find_outcome_finds_existing_bet(db_session):
    # === ARRANGE ===
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

    # === ACT ===
    result = await find_outcome(db_session, "test_theme", 123)

    # === ASSERT === a pure lookup: no validation, just the row
    assert result["id"] == bet.id
    assert result["opts"] == ["yes", "no"]
    assert result["end_timestamp"] == 1000
    assert result["channel_id"] == 456
    assert result["message_id"] == 789


async def test_find_outcome_returns_none_when_missing(db_session):
    assert await find_outcome(db_session, "doesnt_exist", 123) is None
