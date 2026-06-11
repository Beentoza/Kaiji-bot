import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from controllers.try_cmds.double import (
    logic as double_logic,
    DoubleResult,
    DoubleOutcome,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "double_logic.json", encoding="utf-8") as f:
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
        "get_balance_status_luckfactor": AsyncMock(),
        "add_user_balance": AsyncMock(),
        "update_winstreak": AsyncMock(),
        "add_to_jackpot": AsyncMock(),
        "log_try_event": AsyncMock(),
    }
    monkeypatch.setattr("controllers.try_cmds.double.UnitOfWork", _FakeUoW)
    monkeypatch.setattr(
        "controllers.try_cmds.double.db_economy.get_balance_status_luckfactor",
        m["get_balance_status_luckfactor"],
    )
    monkeypatch.setattr(
        "controllers.try_cmds.double.db_user.add_user_balance",
        m["add_user_balance"],
    )
    monkeypatch.setattr(
        "controllers.try_cmds.double.db_user.update_winstreak",
        m["update_winstreak"],
    )
    monkeypatch.setattr(
        "controllers.try_cmds.double.db_economy.add_to_jackpot",
        m["add_to_jackpot"],
    )
    monkeypatch.setattr(
        "controllers.try_cmds.double.db_logs.log_try_event",
        m["log_try_event"],
    )
    return m


@pytest.mark.parametrize("scenario_name", [
    "ban",
    "ban_overrides_other",
    "amount_negative",
    "amount_zero",
    "amount_19",
    "exceeds_zero_bal",
    "exceeds_neg_bal",
    "exceeds_26",
    "exceeds_by_one",
    "edge_balance_27_passes",
    "edge_75pct_passes",
    "edge_status_2",
    "win_lf_0",
    "win_lf_0_5_max_bet",
    "win_lf_2_any_seed",
    "lose_lf_0",
    "lose_lf_0_5",
    "lose_lf_0_8",
    "draw_bug_lf_0",
    "draw_bug_lf_1",
])
async def test_double_logic(try_data, mocks, monkeypatch, scenario_name):
    scenario = try_data["scenarios"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    mocks["get_balance_status_luckfactor"].return_value = (
        setup["balance"], setup["status"], setup["luck_factor"],
    )

    if scenario["mock_random"] is not None:
        monkeypatch.setattr(
            "controllers.try_cmds.double.random.randint",
            lambda *args: scenario["mock_random"],
        )

    # === ACT ===
    result = await double_logic(
        interaction_user_id=discord_id,
        interaction_guild_id=999,
        amount=scenario["amount"],
    )

    # === ASSERT === outcome (banned/too_low/won/...) taken straight from the scenario,
    # plus the money movement
    assert isinstance(result, DoubleResult), f"[{scenario_name}] expected DoubleResult, got {result!r}"

    expected_outcome = DoubleOutcome(expected["outcome"])
    assert result.outcome == expected_outcome, (
        f"[{scenario_name}] outcome: expected {expected_outcome}, got {result.outcome}"
    )

    delta = expected["balance"] - setup["balance"]
    if delta == 0:
        # ban / validation / draw -> balance doesn't move
        mocks["add_user_balance"].assert_not_called()
    else:
        mocks["add_user_balance"].assert_awaited_once()
        assert mocks["add_user_balance"].await_args.kwargs["amount"] == delta, (
            f"[{scenario_name}] delta: expected {delta}, "
            f"got {mocks['add_user_balance'].await_args.kwargs.get('amount')!r}"
        )
        assert result.delta == delta
