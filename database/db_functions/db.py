from database.factory import SessionLocal
from database.models.Users import User
from database.models.Events import Events, EventType
from database.models.ChancesData import ChancesData
from helpers.logger_config import internal_logger as logger
from sqlalchemy import select, func
import time


async def log_get_event(user_id: int):
    try:
        async with SessionLocal() as session:
            async with session.begin():
                internal_id = select(User.id).where(User.discord_id == user_id).scalar_subquery()
                market_stmt = await session.execute(select(
                    func.count(Events.id).label("len"),
                    func.avg(Events.multiplier).label("avg_multiplier"),
                    func.min(Events.profit).label("lose"),
                    func.max(Events.profit).label("win"),
                    func.sum(Events.profit).label("total_profit")
                ).where(Events.user_id == internal_id, Events.event_type == EventType.market))

                double_stmt = await session.execute(select(
                    func.count(Events.id).label("len"),
                    func.min(Events.profit).label("lose"),
                    func.max(Events.profit).label("win"),
                    func.sum(Events.profit).label("total_profit")
                ).where(Events.user_id == internal_id, Events.event_type == EventType.double))

                lottery_stmt = await session.execute(select(
                    func.count(Events.id).label("len"),
                    func.count(Events.id).filter(Events.profit == 19).label("win_20"),
                    func.count(Events.id).filter(Events.profit == 49).label("win_50"),
                    func.count(Events.id).filter(Events.profit == 124).label("win_125"),
                    func.count(Events.id).filter(Events.profit == 249).label("win_250"),
                    func.count(Events.id).filter(Events.profit > 250).label("win_jackpot"),
                    func.max(Events.profit).label("win"),
                    func.sum(Events.profit).label("total_profit")
                ).where(Events.user_id == internal_id, Events.event_type == EventType.lottery))

                market_log = market_stmt.mappings().one()
                double_log = double_stmt.mappings().one()
                lottery_log = lottery_stmt.mappings().one()
                return market_log, double_log, lottery_log
    except Exception as e:
        logger.warning(e)
        return False


async def add_chances_data(double_info, status_points, market_multiplier):
    try:
        async with SessionLocal() as session:
            async with session.begin():
                log = ChancesData(
                    double_info=double_info,
                    market_multiplier=market_multiplier,
                    status_points=status_points,
                    timestamp=time.time()
                )
                session.add(log)
    except Exception as e:
        logger.error(e)
