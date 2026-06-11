from database.factory import SessionLocal
from database.models.Users import User
from database.models.Balances import Balance
from database.models.Bets import Bet
from database.models.BetParticipation import BetParticipation
from database.models.OutcomeEvents import OutcomeEvents, OutcomeEventType
from database.models.BetEvents import BetEvents, BetEventType
from database.models.models import BetStatus
from helpers.logger_config import internal_logger as logger
from sqlalchemy import select, update, delete, bindparam, func


async def get_results_and_apply_payouts(bet_theme: str, current_time: float = None, server_id: int = None, win_choice: str = None, action: str = None, time_check: bool = True, session=None):
    """Ending bet:
    current_time: only if bet ending with a result. Need to give it only after outcome closed
    server_id: necessary, don't needed for automatic closing
    win_choice: don't needed only if action = refund
    time_check: don't needed only if cancelling bet
    session: if provided, uses existing session/transaction; otherwise creates its own
    """
    if session:
        return await _get_results_and_apply_payouts(session, bet_theme, current_time, server_id, win_choice, action, time_check)

    try:
        async with SessionLocal() as session:
            async with session.begin():
                return await _get_results_and_apply_payouts(session, bet_theme, current_time, server_id, win_choice, action, time_check)
    except Exception as e:
        logger.warning(e)
        return None, 0, "error", None, None


async def _get_results_and_apply_payouts(session, bet_theme, current_time, server_id, win_choice, action, time_check):
    logger.debug("Started work bet_and_validate")
    bet_info, status = await get_bet_and_validate(session, bet_theme, current_time, win_choice, server_id, time_check, action)
    logger.debug("Checked")
    if not bet_info:
        logger.info(f"Didn't found outcome {bet_theme}")
        return None, 0, status, None, None

    logger.debug("get participation data")
    rows = await get_participation_data(session, bet_info["id"])

    if not rows:
        logger.info(f"Didn't find participants for outcome {bet_theme}")
        await delete_outcome(session, bet_info["id"])
        return None, 0, "no_participants", bet_info["channel_id"], bet_info["message_id"]

    if action == 'refund':
        logger.info(f"Starting to refund {bet_theme}")
        await execute_refund_step(session, bet_info["id"], rows, 'cancelled')
        return None, 0, "cancelled", bet_info["channel_id"], bet_info["message_id"]

    calc = calculate_payouts(rows, bet_info["opts"], win_choice)

    if calc["action"] == "refund":
        logger.info(f"No winners or loosers for outcome {bet_theme}")
        await execute_refund_step(session, bet_info["id"], rows, 'refunded')
        return None, 0, "no_winners_or_losers", bet_info["channel_id"], bet_info["message_id"]

    if calc["action"] == "payout":
        logger.debug("execute payout step")
        await execute_payout_step(session, bet_info["id"], rows, bet_info["win_index"])
        logger.info(f"Successfully ended outcome {bet_theme}")
        return calc["outcome"], calc["koef"], "success", bet_info["channel_id"], bet_info["message_id"]


async def get_bet_and_validate(session, bet_theme: str, current_time: float, choice: str, server_id: int, time_check: bool, action: str = None) -> tuple[dict | None, str]:
    """Checking if bet exists, if it, returning bet_id, options and win index option"""
    stmt = select(Bet).where(Bet.theme == bet_theme)
    if server_id:
        stmt = stmt.where(Bet.server_id == server_id)
    res = await session.execute(stmt)
    bet = res.scalar_one_or_none()

    if not bet: return None, "bet_not_found"
    if time_check:
        if bet.end_timestamp > current_time: return None, "open_bet"

    opts = bet.options
    if action != 'refund' and choice not in opts:
        return None, "not_option"

    win_index = opts.index(choice) if choice in opts else None
    return {"id": bet.id, "opts": opts, "win_index": win_index, "channel_id": bet.channel_id, "message_id": bet.message_id}, "ok"


