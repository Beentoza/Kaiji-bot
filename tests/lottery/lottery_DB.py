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
from database.models.Jackpot import Jackpot

from controllers.try_cmds.lottery import (
    logic as lottery_logic,
    LotteryResult,
    LotteryOutcome,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

NOW = 10_000_000


# ---------- fixtures ----------

@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "lottery_db.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_externals(monkeypatch):
    # log_try_event writes Events, add_balance_history writes a shared buffer: stub both
    monkeypatch.setattr("controllers.try_cmds.lottery.get_timestamp", lambda: NOW)
    monkeypatch.setattr("controllers.try_cmds.lottery.db_logs.log_try_event", AsyncMock())
    monkeypatch.setattr("controllers.try_cmds.lottery.timed_tasks.add_balance_history", AsyncMock())


# ---------- helpers ----------

async def _seed_user(session, discord_id, balance, status, luck_factor, lottery_timestamp, jackpot):
    new_user = User(discord_id=discord_id)
    session.add(new_user)
    await session.flush()

    # one Jackpot row: get_lottery_info reads it via subquery, update_lottery_and_user writes it
    session.add_all([
        Balance(id=new_user.id, balance=balance),
        Status(id=new_user.id, status=int(status)),
        UserData(id=new_user.id, double_curr_row=0, double_max_row=0, luck_factor=luck_factor),
        Timestamp(id=new_user.id, lottery=lottery_timestamp),
        Jackpot(id=1, money=jackpot),
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
    "too_poor",
    "cooldown",
    "lost",
    "win_5th",
    "win_grand",
])
async def test_lottery_scenarios(db_session, try_data, mock_externals, monkeypatch, scenario_name):
    scenario = try_data["lottery"][scenario_name]
    setup = scenario["setup"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    await _seed_user(
        db_session, discord_id,
        balance=setup["balance"], status=setup["status"], luck_factor=setup["luck_factor"],
        lottery_timestamp=NOW - setup["time_since_last"], jackpot=setup["jackpot"],
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

    # balance in the DB after the real UnitOfWork transaction
    db_session.expire_all()
    actual_balance = await _get_balance(db_session, discord_id)
    assert actual_balance == expected["balance"], (
        f"[{scenario_name}] balance: expected {expected['balance']}, got {actual_balance}"
    )
