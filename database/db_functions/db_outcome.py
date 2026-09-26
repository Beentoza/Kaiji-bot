from database.factory import SessionLocal
from database.models.Users import User
from database.models.Bets import Bet
from database.models.BetParticipation import BetParticipation
from database.models.OutcomeEvents import OutcomeEvents, OutcomeEventType
from helpers.logger_config import internal_logger as logger
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload
import time

class OutcomeRepository:
    def __init__(self, session):
        self.session = session


    async def _log_outcome_event(self, user_id: int, outcome_id: int, outcome_name: str, event_type: str, server_id: int) -> None:
        logger.debug(f'Starting saving outcome {outcome_name} for {user_id}')
        internal_id = select(User.id).where(User.discord_id == user_id).scalar_subquery()
        self.session.add(OutcomeEvents(
            user_id=internal_id,
            event_type=OutcomeEventType(event_type),
            outcome_id=outcome_id,
            outcome_name=outcome_name,
            server_id=server_id,
            timestamp=int(time.time())
        ))


    async def add_new_bet(self, theme: str, options: list, end_timestamp: int, message_id: int, channel_id: int, server_id: int, user_id: int) -> int | None:
        """Create a bet. Its id, or None if this server already has a bet with this theme.

        The (server_id, theme) unique constraint decides, not a prior SELECT: two
        creations that both passed get_bet_with_same_name still end with one row.
        """
        stmt = (
            pg_insert(Bet)
            .values(theme=theme, options=options, end_timestamp=end_timestamp,
                    message_id=message_id, channel_id=channel_id, server_id=server_id)
            .on_conflict_do_nothing(index_elements=[Bet.server_id, Bet.theme])
            .returning(Bet.id)
        )
        bet_id = (await self.session.execute(stmt)).scalar_one_or_none()

        if bet_id is None:
            logger.info(f"Outcome {theme} already exists on server {server_id}, skipping")
            return None

        await self._log_outcome_event(user_id=user_id, outcome_id=bet_id, outcome_name=theme,
                                event_type='created', server_id=server_id)
        return bet_id


    async def get_bet_with_same_name(self, outcome: str, server_id) -> bool:
        logger.debug(f"Started checking if outcome with name {outcome} exists")

        bet_stmt = (
            select(Bet)
            .where(Bet.theme == outcome, Bet.server_id == server_id)
            .order_by(Bet.id.desc())
            .limit(1)
        )
        result = await self.session.execute(bet_stmt)
        existing_bet = result.scalar_one_or_none()

        if existing_bet is not None:
            logger.info(f"Checked {outcome} - same outcome exists")
            return True

        logger.debug(f"Checked {outcome} - same outcome doesn't exist")
        return False

    @staticmethod
    def _filter_by_time(stmt, stmt_ind, open, current_time):
        if open == 1:
            cond = Bet.end_timestamp > current_time
        elif open == 0:
            cond = Bet.end_timestamp < current_time
        else: # open can be equal 2, means no filter by time.
            return stmt, stmt_ind
        return stmt.where(cond), stmt_ind.where(cond)

    @staticmethod
    def _filter_by_participation(stmt, stmt_ind, participate, user_id):
        user_participation = (
            select(BetParticipation.bet_id)
            .where(BetParticipation.user_id == user_id)
        ).scalar_subquery()
        if participate == 1:
            stmt = stmt.where(Bet.id.in_(user_participation))
            stmt_ind = stmt_ind.where(Bet.id.in_(user_participation))
        elif participate == 0:
            stmt = stmt.where(~Bet.id.in_(user_participation))
            stmt_ind = stmt_ind.where(~Bet.id.in_(user_participation))

        return stmt, stmt_ind

    async def get_outcomes(self, current_time : float, user_id: int, open: int, participation: int, server_id):
        """Getting outcomes, optional by time and user participation"""
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


        stmt, stmt_ind = self._filter_by_time(stmt, stmt_ind, open, current_time)
        user_obj = await self.session.scalar(select(User).where(User.discord_id == user_id))

        stmt, stmt_ind = self._filter_by_participation(stmt, stmt_ind, participation, user_obj.id)

        result = await self.session.execute(stmt)
        active_bets = result.scalars().all()

        result = await self.session.execute(stmt_ind)
        row_coeff = result.all()

        return active_bets, row_coeff


    async def get_all_bet_themes(self, server_id, open: int):
        """Getting bet names filtered by open/closed status"""
        now = int(time.time())
        stmt = select(Bet.theme).where(Bet.server_id == server_id)
        if open == 1:
            stmt = stmt.where(Bet.end_timestamp > now)
        if open == 0:
            stmt = stmt.where(Bet.end_timestamp < now)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())



    async def get_bet_options_by_theme(self, theme_name: str, server_id):
        """Finds bet by theme and returns list of its options."""
        stmt = select(Bet.options).where(Bet.theme == theme_name, Bet.server_id == server_id)
        result = await self.session.execute(stmt)
        options = result.scalar()
        if options:
            return options if isinstance(options, list) else options.split(',')
        return []
