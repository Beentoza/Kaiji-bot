import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from database.models.Users import User
from database.models.Balances import Balance
from database.models.Statuses import Status
from database.models.UserData import UserData

from controllers.try_cmds.double import (
    logic as double_logic,
    DoubleResult,
    DoubleOutcome,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ---------- fixtures ----------

@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "double_db.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_log_try_event(monkeypatch):
    # log_try_event writes Events: stub it out
    mock = AsyncMock()
    monkeypatch.setattr("controllers.try_cmds.double.db_logs.log_try_event", mock)
    return mock


# ---------- helpers ----------

async def _seed_user(session, discord_id: int, balance: int, status: int, luck_factor: float):
    new_user = User(discord_id=discord_id)
    session.add(new_user)
    await session.flush()

    session.add_all([
        Balance(id=new_user.id, balance=balance),
        Status(id=new_user.id, status=int(status)),
        UserData(id=new_user.id, double_curr_row=0, double_max_row=0, luck_factor=luck_factor),
    ])
    await session.flush()


async def _get_balance(db_session, discord_id: int) -> int:
    stmt = (
        select(Balance.balance)
        .join(User, User.id == Balance.id)
        .where(User.discord_id == discord_id)
    )
    res = await db_session.execute(stmt)
    return res.scalar_one()


# ---------- tests ----------

@pytest.mark.parametrize("scenario_name", [
    "edge_75pct_passes"
])
async def test_double_scenarios(
    db_session, try_data, mock_log_try_event, monkeypatch, scenario_name,
):
    scenario = try_data["double"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    await _seed_user(
        db_session, discord_id,
        balance=setup["balance"], status=setup["status"], luck_factor=setup["luck_factor"],
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

    # === ASSERT ===
    assert isinstance(result, DoubleResult), f"[{scenario_name}] expected DoubleResult, got {result!r}"

    expected_outcome = DoubleOutcome(expected["outcome"])
    assert result.outcome == expected_outcome, (
        f"[{scenario_name}] outcome: expected {expected_outcome}, got {result.outcome}"
    )

    # balance in the DB after the real UnitOfWork transaction
    db_session.expire_all()
    actual_balance = await _get_balance(db_session, discord_id)
    assert actual_balance == expected["balance"], (
        f"[{scenario_name}] balance: expected {expected['balance']}, got {actual_balance}"
    )
