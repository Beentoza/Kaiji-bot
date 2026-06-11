from database.factory import SessionLocal
from database.models.Users import User
from database.models.Timestamps import Timestamp
from sqlalchemy import select, update
from helpers.logger_config import internal_logger as logger

async def set_pick_up_change_time(user_id, time):
    async with SessionLocal() as session:
        try:
            internal_id = (await session.scalar(select(User).where(User.discord_id == user_id))).id
            await session.execute(update(Timestamp).where(Timestamp.id == internal_id).values(pick_up_change=time))
            await session.commit()
        except Exception as e:
            print(f"Data given:\nuser_id = {user_id}\ntime = {time}")
            print(f"Failed to set pick_up_change time: {e}")
        finally:
            await session.close()


async def set_daily_time(session, user_id, time):
    try:
        internal_id = (await session.scalar(select(User).where(User.discord_id == user_id))).id
        await session.execute(update(Timestamp).where(Timestamp.id == internal_id).values(daily=time))
    except Exception as e:
        logger.warning("Error", e)
        raise


async def set_weekly_time(session, user_id, time):
    try:
        internal_id = (await session.scalar(select(User).where(User.discord_id == user_id))).id
        await session.execute(update(Timestamp).where(Timestamp.id == internal_id).values(weekly=time))
    except Exception as e:
        logger.warning("Error", e)
        raise


async def set_monthly_time(session, user_id, time):
    try:
        internal_id = (await session.scalar(select(User).where(User.discord_id == user_id))).id
        await session.execute(update(Timestamp).where(Timestamp.id == internal_id).values(monthly=time))
    except Exception as e:
        logger.warning("Error", e)
        raise


async def set_market_time(session, user_id, time):
    try:
        internal_id = (await session.scalar(select(User).where(User.discord_id == user_id))).id
        await session.execute(update(Timestamp).where(Timestamp.id == internal_id).values(market=time))
    except Exception as e:
        logger.warning("Error", e)
        raise


async def set_lottery_time(user_id, time):
    async with SessionLocal() as session:
        try:
            internal_id = (await session.scalar(select(User).where(User.discord_id == user_id))).id
            await session.execute(update(Timestamp).where(Timestamp.id == internal_id).values(lottery=time))
            await session.commit()
        except Exception as e:
            print(f"Data given:\nuser_id = {user_id}\ntime = {time}")
            print(f"Failed to set lottery time: {e}")
        finally:
            await session.close()
