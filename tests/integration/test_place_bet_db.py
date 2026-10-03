import time

import pytest
from sqlalchemy import select, func

from database.models.Bets import Bet
from database.models.BetParticipation import BetParticipation
from database.models.BetEvents import BetEvents, BetEventType
from controllers.outcomes.bet_place import logic as place_logic
from helpers.BetTypes import BetPlaceType


pytestmark = pytest.mark.integration


USER = 3001    # places the bet in every test
OTHER = 3002   # already bet on OPEN: someone else's row must not block or leak into ours
BALANCE = 100

# (theme, server_id) - the pair the user types, and the unique key in bets
OPEN = ("match", 1)          # options: win / draw / lose
CLOSED = ("old", 1)          # ended an hour ago
OTHER_SERVER = ("match", 2)  # same theme as OPEN, options: yes / no
NOT_SEEDED = ("cup", 1)


# ---------- fixtures ----------

@pytest.fixture
async def board(db_session, seed_user):
    # same world for every test; returns {(theme, server_id): real bets.id}
    # real clock, not a mock: process_place_bet calls time.time() via `import time`
    now = int(time.time())
    bets = [
        (OPEN, ["win", "draw", "lose"], now + 3600),
        (CLOSED, ["win", "lose"], now - 3600),
        (OTHER_SERVER, ["yes", "no"], now + 3600),
    ]
    ids = {}
    for (theme, server_id), options, end_timestamp in bets:
        bet = Bet(theme=theme, server_id=server_id, options=options, end_timestamp=end_timestamp)
        db_session.add(bet)
        await db_session.flush()
        ids[(theme, server_id)] = bet.id

    other_pk = await seed_user(OTHER, balance=BALANCE, status=1)
    db_session.add(BetParticipation(bet_id=ids[OPEN], user_id=other_pk, option=0, money=50))
    await db_session.flush()
    return ids


# ---------- helpers ----------

async def _place(uow, where, choice, amount):
    theme, server_id = where
    return await place_logic(
        user_id=USER, guild_id=server_id, amount=amount,
        bet=theme, choice=choice, unit_of_work=uow,
    )


async def _rows_of(db_session, user_pk):
    db_session.expire_all()
    parts = (await db_session.execute(
        select(BetParticipation).where(BetParticipation.user_id == user_pk)
    )).scalars().all()
    events = (await db_session.execute(
        select(BetEvents).where(BetEvents.user_id == user_pk)
    )).scalars().all()
    return parts, events


async def _count_participations(db_session) -> int:
    return (await db_session.execute(select(func.count()).select_from(BetParticipation))).scalar_one()


async def _assert_nothing_changed(db_session, get_balance, user_pk, own_bets):
    # a rejected bet leaves no trace: no money moved, no new row, no new event.
    # own_bets = [(option, money)] the user already had before the call,
    # each seeded with its 'placed' event, like the real code does
    parts, events = await _rows_of(db_session, user_pk)
    assert await get_balance(USER) == BALANCE, "user's money moved"
    assert await get_balance(OTHER) == BALANCE, "other user's money moved"
    assert [(p.option, p.money) for p in parts] == own_bets, "user's bets changed"
    # only the events of the bets that were already there, nothing new
    assert [(e.option, e.amount) for e in events] == own_bets, "event logged for a bet that wasn't placed"
    # OTHER's row must survive too: 1 of theirs + whatever the user had
    assert await _count_participations(db_session) == 1 + len(own_bets), "someone else's bet was deleted or added"


# ---------- tests ----------

@pytest.mark.parametrize("status, where, choice, amount, expected", [
    pytest.param(0, OPEN,          "draw", 30,  BetPlaceType.BANNED,           id="banned"),  # STATUS_BANNED_USER = 0
    pytest.param(1, OPEN,          "draw", 0,   BetPlaceType.NEGATIVE_AMOUNT,  id="zero_amount"),
    pytest.param(1, OPEN,          "draw", 101, BetPlaceType.TOO_HIGH,         id="more_than_balance"),
    pytest.param(1, NOT_SEEDED,    "draw", 30,  BetPlaceType.BET_NOT_FOUND,    id="no_such_bet"),
    pytest.param(1, ("match", 3),  "draw", 30,  BetPlaceType.BET_NOT_FOUND,    id="theme_exists_on_other_server"),
    pytest.param(1, CLOSED,        "win",  30,  BetPlaceType.CLOSED,           id="closed"),
    pytest.param(1, OPEN,          "yes",  30,  BetPlaceType.CHOICE_NOT_FOUND, id="choice_of_other_bet"),
])
async def test_place_rejected(db_session, seed_user, get_balance, board, uow,
                              status, where, choice, amount, expected):
    user_pk = await seed_user(USER, balance=BALANCE, status=status)

    result = await _place(uow, where, choice, amount)

    assert result.outcome is expected
    await _assert_nothing_changed(db_session, get_balance, user_pk, own_bets=[])


@pytest.mark.parametrize("choice, amount, option", [
    pytest.param("draw", 30,      1, id="middle_option"),  # index 1, not 0: a lost index would still pass on 0
    pytest.param("lose", BALANCE, 2, id="all_in"),
])
async def test_place_success(db_session, seed_user, get_balance, board, uow, choice, amount, option):
    user_pk = await seed_user(USER, balance=BALANCE, status=1)

    result = await _place(uow, OPEN, choice, amount)

    assert result.outcome is BetPlaceType.SUCCESS

    assert await get_balance(USER) == BALANCE - amount
    assert await get_balance(OTHER) == BALANCE

    parts, events = await _rows_of(db_session, user_pk)
    assert len(parts) == 1
    # the row: on OPEN (not OTHER_SERVER with the same theme), index of the choice, the amount placed
    assert (parts[0].bet_id, parts[0].option, parts[0].money) == (board[OPEN], option, amount)

    assert len(events) == 1
    event = events[0]
    assert event.event_type is BetEventType.placed
    # the event: same bet, option and amount as the row, logged for OPEN's server (OPEN[1])
    assert (event.outcome_id, event.option, event.amount, event.server_id) == (board[OPEN], option, amount, OPEN[1])


async def test_place_twice(db_session, seed_user, get_balance, board, uow):
    user_pk = await seed_user(USER, balance=BALANCE, status=1)
    first_option, first_money = 0, 20  # the bet already there; differs from the second one below
    db_session.add_all([
        BetParticipation(bet_id=board[OPEN], user_id=user_pk, option=first_option, money=first_money),
        BetEvents(user_id=user_pk, event_type=BetEventType.placed, outcome_id=board[OPEN],
                  option=first_option, amount=first_money, server_id=OPEN[1], timestamp=0),
    ])
    await db_session.flush()

    result = await _place(uow, OPEN, "draw", 30)

    assert result.outcome is BetPlaceType.ALREADY_BET
    # the first bet survives untouched, the second leaves no trace
    await _assert_nothing_changed(db_session, get_balance, user_pk, own_bets=[(first_option, first_money)])
