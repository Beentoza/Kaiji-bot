import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from controllers.try_cmds.lottery import (
    logic as lottery_logic,
    LotteryResult,
    LotteryOutcome,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Fixed "now"; the test seeds lottery_timestamp = NOW - time_since_last.
NOW = 10_000_000


@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "lottery_logic.json", encoding="utf-8") as f:
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
        "get_lottery_info": AsyncMock(),
        "log_try_event": AsyncMock(),
        "update_lottery_and_user": AsyncMock(),
        "add_balance_history": AsyncMock(),
    }
    monkeypatch.setattr("controllers.try_cmds.lottery.UnitOfWork", _FakeUoW)
    monkeypatch.setattr("controllers.try_cmds.lottery.get_timestamp", lambda: NOW)
    monkeypatch.setattr("controllers.try_cmds.lottery.db_economy.get_lottery_info", m["get_lottery_info"])
    monkeypatch.setattr("controllers.try_cmds.lottery.db_logs.log_try_event", m["log_try_event"])
    monkeypatch.setattr(
        "controllers.try_cmds.lottery.db_economy.update_lottery_and_user", m["update_lottery_and_user"]
    )
    monkeypatch.setattr(
        "controllers.try_cmds.lottery.timed_tasks.add_balance_history", m["add_balance_history"]
    )
    return m


@pytest.mark.parametrize("scenario_name", [
    "ban",
    "too_poor",
    "cooldown",
    "lost",
    "win_5th",
    "win_4th",
    "win_3rd",
    "win_2nd",
    "win_grand",
])
async def test_lottery_logic(try_data, mocks, monkeypatch, scenario_name):
    scenario = try_data["scenarios"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    lottery_timestamp = NOW - setup["time_since_last"]
    mocks["get_lottery_info"].return_value = (
        lottery_timestamp, setup["balance"], setup["status"], setup["jackpot"], setup["luck_factor"],
    )

    if scenario["mock_randint"] is not None:
        monkeypatch.setattr(
            "controllers.try_cmds.lottery.random.randint",
            lambda *args: scenario["mock_randint"],
        )

    # === ACT ===
    result = await lottery_logic(
        interaction_user_id=discord_id,
        interaction_guild_id=999,
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

    # money moves through update_lottery_and_user(user_money_change=profit)
    profit = expected["balance"] - setup["balance"]
    if profit == 0:
        mocks["update_lottery_and_user"].assert_not_called()
    else:
        mocks["update_lottery_and_user"].assert_awaited_once()
        assert mocks["update_lottery_and_user"].await_args.kwargs["user_money_change"] == profit, (
            f"[{scenario_name}] profit: expected {profit}, "
            f"got {mocks['update_lottery_and_user'].await_args.kwargs.get('user_money_change')!r}"
        )
        assert result.profit == profit
