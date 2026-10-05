import pytest
from sqlalchemy import select

from database.models.Bets import Bet
from database.models.Balances import Balance
from database.models.BetParticipation import BetParticipation
from database.models.BetEvents import BetEvents, BetEventType
from database.models.OutcomeEvents import OutcomeEvents, OutcomeEventType
from helpers.BetTypes import BetEndType
from controllers.outcomes.outcome_end import logic
from database.models.models import BetStatus
import constants
import time
pytestmark = pytest.mark.integration


USER = 3001    # places the bet in every test
OTHER = 3002   # already bet on OPEN: someone else's row must not block or leak into ours
CREATOR = 3041
WITNESS = 3011   # bet on all neighbours: no cancel should touch him
BALANCE = 100
open_time = time.time()+3600
closed_time = time.time()-3600
TARGET = ("match", 1)       # the outcome the tests cancel; each test seeds it itself
SAME_THEME = ("match", 2)   # neighbour: TARGET's theme, other server
SAME_SERVER = ("derby", 1)  # neighbour: TARGET's server, other theme
NOT_SEEDED = ("cup", 1)
ANOTHER_ONE = ('paris', 1)

TARGET_OPTIONS = ['win', 'lose', 'draw']
MISSING_OPTION = 'cool city'   # exists on ANOTHER_ONE, not on the target
assert MISSING_OPTION not in TARGET_OPTIONS

# where the target outcome's message lives: seed it with these, expect them back from logic.
# not None on purpose: None == None would pass even if logic never fills them
CHANNEL_ID = 11
MESSAGE_ID = 111

# who did what on TARGET before the end, one list per refund case. option is an index into
# TARGET_OPTIONS (0 win, 1 lose, 2 draw). history is applied in order;
# refund is the expected answer, written by hand, not computed from history
NOBODY_ON_WINNER = [   # bets on 0 and 2, 'lose' wins: win sum is 0
    # discord_id  history                                    refund
    (4101, [("place", 0, 30)],                               30),
    (4102, [("place", 2, 50)],                               50),
    (4103, [("withdraw", 1, 20)],                            0),   # withdrew from the winner: not a winner
    (4104, [("withdraw", 1, 20), ("place", 2, 40)],          40),  # withdrew, placed again: once
]
ALL_ON_LOSER = [       # everyone on 1, 'draw' wins: one active option, nobody won
    (4101, [("place", 1, 30)],                               30),
    (4102, [("place", 1, 50)],                               50),
    (4103, [("withdraw", 2, 20)],                            0),   # withdrew from the winner: not a winner
]
ALL_ON_WINNER = [      # everyone on 2, 'draw' wins: loser sum is 0
    (4101, [("place", 2, 30)],                               30),
    (4102, [("place", 2, 50)],                               50),
    (4103, [("withdraw", 0, 20)],                            0),   # withdrew from a loser: not a loser
    (4104, [("withdraw", 0, 20), ("place", 2, 40)],          40),
]

# the payout cases: the same stakes every time, only the winner changes.
# sums per option: 0 -> 80, 1 -> 60, 2 -> 30. picked so that // leaves a remainder in every case
STAKES = [
    # discord_id  history
    (4201, [("place", 0, 30)]),
    (4202, [("withdraw", 0, 10), ("place", 0, 50)]),   # one per option withdrew first: his 'withdrawn'
    (4203, [("place", 1, 20)]),
    (4204, [("withdraw", 1, 10), ("place", 1, 40)]),   # must stay, not turn 'won'/'lost' with his 'placed'
    (4205, [("place", 2, 10)]),
    (4206, [("withdraw", 2, 10), ("place", 2, 20)]),
    (4207, [("withdraw", 0, 20)]),   # took it back from option 0: no payout even when 0 wins
]
# every participant also has a bet on this neighbour: 'won'/'lost' must not reach it
PARTICIPANTS_ALSO_ON = SAME_THEME
# what each winner gets back: stake + stake * loser_sum // win_sum, worked out by hand.
# losers and 4207 are not listed: they get 0
PAID_ON_0 = {4201: 30 + 33, 4202: 50 + 56}    # 30*90/80 = 33.75, 50*90/80 = 56.25
PAID_ON_1 = {4203: 20 + 36, 4204: 40 + 73}    # 20*110/60 = 36.67, 40*110/60 = 73.33
PAID_ON_2 = {4205: 10 + 46, 4206: 20 + 93}    # 10*140/30 = 46.67, 20*140/30 = 93.33


# ---------- fixtures ----------

@pytest.fixture
async def board(seed_user, seed_outcome, seed_place):
    # the neighbourhood every cancel test runs in: two outcomes that look like TARGET,
    # each with a WITNESS bet. returns {(theme, server_id): bets.id}
    creator_pk = await seed_user(CREATOR, balance=BALANCE, status=constants.STATUS_OUTCOME_CREATOR)
    witness_pk = await seed_user(WITNESS, balance=BALANCE, status=constants.STATUS_USER)

    bets = [
        (SAME_THEME, ["win", "draw", "lose"]),
        (SAME_SERVER, ["win", "lose"]),
        (ANOTHER_ONE, ['cool city', 'nope'])
    ]
    ids = {}
    for (theme, server_id), options in bets:
        id = await seed_outcome(theme=theme, server_id=server_id, options=options, creator_pk=creator_pk)
        ids[(theme, server_id)] = id
        await seed_place(witness_pk, id, server_id, option=1, money=30)
    return ids