async def get_participation_data(session, bet_id: int) -> list[dict]:
    """Getting all info about outcome: user money on bet, which option, discord_id, internal id, balance"""
    stmt = (
        select(BetParticipation, User, Balance)
        .join(User, User.id == BetParticipation.user_id)
        .join(Balance, Balance.id == User.id)
        .where(BetParticipation.bet_id == bet_id)
    )
    res = await session.execute(stmt)
    rows = res.all()

    data = []
    for bet_partic, user, balance in rows:
        data.append({
            "bet_money_amount": bet_partic.money,
            "bet_option": bet_partic.option,
            "user_discord_id": user.discord_id,
            "balance_id": balance.id,
            "balance_value": balance.balance
        })

    return data


def calculate_payouts(rows, opts, choice) -> dict:
    outcome = {opt: {} for opt in opts}
    active_options = set()
    win_summ, looser_summ = 0, 0

    for row in rows:
        choice_name = opts[row['bet_option']]
        outcome[choice_name][row['user_discord_id']] = row['bet_money_amount']
        active_options.add(row['bet_option'])

        if choice_name == choice:
            win_summ += row['bet_money_amount']
        else:
            looser_summ += row['bet_money_amount']

    if len(active_options) < 2 or win_summ == 0 or looser_summ == 0:
        return {"action": "refund", "outcome": outcome}

    koef = looser_summ / win_summ
    return {"action": "payout", "outcome": outcome, "koef": koef}


async def delete_outcome(session, bet_id):
    await session.execute(delete(Bet).where(Bet.id == bet_id))
    await session.execute(update(OutcomeEvents).where(OutcomeEvents.outcome_id == bet_id).values(event_type=OutcomeEventType('cancelled')))


async def execute_payout_step(session, bet_id, rows, win_index):
    """Giving/withdraw money to users and deleting bet"""
    winner_balance_ids = []
    loser_balance_ids = []

    # integer payout, no float: winner gets stake + stake * loser_sum // win_sum.
    # the remainder of // is dropped (stays in the bank). only reached when both
    # sums are > 0 (calculate_payouts already guards that), so no division by zero.
    win_sum = sum(r['bet_money_amount'] for r in rows if r['bet_option'] == win_index)
    loser_sum = sum(r['bet_money_amount'] for r in rows if r['bet_option'] != win_index)

    for row in rows:
        if row['bet_option'] == win_index:
            payout = row['bet_money_amount'] + row['bet_money_amount'] * loser_sum // win_sum
            # atomic SQL increment instead of read-modify-write on the ORM object
            await session.execute(
                update(Balance)
                .where(Balance.id == row['balance_id'])
                .values(balance=Balance.balance + payout)
            )
            winner_balance_ids.append(row['balance_id'])
        else:
            loser_balance_ids.append(row['balance_id'])

    if winner_balance_ids:
        await session.execute(
            update(BetEvents)
            .where(
                BetEvents.outcome_id == bet_id,
                BetEvents.user_id.in_(winner_balance_ids),
                BetEvents.event_type == BetEventType.placed,
            )
            .values(event_type=BetEventType.won)
        )

    if loser_balance_ids:
        await session.execute(
            update(BetEvents)
            .where(
                BetEvents.outcome_id == bet_id,
                BetEvents.user_id.in_(loser_balance_ids),
                BetEvents.event_type == BetEventType.placed,
            )
            .values(event_type=BetEventType.lost)
        )

    await session.execute(
        update(OutcomeEvents)
        .where(OutcomeEvents.outcome_id == bet_id)
        .values(event_type=OutcomeEventType('ended'))
    )
    await session.execute(delete(BetParticipation).where(BetParticipation.bet_id == bet_id))
    await session.execute(delete(Bet).where(Bet.id == bet_id))


async def execute_refund_step(session, bet_id: int, rows, action: str):
    """Refunding money to users and closing outcome"""
    for row in rows:
        stmt = select(Balance).where(Balance.id == row['balance_id']).with_for_update()
        res = await session.execute(stmt)
        db_balance = res.scalar_one_or_none()
        if not db_balance:
            raise RuntimeError(f"Balance not found for refund: {row['balance_id']}")
        db_balance.balance += row['bet_money_amount']

    await session.execute(
        update(BetEvents)
        .where(BetEvents.outcome_id == bet_id, BetEvents.event_type == BetEventType.placed)
        .values(event_type=BetEventType('refunded')))
    await session.execute(update(OutcomeEvents).where(OutcomeEvents.outcome_id == bet_id).values(event_type=OutcomeEventType(action)))
    await session.execute(delete(BetParticipation).where(BetParticipation.bet_id == bet_id))
    await session.execute(delete(Bet).where(Bet.id == bet_id))


