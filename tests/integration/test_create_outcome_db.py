import json
from pathlib import Path

import pytest
from sqlalchemy import select, func

from database.models.Bets import Bet
from database.models.OutcomeEvents import OutcomeEvents, OutcomeEventType
from controllers.outcomes.outcome_create import create_logic, check_logic
from helpers.BetTypes import BetCreateType, BetCreateResult


pytestmark = pytest.mark.integration


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SCENARIOS = json.loads((FIXTURES_DIR / "outcome_create_db.json").read_text(encoding="utf-8"))["outcomes"]

# create_logic stores them, nothing reads them back here
MESSAGE_ID = 1
CHANNEL_ID = 2

# ---------- fixtures ----------

@pytest.fixture
def try_data():
    with open(FIXTURES_DIR / "outcome_create_db.json", encoding="utf-8") as f:
        return json.load(f)


# ---------- helpers ----------

async def _seed_outcome(db_session, theme, server_id):
    # only (theme, server_id) matter: that's the unique pair; options/time are filler
    new_outcome = Bet(theme=theme, server_id=server_id, options=["a", "b"], end_timestamp=0)
    db_session.add(new_outcome)
    await db_session.flush()
    return new_outcome.id


async def _seed_outcomes(db_session, bets):
    for bet in bets:
        await _seed_outcome(db_session, bet["theme"], bet["server_id"])


async def _count_bets(db_session, theme=None, server_id=None) -> int:
    stmt = select(func.count()).select_from(Bet)
    if theme is not None:
        stmt = stmt.where(Bet.theme == theme, Bet.server_id == server_id)
    return (await db_session.execute(stmt)).scalar_one()


# ---------- tests ----------

@pytest.mark.parametrize("scenario_name", SCENARIOS)
async def test_create_outcome_scenarios(db_session, seed_user, try_data, scenario_name, uow):
    scenario = try_data["outcomes"][scenario_name]
    new = scenario["new"]
    expected = scenario["expected"]
    discord_id = try_data["user"]["discord_id"]

    # === ARRANGE ===
    user_pk = await seed_user(discord_id, status=scenario["status"])
    await _seed_outcomes(db_session, try_data["baseline"])
    pair_before = await _count_bets(db_session, new["theme"], new["server_id"])

    # === ACT 1: preview checks ===
    checked = await check_logic(
        user_id=discord_id,
        guild_id=new["server_id"],
        theme=new["theme"],
        choices=new["choices"],
        timer=new["timer"],
        meas=new["meas"],
        unit_of_work=uow,
    )

    assert isinstance(checked, BetCreateResult), f"[{scenario_name}] expected BetCreateResult, got {checked!r}"
    assert checked.outcome is BetCreateType(expected["check"]), (
        f"[{scenario_name}] check: expected {expected['check']}, got {checked.outcome}"
    )

    if expected["create"] is None:
        assert await _count_bets(db_session, new["theme"], new["server_id"]) == pair_before
        return

    # someone else creates bets while the preview is open
    await _seed_outcomes(db_session, scenario["after"])

    # === ACT 2: confirm, fed with what the preview returned ===
    created = await create_logic(
        theme=new["theme"],
        choices=checked.choices,
        end_timestamp=checked.end_timestamp,
        message_id=MESSAGE_ID,
        channel_id=CHANNEL_ID,
        guild_id=new["server_id"],
        user_id=discord_id,
        unit_of_work=uow,
    )

    # === ASSERT ===
    assert created.outcome is BetCreateType(expected["create"]), (
        f"[{scenario_name}] create: expected {expected['create']}, got {created.outcome}"
    )
    events = (await db_session.execute(select(OutcomeEvents))).scalars().all()

    if created.outcome is BetCreateType.CREATED:
        assert created.bet_id is not None

        # the row holds what the preview returned, not just "some row with this pair"
        bet = await db_session.get(Bet, created.bet_id)
        assert bet.options == list(checked.choices)  # JSON column: the tuple comes back as a list
        assert bet.end_timestamp == checked.end_timestamp
        assert bet.message_id == MESSAGE_ID
        assert bet.channel_id == CHANNEL_ID

        # exactly one 'created' event, with the author resolved (the subquery gives NULL silently)
        assert len(events) == 1, f"[{scenario_name}] expected one event, got {len(events)}"
        event = events[0]
        assert event.event_type is OutcomeEventType.created
        assert event.outcome_id == created.bet_id
        assert event.user_id == user_pk
    else:
        # ON CONFLICT skipped the insert: no bet -> no event either
        assert events == [], f"[{scenario_name}] event logged for a bet that wasn't created"

    # the pair is unique whatever happened: either the new row or the one already there
    assert await _count_bets(db_session, new["theme"], new["server_id"]) == 1
    # near-misses must live side by side, not replace each other
    rows_created = 1 if created.outcome is BetCreateType.CREATED else 0
    total_expected = len(try_data["baseline"]) + len(scenario["after"]) + rows_created
    assert await _count_bets(db_session) == total_expected, f"[{scenario_name}] total bets mismatch"
