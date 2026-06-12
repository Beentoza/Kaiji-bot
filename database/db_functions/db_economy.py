from database.factory import SessionLocal
from database.models.Users import User
from database.models.Balances import Balance
from database.models.Statuses import Status
from database.models.Jackpot import Jackpot
from database.models.Timestamps import Timestamp
from database.models.GlobalEvents import WorldState
from database.models.UserData import UserData
from helpers.logger_config import internal_logger as logger
from sqlalchemy import select, update, true
import time


async def get_jackpot_info() -> str | None:
    async with SessionLocal() as session:
        try:
            result = await session.execute(select(Jackpot.money).limit(1))
            return result.scalar()
        except Exception as e:
            logger.error(f"Error: {e}")
            return None


async def add_to_jackpot(session, amount: int):
    try:
        await session.execute(update(Jackpot).values(money=Jackpot.money + amount))
    except Exception as e:
        logger.error(f"Error: {e}")
        raise


async def update_lottery_and_user(session, user_id: int, user_money_change: int, jackpot_change: int, timer: int = 0) -> int | None:
    try:
        logger.debug(f"Started work in lottery and user balances")
        user_id_sub = select(User.id).where(User.discord_id == user_id).scalar_subquery()

        await session.execute(
            update(Timestamp)
            .where(Timestamp.id == user_id_sub)
            .values(lottery=int(time.time()) + timer)
        )
        await session.execute(
            update(Balance)
            .where(Balance.id == user_id_sub)
            .values(balance=Balance.balance + user_money_change)
        )
        await session.execute(
            update(Jackpot)
            .values(money=Jackpot.money + jackpot_change)
        )
        logger.debug(f"Changed {user_id}: user balance + {user_money_change}, jackpot + {jackpot_change}")


    except Exception as e:
        logger.warning(f"Error for {user_id}: {e}")
        raise


async def get_lottery_info(session, user_id: int):
    try:
        jackpot_subquery = select(Jackpot.money).limit(1).scalar_subquery()
        stmt = (
            select(
                Timestamp.lottery,
                Balance.balance,
                Status.status,
                jackpot_subquery.label("jackpot_balance"),
                UserData.luck_factor
            )
            .select_from(User)
            .join(Balance, Balance.id == User.id)
            .join(Status, Status.id == User.id)
            .join(Timestamp, Timestamp.id == User.id)
            .join(UserData, UserData.id == User.id)
            .where(User.discord_id == user_id)
        )
        result = await session.execute(stmt)
        return result.one_or_none()
    except Exception as e:
        logger.error(f"Error for {user_id}: {e}")
        return None


async def get_timestamp_balance_status(session, user_id: int, timestamp_column_name: str):
    try:
        target_column = getattr(Timestamp, timestamp_column_name)
        stmt = (
            select(target_column, Balance.balance, Status.status, UserData.luck_factor)
            .select_from(User)
            .join(Balance, User.id == Balance.id)
            .join(Status, User.id == Status.id)
            .join(Timestamp, User.id == Timestamp.id)
            .join(UserData, User.id == UserData.id)
            .where(User.discord_id == user_id)
        )
        result = await session.execute(stmt)
        return result.one_or_none()
    except Exception as e:
        logger.error(f"Error for {user_id}: {e}")
        raise

async def get_balance_status_luckfactor(user_id: int, session):
    try:
        stmt = (
            select(Balance.balance, Status.status, UserData.luck_factor)
            .select_from(User)
            .join(Balance, User.id == Balance.id)
            .join(Status, User.id == Status.id)
            .join(UserData, User.id == UserData.id)
            .where(User.discord_id == user_id)
        )
        result = await session.execute(stmt)
        return result.one_or_none()
    except Exception as e:
        logger.error(f"Error for {user_id}: {e}")
        raise


async def get_pickup_change_info(session, user_id: int):
    try:
        stmt = (
            select(
                WorldState.pickupchange_timestamp,
                WorldState.pickupchange_cooldown,
                Timestamp.pick_up_change,
                Timestamp.pick_up_change_timer,
                Balance.balance,
                Status.status
            )
            .select_from(User)
            .join(WorldState, true())
            .join(Balance, User.id == Balance.id)
            .join(Status, User.id == Status.id)
            .join(Timestamp, User.id == Timestamp.id)
            .where(User.discord_id == user_id)
            .where(WorldState.id == 1)
        )
        result = await session.execute(stmt)
        data = result.one_or_none()
        if data is None:
            return None
        return {
            "global_timestamp": data[0],
            "global_cooldown": data[1],
            "user_timestamp": data[2],
            "user_cooldown": data[3],
            "balance": data[4],
            "status": data[5]
        }
    except Exception as e:
        logger.error(f"Error for {user_id}: {e}")
        raise


async def update_personal_pickupchange_info(session, user_id, timestamp, cooldown):
    try:
        user_id_subquery = select(User.id).where(User.discord_id == user_id).scalar_subquery()
        await session.execute(
            update(Timestamp)
            .where(Timestamp.id == user_id_subquery)
            .values(pick_up_change=timestamp, pick_up_change_timer=cooldown)
        )
    except Exception as e:
        logger.error(f"Error happened {e}")
        raise


async def update_global_pickupchange_info(session, timestamp, cooldown):
    try:
        await session.execute(
            update(WorldState)
            .where(WorldState.id == 1)
            .values(pickupchange_timestamp=timestamp, pickupchange_cooldown=cooldown)
        )
    except Exception as e:
        logger.error(f"Error happened {e}")
        raise
