from database.factory import SessionLocal
from database.models.Users import User
from database.models.Bets import Bet
from database.models.BetParticipation import BetParticipation
from database.models.OutcomeEvents import OutcomeEvents, OutcomeEventType
from helpers.logger_config import internal_logger as logger
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
import time


async def log_outcome_event(user_id: int, outcome_id: int, outcome_name: str, event_type: str, server_id: int) -> bool:
    try:
        async with SessionLocal() as session:
            async with session.begin():
                logger.debug(f'Starting saving outcome {outcome_name} for {user_id}')
                internal_id = select(User.id).where(User.discord_id == user_id).scalar_subquery()
                log = OutcomeEvents(
                    user_id=internal_id,
                    event_type=OutcomeEventType(event_type),
                    outcome_id=outcome_id,
                    outcome_name=outcome_name,
                    server_id=server_id,
                    timestamp=int(time.time())
                )
                session.add(log)
                return True
    except Exception as e:
        logger.warning(e)
        return False


async def add_new_bet(theme: str, options: list, end_timestamp: int, message_id: int, channel_id: int, server_id: int, user_id: int) -> str:
    try:
        async with SessionLocal() as session:
            async with session.begin():
                new_bet = Bet(theme=theme, options=options, end_timestamp=end_timestamp, message_id=message_id, channel_id=channel_id, server_id=server_id)
                session.add(new_bet)
                await session.flush()
                await log_outcome_event(user_id=user_id, outcome_id=new_bet.id, outcome_name=theme, server_id=server_id, event_type='created')
                return new_bet.id
    except Exception as e:
        logger.error(f"Failed to create outcome: {e}")
        return 'None'


async def get_bet_with_same_name(outcome: str, server_id) -> bool:
    logger.debug(f"Started checking if outcome with name {outcome} exists")

    async with SessionLocal() as session:
        bet_stmt = (
            select(Bet)
            .where(Bet.theme == outcome, Bet.server_id == server_id)
            .order_by(Bet.id.desc())
            .limit(1)
        )
        result = await session.execute(bet_stmt)
        existing_bet = result.scalar_one_or_none()

        if existing_bet is not None:
            logger.info(f"Checked {outcome} - same outcome exists")
            return True

        logger.info(f"Checked {outcome} - same outcome doesn't exist")
        return False


async def get_outcomes(current_time: float, user_id: int, open: int, participation: int, server_id):
    """Getting outcomes, optional by time and user participation"""
    async with (SessionLocal() as session):
        stmt = (
            select(Bet)
            .options(
                selectinload(Bet.participations)
                .joinedload(BetParticipation.user)
            )
            .where(Bet.server_id == server_id)
        )

        stmt_ind = (
            select(
                BetParticipation.bet_id,
                BetParticipation.option,
                func.sum(BetParticipation.money).label("sum_amount")
            )
            .join(Bet)
            .where(Bet.server_id == server_id)
            .group_by(BetParticipation.bet_id, BetParticipation.option)
        )

        if open == 1:
            logger.info("Checking only open outcomes")
            stmt = stmt.where(Bet.end_timestamp > current_time)
            stmt_ind = stmt_ind.where(Bet.end_timestamp > current_time)
        if open == 0:
            stmt = stmt.where(Bet.end_timestamp < current_time)
            stmt_ind = stmt_ind.where(Bet.end_timestamp < current_time)

        user_obj = await session.scalar(select(User).where(User.discord_id == user_id))

        if participation == 1:
            stmt = stmt.join(BetParticipation).where(BetParticipation.user_id == user_obj.id)
            stmt_ind = stmt_ind.where(BetParticipation.user_id == user_obj.id)

        if participation == 0:
            user_participation = (
                select(BetParticipation.bet_id)
                .where(BetParticipation.user_id == user_obj.id)
            ).scalar_subquery()

            stmt = stmt.where(~Bet.id.in_(user_participation))
            stmt_ind = stmt_ind.where(~Bet.id.in_(user_participation))

        result = await session.execute(stmt)
        active_bets = result.scalars().all()

        result = await session.execute(stmt_ind)
        row_coeff = result.all()

        bets_mapping = {}

        for bet in range(len(active_bets)):
            total_bet_pool = 0
            for r in row_coeff:
                if r.bet_id == active_bets[bet].id:
                    total_bet_pool += (r.sum_amount or 0)

            opts = active_bets[bet].options if isinstance(active_bets[bet].options, list) else []

            bets_mapping[active_bets[bet].id] = {
                "author": 635433154471002112,
                "title": active_bets[bet].theme,
                "open_before": active_bets[bet].end_timestamp,
                "total_amount": total_bet_pool,
                "outcomes": {name: {"users": {}} for name in opts}
            }

            for r in row_coeff:
                index_bet, option, amount = r
                if r.bet_id == active_bets[bet].id:
                    if 0 <= r.option < len(opts):
                        target_name = opts[r.option]
                        bets_mapping[active_bets[bet].id]["outcomes"][target_name]["total_option_amount"] = amount / total_bet_pool * 100

            for p in active_bets[bet].participations:
                if 0 <= p.option < len(opts):
                    outcome_name = opts[p.option]
                    current_user_id = p.user.discord_id

                    if current_user_id == user_id:
                        display_value = f"{p.money} 👈"
                    else:
                        display_value = p.money

                    bets_mapping[active_bets[bet].id]["outcomes"][outcome_name]["users"][current_user_id] = display_value

        return bets_mapping


async def get_all_bet_themes(server_id, open: int):
    """Getting bet names filtered by open/closed status"""
    async with SessionLocal() as session:
        try:
            now = int(time.time())
            stmt = select(Bet.theme).where(Bet.server_id == server_id)
            if open == 1:
                stmt = stmt.where(Bet.end_timestamp > now)
            if open == 0:
                stmt = stmt.where(Bet.end_timestamp < now)
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Database error in get_active_bet_themes: {e}")
            return []


async def get_bet_options_by_theme(theme_name: str, server_id):
    """Finds bet by theme and returns list of its options."""
    async with SessionLocal() as session:
        stmt = select(Bet.options).where(Bet.theme == theme_name, Bet.server_id == server_id)
        result = await session.execute(stmt)
        options = result.scalar()
        if options:
            return options if isinstance(options, list) else options.split(',')
        return []
