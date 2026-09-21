import json
from pathlib import Path

import pytest

from database.db_functions.db_outcome_logic import calculate_payouts, validate_outcome
from helpers.BetTypes import BetEndType


pytestmark = pytest.mark.unit


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "outcome_logic.json", encoding="utf-8") as f:
        return json.load(f)


def _normalize_outcome(expected_outcome):
    return {
        opt: {int(uid): amt for uid, amt in users.items()}
        for opt, users in expected_outcome.items()
    }


@pytest.mark.parametrize("scenario_name", [
    "payout_even",
    "payout_uneven",
    "payout_three_options",
    "refund_single_option",
    "refund_no_bets_on_winner",
    "refund_no_participants",
])
def test_calculate_payouts(try_data, scenario_name):
    scenario = try_data["scenarios"][scenario_name]
    expected = scenario["expected"]

    result = calculate_payouts(scenario["rows"], scenario["opts"], scenario["choice"])

    assert result["action"] == expected["action"], (
        f"[{scenario_name}] action: expected {expected['action']}, got {result['action']}"
    )
    assert result["outcome"] == _normalize_outcome(expected["outcome"]), (
        f"[{scenario_name}] outcome mismatch"
    )

    if expected["action"] == "payout":
        assert result["koef"] == pytest.approx(expected["koef"]), (
            f"[{scenario_name}] koef: expected {expected['koef']}, got {result['koef']}"
        )
    else:
        assert "koef" not in result, f"[{scenario_name}] refund must not carry koef"


# validate_outcome is a plain function now, so the settle rules are checked
# without a database -- same as calculate_payouts above.
def _outcome_info(end_timestamp=1000, opts=("yes", "no")):
    return {
        "id": 1,
        "opts": list(opts),
        "end_timestamp": end_timestamp,
        "channel_id": 456,
        "message_id": 789,
    }


def test_validate_outcome_accepts_closed_bet():
    result, status = validate_outcome(_outcome_info(), current_time=2000, choice="yes")

    assert status is BetEndType.SUCCESS
    assert result["win_index"] == 0


def test_validate_outcome_win_index_of_first_option_is_zero():
    # 0 is falsy: guarding on the index instead of the status would break here
    result, _ = validate_outcome(_outcome_info(), current_time=2000, choice="yes")
    assert result["win_index"] == 0


def test_validate_outcome_rejects_missing_bet():
    assert validate_outcome(None, current_time=2000, choice="yes") == (None, BetEndType.BET_NOT_FOUND)


def test_validate_outcome_rejects_bet_that_is_still_open():
    result, status = validate_outcome(_outcome_info(end_timestamp=3000), current_time=2000, choice="yes")

    assert result is None
    assert status is BetEndType.OPEN_BET


def test_validate_outcome_rejects_unknown_option():
    result, status = validate_outcome(_outcome_info(), current_time=2000, choice="maybe")

    assert result is None
    assert status is BetEndType.NOT_OPTION
