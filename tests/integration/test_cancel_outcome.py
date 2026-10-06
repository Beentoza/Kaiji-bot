import time

import pytest
from sqlalchemy import select

from database.models.Bets import Bet
from database.models.Balances import Balance
from database.models.BetParticipation import BetParticipation
from database.models.BetEvents import BetEvents, BetEventType
from database.models.OutcomeEvents import OutcomeEvents, OutcomeEventType
from helpers.BetTypes import BetEndType
from controllers.outcomes.outcome_cancel import logic
from database.models.models import BetStatus
import constants

pytestmark = pytest.mark.integration


USER = 3001    # places the bet in every test
OTHER = 3002   # already bet on OPEN: someone else's row must not block or leak into ours
CREATOR = 3041
BALANCE = 100

TARGET = ("match", 1)       # the outcome the tests cancel; each test seeds it itself
SAME_THEME = ("match", 2)   # neighbour: TARGET's theme, other server
SAME_SERVER = ("derby", 1)  # neighbour: TARGET's server, other theme
NOT_SEEDED = ("cup", 1)

WITNESS = 3011   # bet on both neighbours: no cancel may touch him
NEIGHBOUR_MESSAGES = {SAME_THEME: (21, 211), SAME_SERVER: (12, 121)}  # differ from TARGET's on purpose
# where the target outcome's message lives: seed it with these, expect them back from logic.
# not None on purpose: None == None would pass even if logic never fills them
CHANNEL_ID = 11
MESSAGE_ID = 111

# who did what on TARGET before the cancel. history is applied in order;
# refund is the expected answer, written by hand, not computed from history
PARTICIPANTS = [
    # discord_id  history                                    refund
    (4101, [("place", 0, 30)],                               30),
    (4102, [("place", 1, 50)],                               50),
    (4103, [("withdraw", 0, 20)],                            0),   # took it back: nothing
    (4104, [("withdraw", 0, 20), ("place", 1, 40)],          40),  # withdrew, placed again: once
]


# ---------- fixtures ----------

@pytest.fixture
async def board(seed_user, seed_outcome, seed_place):
    # the neighbourhood every cancel test runs in: two outcomes that look like TARGET,
    # each with a WITNESS bet. returns {(theme, server_id): bets.id}
    creator_pk = await seed_user(CREATOR, balance=BALANCE, status=constants.STATUS_OUTCOME_CREATOR)
    witness_pk = await seed_user(WITNESS, balance=BALANCE, status=constants.STATUS_USER)
    ids = {}
    for where, (channel_id, message_id) in NEIGHBOUR_MESSAGES.items():
        theme, server_id = where
        ids[where] = await seed_outcome(theme, server_id, creator_pk,
                                        channel_id=channel_id, message_id=message_id)
        await seed_place(witness_pk, ids[where], server_id, option=1, money=30)
    return ids

# ---------- helpers ----------

async def _seed_participants(seed_user, seed_place, seed_withdrawn, bet_id, server_id):
    # seeds PARTICIPANTS on the target; returns {user_pk: expected refund} for _assert_refunded
    seed = {"place": seed_place, "withdraw": seed_withdrawn}
    refunds = {}
    for discord_id, history, refund in PARTICIPANTS:
        pk = await seed_user(discord_id, balance=BALANCE, status=constants.STATUS_USER)
        for action, option, money in history:
            await seed[action](pk, bet_id, server_id, option=option, money=money)
        refunds[pk] = refund
    return refunds


async def _snapshot(db_session):
    # every row a cancel can touch, neighbour outcomes and their users included.
    async def rows(stmt):
        return sorted(tuple(r) for r in (await db_session.execute(stmt)).all())

    return {
        "bets": await rows(select(Bet.id, Bet.theme, Bet.server_id, Bet.status)),
        "balances": await rows(select(Balance.id, Balance.balance)),
        "participation": await rows(select(BetParticipation.bet_id, BetParticipation.user_id,
                                           BetParticipation.option, BetParticipation.money)),
        "bet_events": await rows(select(BetEvents.id, BetEvents.user_id, BetEvents.outcome_id,
                                        BetEvents.event_type)),
        "outcome_events": await rows(select(OutcomeEvents.id, OutcomeEvents.outcome_id,
                                            OutcomeEvents.event_type)),
    }


async def _assert_rejected(db_session, before, result, expected):
    # a rejected cancel: the answer names the reason, and the DB is exactly as it was
    assert result.outcome is expected
    assert await _snapshot(db_session) == before, "rejected cancel changed the DB"


def _expect_target_gone(before, bet_id):
    # what every successful cancel does to the target: its Bet is deleted, its outcome event is 'cancelled'
    # without a seeded 'created' event there is nothing to compare: all([]) passes
    assert any(o_id == bet_id for _, o_id, _ in before["outcome_events"]), "target has no outcome event"
    expected = dict(before)
    expected["bets"] = [b for b in before["bets"] if b[0] != bet_id]
    expected["outcome_events"] = [
        (e_id, o_id, OutcomeEventType.cancelled if o_id == bet_id else kind)
        for e_id, o_id, kind in before["outcome_events"]
    ]
    return expected


