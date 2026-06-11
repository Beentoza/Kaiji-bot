import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from controllers.try_cmds.market import (
    logic as market_logic,
    MarketResult,
    MarketOutcome,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Fixed "now"; the test seeds market_timestamp = NOW - time_since_last.
NOW = 10_000_000


@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "market_logic.json", encoding="utf-8") as f:
        return json.load(f)


class _FakeUoW:
    def __init__(self):
        self.session = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


@pytest.fixture
def mocks(monkeypatch):
    m = {
        "get_timestamp_balance_status": AsyncMock(),
        "set_market_time": AsyncMock(),
        "log_try_event": AsyncMock(),
        "add_user_balance": AsyncMock(),
        "add_to_jackpot": AsyncMock(),
        "add_balance_history": AsyncMock(),
    }
    monkeypatch.setattr("controllers.try_cmds.market.UnitOfWork", _FakeUoW)
    monkeypatch.setattr("controllers.try_cmds.market.get_timestamp", lambda: NOW)
    monkeypatch.setattr(
        "controllers.try_cmds.market.db_economy.get_timestamp_balance_status",
        m["get_timestamp_balance_status"],
    )
    monkeypatch.setattr("controllers.try_cmds.market.db_time.set_market_time", m["set_market_time"])
    monkeypatch.setattr("controllers.try_cmds.market.db_logs.log_try_event", m["log_try_event"])
    monkeypatch.setattr("controllers.try_cmds.market.db_user.add_user_balance", m["add_user_balance"])
    monkeypatch.setattr("controllers.try_cmds.market.db_economy.add_to_jackpot", m["add_to_jackpot"])
    monkeypatch.setattr(
        "controllers.try_cmds.market.timed_tasks.add_balance_history", m["add_balance_history"]
    )
    return m


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
async def test_market_logic(try_data, mocks, monkeypatch, scenario_name):
    scenario = try_data["scenarios"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    market_timestamp = NOW - setup["time_since_last"]
    mocks["get_timestamp_balance_status"].return_value = (
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
        mocks["add_user_balance"].assert_not_called()
    else:
        mocks["add_user_balance"].assert_awaited_once()
        assert mocks["add_user_balance"].await_args.kwargs["amount"] == delta, (
            f"[{scenario_name}] delta: expected {delta}, "
            f"got {mocks['add_user_balance'].await_args.kwargs.get('amount')!r}"
        )
        assert result.delta == delta
