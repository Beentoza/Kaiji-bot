from database.models.Users import User
from database.models.Balances import Balance
from database.models.Events import Events
from helpers.logger_config import internal_logger as logger
from sqlalchemy import select, desc
import time


class OtherRepository:
    def __init__(self, session):
        self.session = session

    async def get_leaderboard(self):
        try:
            stmt = (
                select(User.discord_id, Balance.balance)
                .join(Balance, User.id == Balance.id)
                .order_by(desc(Balance.balance))
                .limit(5)
            )
            result = await self.session.execute(stmt)
            return result.all()
        except Exception as e:
            logger.warning(e)
            raise


    async def get_chances_data(self):
        day_ago_time = time.time() - 604800 // 7
        try:
            stmt = (
                select(Events.event_type, Events.profit, Events.multiplier)
                .where(Events.timestamp >= day_ago_time)
            )
            result = await self.session.execute(stmt)
            return result.all()
        except Exception as e:
            logger.error(e)
            raise
