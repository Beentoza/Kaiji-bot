import helpers.time_handler
from database.models.Users import User
from database.models.Timestamps import Timestamp
from sqlalchemy import select, update
from helpers.logger_config import internal_logger as logger

class TimeRepository:
    def __init__(self, session):
        self.session = session

    async def set_pick_up_change_time(self, user_id, time):
        try:
            internal_id = (await self.session.scalar(select(User).where(User.discord_id == user_id))).id
            await self.session.execute(update(Timestamp).where(Timestamp.id == internal_id).values(pick_up_change=time))
        except Exception as e:
            logger.warning(f"Failed to set pick_up_change time for {user_id}: {e}")
            raise


    async def claim_daily(self, user_id, time):
        internal_id = (await self.session.scalar(select(User).where(User.discord_id == user_id))).id
        result = await self.session.execute(
            update(Timestamp)
            .where((Timestamp.id == internal_id),
                   time-Timestamp.daily >= helpers.time_handler.DAY)
            .values(daily=time)

        )
        return result.rowcount


    async def claim_weekly(self, user_id, time):
        internal_id = (await self.session.scalar(select(User).where(User.discord_id == user_id))).id
        result = await self.session.execute(
            update(Timestamp)
            .where((Timestamp.id == internal_id),
                   time-Timestamp.weekly >= helpers.time_handler.WEEK)
            .values(weekly=time)
        )
        return result.rowcount


    async def claim_monthly(self, user_id, time):
        internal_id = (await self.session.scalar(select(User).where(User.discord_id == user_id))).id
        result = await self.session.execute(
            update(Timestamp)
            .where((Timestamp.id == internal_id),
                   time-Timestamp.monthly >= helpers.time_handler.MONTH)
            .values(monthly=time)
        )
        return result.rowcount


    async def set_market_time(self, user_id, time):
        try:
            internal_id = (await self.session.scalar(select(User).where(User.discord_id == user_id))).id
            await self.session.execute(update(Timestamp).where(Timestamp.id == internal_id).values(market=time))
        except Exception as e:
            logger.warning("Error", e)
            raise


    async def set_lottery_time(self, user_id, time):
        try:
            internal_id = (await self.session.scalar(select(User).where(User.discord_id == user_id))).id
            await self.session.execute(update(Timestamp).where(Timestamp.id == internal_id).values(lottery=time))
        except Exception as e:
            logger.warning(f"Failed to set lottery time for {user_id}: {e}")
            raise
