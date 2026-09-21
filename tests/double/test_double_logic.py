import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import constants
from controllers.try_cmds import double
from controllers.try_cmds.double import (
    logic as double_logic,
    DoubleResult,
    DoubleOutcome,
)


pytestmark = pytest.mark.unit


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


def _patch_roll(monkeypatch, outcome: str, luck_factor: float) -> None:
    """Arranges the roll that produces the scenario's outcome under the CURRENT constants.

    The scenario states the outcome, never the number - retuning LOWEST/HIGHEST/
    DOUBLE_CHANCE_TO_WIN can't silently turn a winning roll into a losing one.
    """
    low, high = double._roll_bounds(luck_factor)
    roll = {"won": low, "lost": high, "draw": double.win_threshold()}.get(outcome)
    if roll is None:          # banned / validation - the code never rolls
        return
    monkeypatch.setattr("controllers.try_cmds.double.random.randint", lambda *_: roll)


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

    _patch_roll(monkeypatch, expected["outcome"], setup["luck_factor"])

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


# ---------- the rule itself, on constants chosen here ----------
# The scenarios above ask the production code which roll wins, so they can't catch a
# flipped comparison. These can: the numbers below are fixed by this file, not by config.

@pytest.fixture
def toy_constants(monkeypatch):
    # small enough to read by eye: threshold = 0 + (10-0)*0.4 = 4
    monkeypatch.setattr(constants, "LOWEST_DOUBLE_PROB", 0)
    monkeypatch.setattr(constants, "HIGHEST_DOUBLE_PROB", 10)
    monkeypatch.setattr(constants, "DOUBLE_CHANCE_TO_WIN", 40)


@pytest.mark.parametrize("roll, expected", [
    (0, (95, True)),        # bottom of the range wins
    (3, (95, True)),        # last winning roll
    (4, (None, None)),      # exactly on the threshold -> draw
    (5, (-100, False)),     # first losing roll
    (10, (-100, False)),    # top of the range loses
])
def test_outcome_rule(toy_constants, roll, expected):
    assert double._resolve_double_outcome(roll, amount=100) == expected


def _winrate(luck_factor: float) -> float:
    """Exact win share over every roll the range can produce - no sampling, no flakiness."""
    low, high = double._roll_bounds(luck_factor)
    rolls = range(low, high + 1)
    wins = sum(1 for roll in rolls if double._resolve_double_outcome(roll, amount=100)[1])
    return wins / len(rolls)


def test_base_winrate_matches_the_constant():
    # off by ~0.04%: the range is inclusive on both ends, so it holds one roll more
    # than the span the percentage is computed from
    assert _winrate(0.0) == pytest.approx(constants.DOUBLE_CHANCE_TO_WIN / 100, abs=0.01)


def test_luck_factor_helps():
    rates = [_winrate(lf) for lf in (0.0, 0.5, 1.0, 2.0)]
    assert rates == sorted(rates), f"luck_factor must never lower the win rate: {rates}"
    assert rates[-1] > rates[0], f"luck_factor must actually change something: {rates}"
