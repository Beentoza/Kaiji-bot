from sqlalchemy.exc import IntegrityError

from database.factory import SessionLocal
from database.models.Users import User
from database.models.Balances import Balance
from database.models.Bets import Bet
from database.models.BetParticipation import BetParticipation
from database.models.BetEvents import BetEvents, BetEventType
from helpers.logger_config import internal_logger as logger
from sqlalchemy import select, update, delete, true
import time
from helpers.BetTypes import BetType, BetResult


async def log_bet_event(session, user_id: int, outcome_id: int, amount: int, option: int, event_type: str, server_id: int):
    """Adding log in table bet_events for bet commands"""
    try:
        internal_id = select(User.id).where(User.discord_id == user_id).scalar_subquery()
        log = BetEvents(
            user_id=internal_id,
            event_type=BetEventType(event_type),
            outcome_id=outcome_id,
            amount=amount,
            option=option,
            server_id=server_id,
            timestamp=int(time.time())
        )
        session.add(log)
    except Exception as e:
        logger.warning(e)
        raise




async def withdraw_bet_for_user(bet_theme: str, user_id: int, server_id, time_now: int) -> str:
    try:
        async with SessionLocal() as session:
            async with session.begin():
                internal_id = (await session.scalar(select(User).where(User.discord_id == user_id))).id
                stmt = (
                    select(Bet.end_timestamp, BetParticipation)
                    .join(Bet, Bet.id == BetParticipation.bet_id)
                    .where(
                        BetParticipation.user_id == internal_id,
                        Bet.theme == bet_theme,
                        Bet.server_id == server_id)
                )
                result = await session.execute(stmt)

                row = result.one_or_none()

                if row is None:
                    return 'not_existent_bet'
                end_timestamp, participation = row
                if end_timestamp < time_now:
                    return 'closed_bet'

                await session.execute(update(BetEvents).where(
                    BetEvents.user_id == internal_id,
                    BetEvents.outcome_id == participation.bet_id,
                    BetEvents.event_type == BetEventType.placed
                ).values(event_type=BetEventType('withdrawn')))

                await session.execute(update(Balance)
                    .where(Balance.id == internal_id)
                    .values(balance=Balance.balance + participation.money)
                )
                await session.execute(delete(BetParticipation).where(
                    BetParticipation.bet_id == participation.bet_id,
                    BetParticipation.user_id == participation.user_id
                ))
                return 'success'
    except Exception as e:
        logger.warning(e)
        return 'error'




async def process_place_bet(session, user_discord_id: int, bet_theme: str, choice_text: str, amount: int, server_id: int) -> BetResult:
    try:

        stmt = (
            select(Bet, User, Balance)
            .select_from(Bet)
            .join(User, true())
            .join(Balance, Balance.id == User.id)
            .where(Bet.theme == bet_theme, Bet.server_id == server_id)
            .where(User.discord_id == user_discord_id)
        )

        res = await session.execute(stmt)
        data = res.first()

        if not data:
            return BetResult(outcome=BetType.BET_NOT_FOUND)

        bet_entry, user_obj, balance_obj = data

        if time.time() > bet_entry.end_timestamp:
            return BetResult(outcome=BetType.CLOSED)

        opts = bet_entry.options
        list_options = opts if isinstance(opts, list) else opts.split(';')

        if choice_text not in list_options:
            return BetResult(outcome=BetType.CHOICE_NOT_FOUND)

        choice_index = list_options.index(choice_text)
        new_part = BetParticipation(
            bet_id=bet_entry.id,
            user_id=user_obj.id,
            option=choice_index,
            money=amount
        )
        session.add(new_part)

        await session.execute(
            update(Balance)
            .where(Balance.id == user_obj.id)
            .values(balance=Balance.balance - amount)
        )

        await session.flush()
        await log_bet_event(
            session=session,
            user_id=user_discord_id,
            outcome_id=bet_entry.id,
            amount=amount,
            option=choice_index,
            event_type='placed',
            server_id=server_id
        )
        logger.info(f"Placed bet {user_discord_id} on {bet_theme} {choice_text}: {amount}")
        return BetResult(outcome=BetType.SUCCESS, amount=amount, bet_name=bet_theme)
    except IntegrityError as e:
        if "23505" in str(e) or "UniqueViolationError" in str(e):
            return BetResult(outcome=BetType.ALREADY_BET)
        raise
    except Exception as e:
        logger.warning(f"Error Type: {type(e)} | Msg: {e}", exc_info=True)
        raise