# ---------- helpers ----------

async def _seed_participants(seed_user, seed_place, seed_withdrawn, bet_id, server_id, participants):
    # seeds participants on the target; returns {user_pk: expected refund} for _assert_refunded
    seed = {"place": seed_place, "withdraw": seed_withdrawn}
    refunds = {}
    for discord_id, history, refund in participants:
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


def _expect_target_gone(before, bet_id, outcome_event):
    # what every closing branch does to the target: its Bet is deleted, its outcome event becomes
    # outcome_event ('cancelled' with no participants, 'refunded' on refund).
    # without a seeded 'created' event there is nothing to compare: all([]) passes
    assert any(o_id == bet_id for _, o_id, _ in before["outcome_events"]), "target has no outcome event"
    expected = dict(before)
    expected["bets"] = [b for b in before["bets"] if b[0] != bet_id]
    expected["outcome_events"] = [
        (e_id, o_id, outcome_event if o_id == bet_id else kind)
        for e_id, o_id, kind in before["outcome_events"]
    ]
    return expected


async def _assert_emptied(db_session, before, result, bet_id, channel_id, message_id):
    assert result.outcome is BetEndType.NO_PARTICIPANTS
    assert (result.channel_id, result.message_id) == (channel_id, message_id)
    assert await _snapshot(db_session) == _expect_target_gone(before, bet_id, OutcomeEventType.cancelled)


async def _assert_refunded(db_session, before, result, bet_id, refunds, channel_id, message_id):
    # an end with no winners or no losers. refunds = {user_pk: money}, declared by the test, not read from the DB.
    # each of them gets exactly that back, their 'placed' events on the target turn 'refunded',
    # the target's participation goes away. everything else stays: 'withdrawn' events, neighbours
    assert result.outcome is BetEndType.NO_WINNERS_OR_LOSERS
    assert (result.channel_id, result.message_id) == (channel_id, message_id)
    assert any(p[0] == bet_id for p in before["participation"]), "target has no participants"
    # balances.id == users.id, so refunds are keyed by user_pk. A discord id here would match
    # nothing, and "nobody refunded" would pass
    assert set(refunds) <= {b_id for b_id, _ in before["balances"]}, "refunds keyed by unknown ids"

    expected = _expect_target_gone(before, bet_id, OutcomeEventType.refunded)
    expected["participation"] = [p for p in before["participation"] if p[0] != bet_id]
    expected["balances"] = [(b_id, money + refunds.get(b_id, 0)) for b_id, money in before["balances"]]
    expected["bet_events"] = [
        (e_id, u_id, o_id,
         BetEventType.refunded if o_id == bet_id and kind is BetEventType.placed else kind)
        for e_id, u_id, o_id, kind in before["bet_events"]
    ]
    assert await _snapshot(db_session) == expected


async def _assert_paid(db_session, before, result, bet_id, payouts, channel_id, message_id):
    assert result.outcome is BetEndType.SUCCESS
    assert (result.channel_id, result.message_id) == (channel_id, message_id)
    assert any(p[0] == bet_id for p in before["participation"]), "target has no participants"
    assert set(payouts) <= {b_id for b_id, _ in before["balances"]}, "payouts keyed by unknown ids"
    winners = {pk for pk, money in payouts.items() if money}
    assert winners, "no winners declared: every 'placed' would be expected 'lost'"

    expected = _expect_target_gone(before, bet_id, OutcomeEventType.ended)
    expected["participation"] = [p for p in before["participation"] if p[0] != bet_id]
    expected["balances"] = [(b_id, money + payouts.get(b_id, 0)) for b_id, money in before["balances"]]
    expected["bet_events"] = [
        (e_id, u_id, o_id,
         (BetEventType.won if u_id in winners else BetEventType.lost)
         if o_id == bet_id and kind is BetEventType.placed else kind)
        for e_id, u_id, o_id, kind in before["bet_events"]
    ]
    assert await _snapshot(db_session) == expected


# ---------- tests ----------



@pytest.mark.parametrize("theme, server_id, status, expected", [
    pytest.param(*NOT_SEEDED, constants.STATUS_USER,  BetEndType.NO_RIGHTS,     id="no_rights"),
    pytest.param(*NOT_SEEDED, constants.STATUS_ADMIN, BetEndType.BET_NOT_FOUND, id="no_such_bet"),
])
async def test_end_rejected(db_session, seed_user,board, uow, theme, server_id, status, expected):
    await seed_user(USER, balance=0, status=status)
    before = await _snapshot(db_session)
    result = await logic(USER, theme, server_id, 0, 0,uow)
    await _assert_rejected(db_session,before, result, expected)