async def check_open_bets(time_now) -> list | None:
    logger.debug('Check in DB for open bets')
    try:
        async with SessionLocal() as session:
            async with session.begin():
                current_ts = int(time_now)

                stmt = (
                    select(Bet)
                    .where(Bet.status == BetStatus.ACTIVE.value)
                    .where(Bet.end_timestamp <= current_ts)
                )

                result = await session.execute(stmt)
                expired_bets = result.scalars().all()

                if not expired_bets:
                    logger.debug('No open bets found which should be closed')
                    return None

                for bet in expired_bets:
                    bet.status = BetStatus.IN_PROGRESS.value

                logger.debug(f"Changing status for {len(expired_bets)} bets...")

                data_to_return = [
                    {
                        "id": b.id,
                        "theme": b.theme,
                        "server_id": b.server_id,
                        "channel_id": b.channel_id,
                        "message_id": b.message_id
                    } for b in expired_bets
                ]
                return data_to_return

    except Exception as e:
        logger.error(f"Error while tried to change open status bets: {e}")
        return None


async def checking_couple_bets_if_they_are_vallide(bet_ids: list[int], session) -> dict:
    if not bet_ids:
        return {}

    stmt = (
        select(
            BetParticipation.bet_id,
            BetParticipation.option,
            func.sum(BetParticipation.money).label('option_total')
        )
        .where(BetParticipation.bet_id.in_(bet_ids))
        .group_by(BetParticipation.bet_id, BetParticipation.option)
    )

    result = await session.execute(stmt)
    rows = result.all()

    stats = {}
    for b_id, opt, total in rows:
        if b_id not in stats:
            stats[b_id] = []
        stats[b_id].append(total)

    validation_results = {}
    for b_id in bet_ids:
        validation_results[b_id] = len(stats.get(b_id, [])) >= 2

    return validation_results


async def process_in_progress_bets() -> dict:
    logger.debug('Checking if some bets should expire')
    try:
        async with SessionLocal() as session:
            async with session.begin():
                stmt = select(Bet).where(Bet.status == BetStatus.IN_PROGRESS.value)
                res = await session.execute(stmt)
                bets = res.scalars().all()

                if not bets:
                    logger.debug("Didn't found bets which should expire")
                    return {"refunded": [], "active": []}

                bet_ids = [b.id for b in bets]
                validity_map = await checking_couple_bets_if_they_are_vallide(bet_ids, session)

                valid_ids = []
                invalid_ids = []
                refund_info = []

                for bet in bets:
                    if validity_map.get(bet.id):
                        valid_ids.append(bet.id)
                    else:
                        invalid_ids.append(bet.id)
                        refund_info.append({"channel_id": bet.channel_id, "message_id": bet.message_id, "theme": bet.theme})

                logger.debug(f"Found {len(invalid_ids)} bets, which should expire")

                for bet in bets:
                    if bet.id in invalid_ids:
                        await get_results_and_apply_payouts(
                            bet_theme=bet.theme, action='refund', time_check=False, session=session
                        )

                active_bets_objects = []
                if valid_ids:
                    await session.execute(
                        update(Bet)
                        .where(Bet.id.in_(valid_ids))
                        .values(status=BetStatus.CLOSED.value)
                    )
                    res_active = await session.execute(select(Bet).where(Bet.id.in_(valid_ids)))
                    active_bets_objects = res_active.scalars().all()

                logger.debug('Found a bets which should expire, returning')
                return {
                    "refunded": refund_info,
                    "active": list(active_bets_objects)
                }

    except Exception as e:
        logger.error(f"Error in process_in_progress_bets: {e}")
        return {"refunded": [], "active": []}