async def _assert_emptied(db_session, before, result, bet_id, channel_id, message_id):
    # a cancel with no participants: the target Bet goes away and its outcome event turns 'cancelled'.
    # everything else stays: neighbour outcomes, 'withdrawn' BetEvents, balances
    assert result.outcome is BetEndType.NO_PARTICIPANTS
    assert (result.channel_id, result.message_id) == (channel_id, message_id)
    assert await _snapshot(db_session) == _expect_target_gone(before, bet_id)


async def _assert_refunded(db_session, before, result, bet_id, refunds, channel_id, message_id):
    # a cancel with participants. refunds = {user_pk: money}, declared by the test, not read from the DB.
    # each of them gets exactly that back, their 'placed' events on the target turn 'refunded',
    # the target's participation goes away. everything else stays: 'withdrawn' events, neighbours
    assert result.outcome is BetEndType.CANCELLED
    assert (result.channel_id, result.message_id) == (channel_id, message_id)
    assert any(p[0] == bet_id for p in before["participation"]), "target has no participants"
    # balances.id == users.id, so refunds are keyed by user_pk. A discord id here would match
    # nothing, and "nobody refunded" would pass
    assert set(refunds) <= {b_id for b_id, _ in before["balances"]}, "refunds keyed by unknown ids"

    expected = _expect_target_gone(before, bet_id)
    expected["participation"] = [p for p in before["participation"] if p[0] != bet_id]
    expected["balances"] = [(b_id, money + refunds.get(b_id, 0)) for b_id, money in before["balances"]]
    expected["bet_events"] = [
        (e_id, u_id, o_id,
         BetEventType.refunded if o_id == bet_id and kind is BetEventType.placed else kind)
        for e_id, u_id, o_id, kind in before["bet_events"]
    ]
    assert await _snapshot(db_session) == expected


# ---------- tests ----------



@pytest.mark.parametrize("theme, server_id, status, expected", [
    pytest.param(*TARGET,     constants.STATUS_USER,  BetEndType.NO_RIGHTS,     id="no_rights"),
    pytest.param(*NOT_SEEDED, constants.STATUS_ADMIN, BetEndType.BET_NOT_FOUND, id="no_such_bet"),
])
async def test_cancel_rejected(db_session, seed_user, board, uow, theme, server_id, status, expected):
    await seed_user(USER, balance=0, status=status)
    before = await _snapshot(db_session)
    result = await logic(USER, theme, server_id, uow)
    assert result.outcome is expected
    await _assert_rejected(db_session,before, result, expected)

@pytest.mark.parametrize("theme, server_id, status, bet_status", [
    # status = the canceller's (the threshold itself and above); bet_status = the outcome's:
    # cancel doesn't look at it, so open, expired and closed outcomes all go the same way
    pytest.param(*TARGET,    constants.STATUS_OUTCOME_CREATOR, BetStatus.ACTIVE,      id="active"),
    pytest.param(*TARGET, constants.STATUS_ADMIN,           BetStatus.IN_PROGRESS, id="in_progress"),
    pytest.param(*TARGET, constants.STATUS_ADMIN,           BetStatus.CLOSED,      id="closed"),
])
async def test_cancel_empty(db_session, seed_user,seed_outcome,board, uow, theme, server_id, status, bet_status):
    user_pk = await seed_user(USER, balance=0, status=status)
    bet_id = await seed_outcome(theme=theme, server_id=server_id, creator_pk=user_pk, channel_id=CHANNEL_ID, message_id=MESSAGE_ID,status=bet_status)
    before = await _snapshot(db_session)
    result = await logic(USER, theme, server_id, uow)
    await _assert_emptied(db_session, before, result, bet_id, CHANNEL_ID, MESSAGE_ID)

@pytest.mark.parametrize("theme, server_id, status, bet_status", [
    # always TARGET: the participants are seeded on TARGET[1]; only the outcome's status varies
    pytest.param(*TARGET, constants.STATUS_ADMIN, BetStatus.ACTIVE,      id="active"),
    pytest.param(*TARGET, constants.STATUS_ADMIN, BetStatus.IN_PROGRESS, id="in_progress"),
])
async def test_cancel_with_users(db_session, seed_user,seed_outcome,board,seed_place,seed_withdrawn, uow, theme, server_id, status, bet_status):
    user_pk = await seed_user(USER, balance=0, status=status)
    bet_id = await seed_outcome(theme=theme, server_id=server_id, creator_pk=user_pk, channel_id=CHANNEL_ID,
                                message_id=MESSAGE_ID, status=bet_status)
    refunds = await _seed_participants(seed_user, seed_place, seed_withdrawn, bet_id, TARGET[1])
    before = await _snapshot(db_session)
    result = await logic(USER, theme, server_id, uow)
    await _assert_refunded(db_session, before, result, bet_id, refunds, channel_id=CHANNEL_ID,message_id=MESSAGE_ID)