@pytest.mark.parametrize("theme, server_id, status, options, win_option, bet_status, timestamp, expected", [
    pytest.param(*TARGET, constants.STATUS_ADMIN,TARGET_OPTIONS,TARGET_OPTIONS[0], BetStatus.ACTIVE,open_time,  BetEndType.OPEN_BET,     id="open_bet"),
    pytest.param(*TARGET, constants.STATUS_ADMIN,TARGET_OPTIONS,MISSING_OPTION, BetStatus.CLOSED,closed_time, BetEndType.NOT_OPTION, id="not_option"),
])
async def test_end_created_rejected(db_session, seed_user,board, seed_outcome, uow, theme, server_id,status,options,win_option,bet_status, timestamp, expected):
    user_pk = await seed_user(USER, balance=0, status=status)
    await seed_outcome(theme=theme, server_id=server_id, creator_pk=user_pk, channel_id=CHANNEL_ID,
                                message_id=MESSAGE_ID, status=bet_status, end_timestamp=timestamp, options=options)
    before = await _snapshot(db_session)
    result = await logic(USER, theme, server_id, win_option,int(time.time()),uow)
    await _assert_rejected(db_session,before, result, expected)


@pytest.mark.parametrize("theme, server_id, status, bet_status", [
    pytest.param(*TARGET, constants.STATUS_OUTCOME_CREATOR, BetStatus.CLOSED,      id="closed1"),
    pytest.param(*TARGET, constants.STATUS_ADMIN,           BetStatus.CLOSED, id="closed2"),
])
async def test_end_empty(db_session, seed_user,seed_outcome,board, uow, theme, server_id, status, bet_status):
    user_pk = await seed_user(USER, balance=0, status=status)
    bet_id = await seed_outcome(theme=theme, server_id=server_id, creator_pk=user_pk, channel_id=CHANNEL_ID, message_id=MESSAGE_ID,
                                status=bet_status, end_timestamp=closed_time, options=TARGET_OPTIONS)
    before = await _snapshot(db_session)

    result = await logic(USER, theme, server_id, TARGET_OPTIONS[1], int(time.time()), uow)
    await _assert_emptied(db_session, before, result, bet_id, CHANNEL_ID, MESSAGE_ID)


@pytest.mark.parametrize("theme, server_id, participants, win_option", [
    pytest.param(*TARGET, NOBODY_ON_WINNER, TARGET_OPTIONS[1], id="nobody_on_winner"),
    pytest.param(*TARGET, ALL_ON_LOSER,     TARGET_OPTIONS[2], id="all_on_loser"),
    pytest.param(*TARGET, ALL_ON_WINNER,    TARGET_OPTIONS[2], id="all_on_winner"),
])
async def test_end_refund(db_session, seed_user, seed_outcome, board, seed_place, seed_withdrawn, uow,
                          theme, server_id, participants, win_option):
    user_pk = await seed_user(USER, balance=0, status=constants.STATUS_ADMIN)
    bet_id = await seed_outcome(theme=theme, server_id=server_id, creator_pk=user_pk, channel_id=CHANNEL_ID,
                                message_id=MESSAGE_ID, status=BetStatus.CLOSED, end_timestamp=closed_time,
                                options=TARGET_OPTIONS)
    refunds = await _seed_participants(seed_user, seed_place, seed_withdrawn, bet_id, server_id, participants)
    before = await _snapshot(db_session)

    result = await logic(USER, theme, server_id, win_option, int(time.time()), uow)
    await _assert_refunded(db_session, before, result, bet_id, refunds, CHANNEL_ID, MESSAGE_ID)


@pytest.mark.parametrize("theme, server_id, win_option, paid", [
    pytest.param(*TARGET, TARGET_OPTIONS[0], PAID_ON_0, id="win_0"),
    pytest.param(*TARGET, TARGET_OPTIONS[1], PAID_ON_1, id="win_1"),
    pytest.param(*TARGET, TARGET_OPTIONS[2], PAID_ON_2, id="win_2"),
])
async def test_end_payout(db_session, seed_user, seed_outcome, board, seed_place, seed_withdrawn, uow,
                          theme, server_id, win_option, paid):
    user_pk = await seed_user(USER, balance=0, status=constants.STATUS_ADMIN)
    bet_id = await seed_outcome(theme=theme, server_id=server_id, creator_pk=user_pk, channel_id=CHANNEL_ID,
                                message_id=MESSAGE_ID, status=BetStatus.CLOSED, end_timestamp=closed_time,
                                options=TARGET_OPTIONS)
    participants = [(discord_id, history, paid.get(discord_id, 0)) for discord_id, history in STAKES]
    payouts = await _seed_participants(seed_user, seed_place, seed_withdrawn, bet_id, server_id, participants)
    _, neighbour_server = PARTICIPANTS_ALSO_ON
    for pk in payouts:
        await seed_place(pk, board[PARTICIPANTS_ALSO_ON], neighbour_server, option=0, money=10)
    before = await _snapshot(db_session)

    result = await logic(USER, theme, server_id, win_option, int(time.time()), uow)
    await _assert_paid(db_session, before, result, bet_id, payouts, CHANNEL_ID, MESSAGE_ID)
    # the result message prints result.payouts: it must be exactly what reached the balances
    assert result.payouts == paid