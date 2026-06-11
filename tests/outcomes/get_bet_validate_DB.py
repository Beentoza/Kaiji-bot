from database.models.Bets import Bet
from database.models.models import BetStatus
from database.db_functions.db_outcome_logic import get_bet_and_validate


async def test_get_bet_and_validate_finds_existing_bet(db_session):
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

    # === ACT === current_time > end_timestamp, so the bet is past due
    result, status = await get_bet_and_validate(
        session=db_session,
        bet_theme="test_theme",
        current_time=2000,
        choice="yes",
        server_id=123,
        time_check=True,
    )

    # === ASSERT ===
    assert status == "ok"
    assert result["id"] == bet.id
    assert result["win_index"] == 0


async def test_get_bet_and_validate_returns_not_found(db_session):
    result, status = await get_bet_and_validate(
        session=db_session,
        bet_theme="doesnt_exist",
        current_time=2000,
        choice="yes",
        server_id=123,
        time_check=True,
    )
    assert result is None
    assert status == "bet_not_found"
