import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from controllers.try_cmds.double import random
from database.db_functions.db_user import UserRepository
from controllers.try_cmds import double
from controllers.try_cmds.double import (
    logic as double_logic,
    DoubleResult,
    DoubleOutcome,
)


pytestmark = pytest.mark.integration


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
logic_SCENARIOS = json.loads((FIXTURES_DIR / "double_db.json").read_text(encoding="utf-8"))["double"]
rollback_SCENARIOS = json.loads((FIXTURES_DIR / "double_db.json").read_text(encoding="utf-8"))["rollback"]

# ---------- fixtures ----------

@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "double_db.json", encoding="utf-8") as f:
        return json.load(f)



# ---------- helpers ----------

def _patch_roll(monkeypatch, outcome: str, luck_factor: float) -> None:
    """Arranges the roll that produces the scenario's outcome under the CURRENT constants.

    The scenario states the outcome, never the number - retuning LOWEST/HIGHEST/
    DOUBLE_CHANCE_TO_WIN can't silently turn a winning roll into a losing one.
    """
    low, high = double._roll_bounds(luck_factor)
    roll = {"won": low, "lost": high, "draw": double.win_threshold()}.get(outcome)
    if roll is None:          # banned / validation - the code never rolls
        return
    monkeypatch.setattr(random, "randint", lambda *_: roll)


# ---------- tests ----------

@pytest.mark.parametrize("scenario_name", logic_SCENARIOS)
async def test_double_scenarios(db_session, seed_user, get_balance, try_data, monkeypatch, scenario_name, uow):
    scenario = try_data["double"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    await seed_user(
        discord_id,
        balance=setup["balance"], status=setup["status"], luck_factor=setup["luck_factor"],
    )

    _patch_roll(monkeypatch, expected["outcome"], setup["luck_factor"])

    # === ACT ===
    result = await double_logic(
        interaction_user_id=discord_id,
        interaction_guild_id=999,
        amount=scenario["amount"],
        unit_of_work=uow
    )

    # === ASSERT ===
    assert isinstance(result, DoubleResult), f"[{scenario_name}] expected DoubleResult, got {result!r}"

    expected_outcome = DoubleOutcome(expected["outcome"])
    assert result.outcome == expected_outcome, (
        f"[{scenario_name}] outcome: expected {expected_outcome}, got {result.outcome}"
    )

    # balance in the DB after the real UnitOfWork transaction
    db_session.expire_all()
    actual_balance = await get_balance(discord_id)
    assert actual_balance == expected["balance"], (
        f"[{scenario_name}] balance: expected {expected['balance']}, got {actual_balance}"
    )
async def boom(*args, **kwargs):
    raise RuntimeError("boom")

@pytest.mark.parametrize("scenario_name", rollback_SCENARIOS)
async def test_double_rollback_scenarios(db_session, seed_user, get_balance, try_data, monkeypatch, scenario_name, uow):
    scenario = try_data["rollback"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    await seed_user(
        discord_id,
        balance=setup["balance"], status=setup["status"], luck_factor=setup["luck_factor"],
    )

    _patch_roll(monkeypatch, setup["roll"], setup["luck_factor"])
    monkeypatch.setattr(UserRepository, "update_winstreak", boom)

    result = await double_logic(
        interaction_user_id=discord_id,
        interaction_guild_id=999,
        amount=scenario["amount"],
        unit_of_work=uow
    )


    expected_outcome = DoubleOutcome(expected["outcome"])
    assert result.outcome == expected_outcome, (
        f"[{scenario_name}] outcome: expected {expected_outcome}, got {result.outcome}"
    )


    db_session.expire_all()
    actual_balance = await get_balance(discord_id)
    assert actual_balance == expected["balance"], (
        f"[{scenario_name}] balance: expected {expected['balance']}, got {actual_balance}"
    )

