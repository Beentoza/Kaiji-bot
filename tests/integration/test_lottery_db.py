import json
from pathlib import Path

import pytest
from database.models.Jackpot import Jackpot

from controllers.try_cmds.lottery import (
    logic as lottery_logic,
    LotteryResult,
    LotteryOutcome,
)


pytestmark = pytest.mark.integration


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ---------- fixtures ----------

@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "lottery_db.json", encoding="utf-8") as f:
        return json.load(f)


# ---------- tests ----------

@pytest.mark.parametrize("scenario_name", [
    "ban",
    "too_poor",
    "cooldown",
    "lost",
    "win_5th",
    "win_grand",
])
async def test_lottery_scenarios(db_session, seed_user, get_balance, now, try_data, mock_externals, monkeypatch, scenario_name, uow):
    scenario = try_data["lottery"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    await seed_user(
        discord_id,
        balance=setup["balance"], status=setup["status"], luck_factor=setup["luck_factor"],
        lottery=now - setup["time_since_last"],
    )
    # one Jackpot row: get_lottery_info reads it via subquery, update_lottery_and_user writes it
    db_session.add(Jackpot(id=1, money=setup["jackpot"]))
    await db_session.flush()

    if scenario["mock_randint"] is not None:
        monkeypatch.setattr(
            "controllers.try_cmds.lottery.random.randint",
            lambda *args: scenario["mock_randint"],
        )

    # === ACT ===
    result = await lottery_logic(
        interaction_user_id=discord_id,
        interaction_guild_id=999,
        unit_of_work=uow,
    )

    # === ASSERT ===
    assert isinstance(result, LotteryResult), f"[{scenario_name}] expected LotteryResult, got {result!r}"

    expected_outcome = LotteryOutcome(expected["outcome"])
    assert result.outcome == expected_outcome, (
        f"[{scenario_name}] outcome: expected {expected_outcome}, got {result.outcome}"
    )
    assert result.place == expected["place"], (
        f"[{scenario_name}] place: expected {expected['place']}, got {result.place}"
    )

    # balance in the DB after the real UnitOfWork transaction
    db_session.expire_all()
    actual_balance = await get_balance(discord_id)
    assert actual_balance == expected["balance"], (
        f"[{scenario_name}] balance: expected {expected['balance']}, got {actual_balance}"
    )
