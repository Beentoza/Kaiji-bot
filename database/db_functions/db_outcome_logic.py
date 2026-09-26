from database.factory import SessionLocal
from database.models.Users import User
from database.models.Balances import Balance
from database.models.Bets import Bet
from database.models.BetParticipation import BetParticipation
from database.models.OutcomeEvents import OutcomeEvents, OutcomeEventType
from database.models.BetEvents import BetEvents, BetEventType
from database.models.models import BetStatus
from helpers.BetTypes import BetEndType, BetEndResult
from helpers.outcome_rules import validate_outcome, calculate_payouts
from helpers.logger_config import internal_logger as logger
from sqlalchemy import select, update, delete, bindparam, func


class OutcomeLogicRepository:
    def __init__(self, session):
        self.session = session
        
    async def settle_bet(self, outcome_name, server_id, win_option, time_now):
        """Close a bet with a winning option and pay the winners out.

        Returns (outcome, koef, status, channel_id, message_id).
        """
        outcome_info = await self.find_outcome(outcome_name, server_id)

        outcome_info, status = validate_outcome(outcome_info, time_now, win_option)
        if not outcome_info:
            return BetEndResult(outcome=status)

        rows = await self.check_participants(outcome_name, outcome_info)
        if not rows:
            return BetEndResult(
                outcome=BetEndType.NO_PARTICIPANTS,
                channel_id=outcome_info["channel_id"],
                message_id=outcome_info["message_id"],
            )

        calc = calculate_payouts(rows, outcome_info["opts"], win_option)

        if calc["action"] == "refund":
            logger.info(f"No winners or loosers for outcome {outcome_name}")
            await self.execute_refund_step(outcome_info["id"], rows, 'refunded')
            return BetEndResult(
                outcome=BetEndType.NO_WINNERS_OR_LOSERS,
                channel_id=outcome_info["channel_id"],
                message_id=outcome_info["message_id"],
            )

        # calculate_payouts only ever returns "refund" or "payout"
        logger.debug("execute payout step")
        await self.execute_payout_step(outcome_info["id"], rows, outcome_info["win_index"])
        logger.info(f"Successfully ended outcome {outcome_name}")
        return BetEndResult(
            outcome=BetEndType.SUCCESS,
            payouts=calc["outcome"],
            koef=calc["koef"],
            channel_id=outcome_info["channel_id"],
            message_id=outcome_info["message_id"],
        )


    async def refund_bet(self, outcome_name, server_id, action='cancelled'):
        """Give every participant their stake back and remove the bet.

        action: the OutcomeEvents type written to the log -- 'cancelled' or 'refunded'.
        Returns (outcome, koef, status, channel_id, message_id).
        """
        outcome_info = await self.find_outcome(outcome_name, server_id)
        if not outcome_info:
            return BetEndResult(outcome=BetEndType.BET_NOT_FOUND)

        rows = await self.check_participants(outcome_name, outcome_info)
        if not rows:
            return BetEndResult(
                outcome=BetEndType.NO_PARTICIPANTS,
                channel_id=outcome_info["channel_id"],
                message_id=outcome_info["message_id"],
            )

        logger.info(f"Starting to refund {outcome_name}")
        await self.execute_refund_step(outcome_info["id"], rows, action)
        return BetEndResult(
            outcome=BetEndType.CANCELLED,
            channel_id=outcome_info["channel_id"],
            message_id=outcome_info["message_id"],
        )


    async def find_outcome(self, outcome_name, server_id) -> dict | None:
        """Returns outcome info"""
        stmt = select(Bet).where(Bet.theme == outcome_name)
        if server_id: stmt = stmt.where(Bet.server_id == server_id)
        stmt = stmt.with_for_update()
        bet = (await self.session.execute(stmt)).scalar_one_or_none()
        if not bet:
            logger.info(f"Didn't found outcome {outcome_name}")
            return None
        return {
            "id": bet.id,
            "opts": bet.options,
            "end_timestamp": bet.end_timestamp,
            "channel_id": bet.channel_id,
            "message_id": bet.message_id,
        }


    async def check_participants(self, outcome_name, bet_info):
        rows = await self.get_participation_data(bet_info["id"])

        if not rows:
            logger.info(f"Didn't find participants for outcome {outcome_name}")
            await self.delete_outcome(bet_info["id"])
            return None
        return rows


    async def get_participation_data(self, bet_id: int) -> list[dict]:
        """Getting all info about outcome: user money on bet, which option, discord_id, internal id, balance"""
        stmt = (
            select(BetParticipation, User, Balance)
            .join(User, User.id == BetParticipation.user_id)
            .join(Balance, Balance.id == User.id)
            .where(BetParticipation.bet_id == bet_id)
        )
        res = await self.session.execute(stmt)
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


    async def delete_outcome(self, bet_id):
        await self.session.execute(delete(Bet).where(Bet.id == bet_id))
        await self.session.execute(update(OutcomeEvents).where(OutcomeEvents.outcome_id == bet_id).values(event_type=OutcomeEventType('cancelled')))


    async def execute_payout_step(self, bet_id, rows, win_index):
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
                await self.session.execute(
                    update(Balance)
                    .where(Balance.id == row['balance_id'])
                    .values(balance=Balance.balance + payout)
                )
                winner_balance_ids.append(row['balance_id'])
            else:
                loser_balance_ids.append(row['balance_id'])

        if winner_balance_ids:
            await self.session.execute(
                update(BetEvents)
                .where(
                    BetEvents.outcome_id == bet_id,
                    BetEvents.user_id.in_(winner_balance_ids),
                    BetEvents.event_type == BetEventType.placed,
                )
                .values(event_type=BetEventType.won)
            )

        if loser_balance_ids:
            await self.session.execute(
                update(BetEvents)
                .where(
                    BetEvents.outcome_id == bet_id,
                    BetEvents.user_id.in_(loser_balance_ids),
                    BetEvents.event_type == BetEventType.placed,
                )
                .values(event_type=BetEventType.lost)
            )

        await self.session.execute(
            update(OutcomeEvents)
            .where(OutcomeEvents.outcome_id == bet_id)
            .values(event_type=OutcomeEventType('ended'))
        )
        await self.session.execute(delete(BetParticipation).where(BetParticipation.bet_id == bet_id))
        await self.session.execute(delete(Bet).where(Bet.id == bet_id))


    async def execute_refund_step(self, bet_id: int, rows, action: str):
        """Refunding money to users and closing outcome"""

        update_data = [
            {
                "b_id": row['balance_id'],
                "add_money": row['bet_money_amount']
            }
            for row in rows
        ]

        stmt = (
            update(Balance)
            .where(Balance.id == bindparam("b_id"))
            .values(balance=Balance.balance + bindparam("add_money"))
        )

        conn = await self.session.connection()
        await conn.execute(stmt, update_data)
        await self.session.execute(
            update(BetEvents)
            .where(BetEvents.outcome_id == bet_id, BetEvents.event_type == BetEventType.placed)
            .values(event_type=BetEventType('refunded')))
        await self.session.execute(update(OutcomeEvents).where(OutcomeEvents.outcome_id == bet_id).values(event_type=OutcomeEventType(action)))
        await self.session.execute(delete(BetParticipation).where(BetParticipation.bet_id == bet_id))
        await self.session.execute(delete(Bet).where(Bet.id == bet_id))


    async def check_open_bets(self, time_now) -> list | None:
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

                    result = await self.session.execute(stmt)
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


    async def checking_couple_bets_if_they_are_vallide(self, bet_ids: list[int]) -> dict:
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

        result = await self.session.execute(stmt)
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


    async def process_in_progress_bets(self) -> dict:
        logger.debug('Checking if some bets should expire')
        try:
            async with SessionLocal() as session:
                async with session.begin():
                    stmt = select(Bet).where(Bet.status == BetStatus.IN_PROGRESS.value)
                    res = await self.session.execute(stmt)
                    bets = res.scalars().all()

                    if not bets:
                        logger.debug("Didn't found bets which should expire")
                        return {"refunded": [], "active": []}

                    bet_ids = [b.id for b in bets]
                    validity_map = await self.checking_couple_bets_if_they_are_vallide(bet_ids)

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

                    # refund_bet opens its own session, and we are already inside one --
                    # so call the session-taking steps it is built from. We already hold the
                    # Bet row, so there is nothing to look up by theme again.
                    invalid_set = set(invalid_ids)
                    for bet in bets:
                        if bet.id not in invalid_set:
                            continue
                        rows = await self.get_participation_data(bet.id)
                        if rows:
                            await self.execute_refund_step(bet.id, rows, 'cancelled')
                        else:
                            await self.delete_outcome(bet.id)

                    active_bets_objects = []
                    if valid_ids:
                        await self.session.execute(
                            update(Bet)
                            .where(Bet.id.in_(valid_ids))
                            .values(status=BetStatus.CLOSED.value)
                        )
                        res_active = await self.session.execute(select(Bet).where(Bet.id.in_(valid_ids)))
                        active_bets_objects = res_active.scalars().all()

                    logger.debug('Found a bets which should expire, returning')
                    return {
                        "refunded": refund_info,
                        "active": list(active_bets_objects)
                    }

        except Exception as e:
            logger.error(f"Error in process_in_progress_bets: {e}")
            return {"refunded": [], "active": []}