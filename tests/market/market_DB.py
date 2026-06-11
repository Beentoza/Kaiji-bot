import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from database.models.Users import User
from database.models.Balances import Balance
from database.models.Statuses import Status
from database.models.UserData import UserData
from database.models.Timestamps import Timestamp

from controllers.try_cmds.market import (
    logic as market_logic,
    MarketResult,
    MarketOutcome,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

NOW = 10_000_000


# ---------- fixtures ----------

@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "market_db.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_externals(monkeypatch):
    # log_try_event writes Events, add_balance_history writes a shared buffer: stub both
    monkeypatch.setattr("controllers.try_cmds.market.get_timestamp", lambda: NOW)
    monkeypatch.setattr("controllers.try_cmds.market.db_logs.log_try_event", AsyncMock())
    monkeypatch.setattr("controllers.try_cmds.market.timed_tasks.add_balance_history", AsyncMock())


# ---------- helpers ----------

async def _seed_user(session, discord_id, balance, status, luck_factor, market_timestamp):
    new_user = User(discord_id=discord_id)
    session.add(new_user)
    await session.flush()

    session.add_all([
        Balance(id=new_user.id, balance=balance),
        Status(id=new_user.id, status=int(status)),
        UserData(id=new_user.id, double_curr_row=0, double_max_row=0, luck_factor=luck_factor),
        Timestamp(id=new_user.id, market=market_timestamp),
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
    "ban",
    "insufficient",
    "cooldown",
    "same_balance",
    "win",
    "lose",
    "all_in_win",
])
async def test_market_scenarios(db_session, try_data, mock_externals, monkeypatch, scenario_name):
    scenario = try_data["market"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    await _seed_user(
        db_session, discord_id,
        balance=setup["balance"], status=setup["status"], luck_factor=setup["luck_factor"],
        market_timestamp=NOW - setup["time_since_last"],
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

    # balance in the DB after the real UnitOfWork transaction
    db_session.expire_all()
    actual_balance = await _get_balance(db_session, discord_id)
    assert actual_balance == expected["balance"], (
        f"[{scenario_name}] balance: expected {expected['balance']}, got {actual_balance}"
    )
