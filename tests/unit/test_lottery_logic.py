import json
from pathlib import Path
import pytest

from controllers.try_cmds.lottery import (
    logic as lottery_logic,
    LotteryResult,
    LotteryOutcome,
)

pytestmark = pytest.mark.unit

@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "lottery_logic.json", encoding="utf-8") as f:
        return json.load(f)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# Fixed "now"; the test seeds lottery_timestamp = NOW - time_since_last.
NOW = 10_000_000





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
async def test_lottery_logic(try_data, monkeypatch, scenario_name, fake_uow):
    scenario = try_data["scenarios"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    monkeypatch.setattr(
        "controllers.try_cmds.lottery.get_timestamp",

        lambda: NOW
    )

    lottery_timestamp = NOW - setup["time_since_last"]
    fake_uow.economy.get_lottery_info.return_value = (
        lottery_timestamp, setup["balance"], setup["status"], setup["jackpot"], setup["luck_factor"],
    )
    # place 1 reads the jackpot under lock via take_jackpot, not from the snapshot above
    fake_uow.economy.take_jackpot.return_value = setup["jackpot"]

    if scenario["mock_randint"] is not None:
        monkeypatch.setattr(
            "controllers.try_cmds.lottery.random.randint",
            lambda *args: scenario["mock_randint"],
        )

    # === ACT ===
    result = await lottery_logic(
        interaction_user_id=discord_id,
        interaction_guild_id=999,
        unit_of_work=fake_uow
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
        fake_uow.economy.update_lottery_and_user.assert_not_called()
    else:
        fake_uow.economy.update_lottery_and_user.assert_awaited_once()
        assert fake_uow.economy.update_lottery_and_user.await_args.kwargs["user_money_change"] == profit, (
            f"[{scenario_name}] profit: expected {profit}, "
            f"got {fake_uow.economy.update_lottery_and_user.await_args.kwargs.get('user_money_change')!r}"
        )
        assert result.profit == profit
