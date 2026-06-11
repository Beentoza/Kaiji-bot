import json
from pathlib import Path

import pytest

from database.db_functions.db_outcome_logic import calculate_payouts


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
