import json
from pathlib import Path

import pytest

from controllers.try_cmds.market import (
    logic as market_logic,
    MarketResult,
    MarketOutcome,
)


pytestmark = pytest.mark.integration


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ---------- fixtures ----------

@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "market_db.json", encoding="utf-8") as f:
        return json.load(f)


# ---------- tests ----------

@pytest.mark.parametrize("scenario_name", [
    "ban",
    "insufficient",
    "cooldown",
    "same_balance",
    "win",
    "lose",
    "all_in_win",
])
async def test_market_scenarios(db_session, seed_user, get_balance, now, try_data, mock_externals, monkeypatch, scenario_name, uow):
    scenario = try_data["market"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    await seed_user(
        discord_id,
        balance=setup["balance"], status=setup["status"], luck_factor=setup["luck_factor"],
        market=now - setup["time_since_last"],
    )

    if scenario["multiplier"] is not None:
        monkeypatch.setattr(
            "controllers.try_cmds.market._random_multiplier",
            lambda luck_factor: scenario["multiplier"],
        )

    # === ACT ===
    result = await market_logic(
        interaction_user_id=discord_id,
        interaction_guild_id=999,
        unit_of_work=uow,
        amount=scenario["amount"],
    )

    # === ASSERT ===
    assert isinstance(result, MarketResult), f"[{scenario_name}] expected MarketResult, got {result!r}"

    expected_outcome = MarketOutcome(expected["outcome"])
    assert result.outcome == expected_outcome, (
        f"[{scenario_name}] outcome: expected {expected_outcome}, got {result.outcome}"
    )

    # balance in the DB after the real UnitOfWork transaction
    db_session.expire_all()
    actual_balance = await get_balance(discord_id)
    assert actual_balance == expected["balance"], (
        f"[{scenario_name}] balance: expected {expected['balance']}, got {actual_balance}"
    )
