import json
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from database.models.Users import User
from database.models.Balances import Balance
from database.models.Statuses import Status
from database.models.Timestamps import Timestamp
from database.models.UserData import UserData
from database.models.Bets import Bet
from database.models.models import BetStatus

from database.db_functions.db_bet import process_place_bet
from database.db_functions.db_outcome_logic import get_results_and_apply_payouts

# starting balance, same as db_user.add_new_user (expected.balances are computed from it)
START_BALANCE = 100


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


# ---------- fixtures ----------

@pytest.fixture
def data():
    with open(FIXTURES_DIR / "bets.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def mock_log_bet_event(monkeypatch):
    # log_bet_event writes Events: stub it out
    mock = AsyncMock()
    monkeypatch.setattr("database.db_functions.db_bet.log_bet_event", mock)
    return mock


# ---------- helpers ----------

async def _seed_all_users(db_session, data):
    # one flush+commit for everyone instead of add_new_user per user (which opened a
    # separate session each -> hundreds of round-trips). Same rows as db_user.add_new_user.
    users = [User(discord_id=info["discord_id"]) for info in data["users"].values()]
    db_session.add_all(users)
    await db_session.flush()  # populate user.id

    rows = []
    for user, info in zip(users, data["users"].values()):
        rows.append(Balance(id=user.id, balance=START_BALANCE))
        rows.append(Status(id=user.id, status=int(info["status"])))
        rows.append(Timestamp(
            id=user.id,
            pick_up_change=0, daily=0, weekly=0, monthly=0, market=0, lottery=0, pick_up_change_timer=0,
        ))
        rows.append(UserData(id=user.id, double_curr_row=0, double_max_row=0, luck_factor=0))
    db_session.add_all(rows)
    await db_session.commit()


async def _seed_bet(db_session, scenario, end_timestamp: float):
    # bet=null in a scenario means "don't create" (used by bet_not_found)
    if scenario["bet"] is None:
        return
    info = scenario["bet"]
    bet = Bet(
        theme=info["theme"],
        server_id=info["server_id"],
        channel_id=info["channel_id"],
        message_id=info["message_id"],
        status=BetStatus.ACTIVE.value,
        end_timestamp=end_timestamp,
        options=info["options"],
    )
    db_session.add(bet)
    await db_session.commit()


async def _place_participations(scenario, data):
    if scenario["bet"] is None:
        return
    bet_info = scenario["bet"]
    for p in scenario["participations"]:
        user_discord_id = data["users"][p["user"]]["discord_id"]
        result = await process_place_bet(
            user_discord_id=user_discord_id,
            bet_theme=bet_info["theme"],
            choice_text=p["choice"],
            amount=p["amount"],
            server_id=bet_info["server_id"],
        )
        assert result == "success", f"failed to place bet for {p['user']}: {result}"


async def _get_balance(db_session, discord_id: int) -> int:
    stmt = (
        select(Balance.balance)
        .join(User, User.id == Balance.id)
        .where(User.discord_id == discord_id)
    )
    res = await db_session.execute(stmt)
    return res.scalar_one()


def _normalize_outcome(expected_outcome):
    # JSON user keys are strings; the function returns outcome with int discord_id keys
    if expected_outcome is None:
        return None
    return {
        opt: {int(uid): amt for uid, amt in users.items()}
        for opt, users in expected_outcome.items()
    }


# ---------- tests ----------

# one representative per integration branch (distinct DB side-effects), not number
# variations: koef/distribution math is covered by the fast unit `outcome_logic.py`.
@pytest.mark.parametrize("scenario_name", [
    "winner_one_loser_big",     # payout, koef=3.0, checks the balance multiplication
    "many_winners_one_loser",   # payout, loop over several winners
    "refund_one_option_only",   # auto refund (no winners or losers)
    "user_initiated_refund",    # action=refund
    "no_participants",          # delete a bet with no participants
    "bet_not_found",            # early return
    "open_bet",                 # time_check: bet not closed yet
])
async def test_settlement_scenarios(db_session, data, mock_log_bet_event, scenario_name):
    scenario = data["scenarios"][scenario_name]
    expected = scenario["expected"]
    settlement = scenario["settlement"]

    # === ARRANGE ===
    await _seed_all_users(db_session, data)
    future_ts = time.time() + 3600
    await _seed_bet(db_session, scenario, end_timestamp=future_ts)
    await _place_participations(scenario, data)

    # === ACT ===
    # settle_before_end -> close before end_ts to get the open_bet status
    if settlement.get("settle_before_end"):
        settlement_time = future_ts - 100
    else:
        settlement_time = future_ts + 1

    # bet=null -> use a fake theme to exercise bet_not_found
    if scenario["bet"] is None:
        bet_theme = settlement["fake_theme"]
        server_id = 999
    else:
        bet_theme = scenario["bet"]["theme"]
        server_id = scenario["bet"]["server_id"]

    settlement_kwargs = {
        "bet_theme": bet_theme,
        "current_time": settlement_time,
        "server_id": server_id,
        "win_choice": settlement["win_choice"],
    }
    if "action" in settlement:
        settlement_kwargs["action"] = settlement["action"]

    outcome, koef, status, channel_id, message_id = await get_results_and_apply_payouts(**settlement_kwargs)

    # === ASSERT === all 5 return values + balances
    assert status == expected["status"], (
        f"[{scenario_name}] status: expected {expected['status']!r}, got {status!r}"
    )
    assert koef == pytest.approx(expected["koef"]), (
        f"[{scenario_name}] koef: expected {expected['koef']}, got {koef}"
    )
    assert channel_id == expected["channel_id"]
    assert message_id == expected["message_id"]
    assert outcome == _normalize_outcome(expected["outcome"]), (
        f"[{scenario_name}] outcome mismatch"
    )

    if expected["balances"]:
        db_session.expire_all()
        for user_name, expected_balance in expected["balances"].items():
            discord_id = data["users"][user_name]["discord_id"]
            actual = await _get_balance(db_session, discord_id)
            assert actual == expected_balance, (
                f"[{scenario_name}] {user_name}: expected {expected_balance}, got {actual}"
            )
