import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from controllers.try_cmds.market import (
    logic as market_logic,
    MarketResult,
    MarketOutcome,
)


pytestmark = pytest.mark.unit


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Fixed "now"; the test seeds market_timestamp = NOW - time_since_last.
NOW = 10_000_000


@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "market_logic.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("scenario_name", [
    "ban",
    "amount_negative",
    "too_low_49",
    "insufficient",
    "cooldown",
    "same_balance",
    "win",
    "win_status_2",
    "win_small_no_jp",
    "lose",
    "all_in_win",
])
async def test_market_logic(try_data, monkeypatch, scenario_name, fake_uow):
    scenario = try_data["scenarios"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    monkeypatch.setattr("controllers.try_cmds.market.get_timestamp", lambda: NOW)
    # called after the uow block, not through it -> still patched on the module
    monkeypatch.setattr("controllers.try_cmds.market.timed_tasks.add_balance_history", AsyncMock())

    market_timestamp = NOW - setup["time_since_last"]
    fake_uow.economy.get_timestamp_balance_status.return_value = (
        market_timestamp, setup["balance"], setup["status"], setup["luck_factor"],
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
        amount=scenario["amount"],
        unit_of_work=fake_uow,
    )

    # === ASSERT ===
    assert isinstance(result, MarketResult), f"[{scenario_name}] expected MarketResult, got {result!r}"

    expected_outcome = MarketOutcome(expected["outcome"])
    assert result.outcome == expected_outcome, (
        f"[{scenario_name}] outcome: expected {expected_outcome}, got {result.outcome}"
    )

    # money moves through add_user_balance(amount=delta)
    delta = expected["balance"] - setup["balance"]
    if delta == 0:
        fake_uow.user.add_user_balance.assert_not_called()
    else:
        fake_uow.user.add_user_balance.assert_awaited_once()
        assert fake_uow.user.add_user_balance.await_args.kwargs["amount"] == delta, (
            f"[{scenario_name}] delta: expected {delta}, "
            f"got {fake_uow.user.add_user_balance.await_args.kwargs.get('amount')!r}"
        )
        assert result.delta == delta
