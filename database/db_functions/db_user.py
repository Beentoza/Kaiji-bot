from database.models.Users import User
from database.models.Balances import Balance
from database.models.Statuses import Status
from database.models.Timestamps import Timestamp
from database.models.UserData import UserData
from database.models.BalanceHistory import BalanceHistory
from database.models.Events import Events, EventType
from helpers.logger_config import internal_logger as logger
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
import time

class UserRepository:
    def __init__(self, session):
        self.session = session


    async def add_new_user(self, user_id, status: int = 1, balance: int = 100, luck_factor: float = 0) -> bool:
        """Register a user. True if this call created him, False if he was already there.

        The insert itself answers "did he exist": on a duplicate discord_id Postgres
        skips the row and RETURNING gives back nothing, so there is no read-then-write
        gap for a concurrent registration to slip into.
        """
        stmt = (
            pg_insert(User)
            .values(discord_id=user_id)
            .on_conflict_do_nothing(index_elements=[User.discord_id])
            .returning(User.id)
        )
        internal_id = (await self.session.execute(stmt)).scalar_one_or_none()

        if internal_id is None:
            logger.debug(f"User {user_id} already registered, skipping")
            return False

        self.session.add_all([
            Balance(id=internal_id, balance=balance),
            Status(id=internal_id, status=int(status)),
            Timestamp(
                id=internal_id,
                pick_up_change=0, daily=0, weekly=0, monthly=0, market=0, lottery=0, pick_up_change_timer=0
            ),
            UserData(
                id=internal_id,
                double_curr_row=0,
                double_max_row=0,
                luck_factor=luck_factor),
        ])

        logger.info(f'Added new user {user_id} into database')
        return True


    async def check_user_exists(self, user_id: int) -> bool:
        """
        Return True if exist and False if not
        """
        try:
            stmt = select(User.id).where(User.discord_id == user_id)
            result = await self.session.execute(stmt)
            exists = result.scalar() is not None
            logger.debug(f" Check if  {user_id} exists: {exists}")
            return exists
        except Exception as e:
            logger.error(f"Couldn't check if {user_id} exists: {e}")
            raise


    async def get_user_status(self, user_id: int):
        try:
            stmt = (
                select(Status.status)
                .join(User, User.id == Status.id)
                .where(User.discord_id == user_id)
            )
            result = await self.session.execute(stmt)
            status = result.scalar()

            if status is not None:
                logger.debug(f"User {user_id} status is {status}")
                return status

            logger.debug(f"User {user_id} not found")
            return None
        except Exception as e:
            logger.error(f"Failed to get status for {user_id}: {e}")
            raise

    async def get_user_status_balance(self, user_id):
        stmt = (
            select(Status.status, Balance.balance)
            .select_from(User)
            .join(Status, User.id == Status.id)
            .join(Balance, User.id == Balance.id)
            .where(User.discord_id == user_id)
        )

        result = await self.session.execute(stmt)
        info_obj = result.one_or_none()
        return info_obj


    async def change_user_status(self, user_id: int, new_status: int):
        try:
            stmt = select(Status).join(User).where(User.discord_id == user_id)
            result = await self.session.execute(stmt)
            status_obj = result.scalar_one_or_none()

            if not status_obj:
                logger.info(f"User {user_id} wasn't found, can't change status")
                return False

            old_status = status_obj.status
            if old_status == new_status:
                logger.info(f"Tried to give  {user_id} same status: {new_status} = {old_status}")
                return True

            status_obj.status = new_status
            logger.info(f"User: {user_id}  Status changed: {old_status} -> {new_status}")
            return True

        except Exception as e:
            logger.error(f"Failed to update status for {user_id}: {e}")
            raise


    async def get_user_balance(self, user_id: int):
        try:
            stmt = select(Balance).join(User).where(User.discord_id == user_id)
            result = await self.session.execute(stmt)
            balance_obj = result.scalar_one_or_none()

            if balance_obj:
                logger.debug(f"User {user_id} balance: {balance_obj.balance}")
                return balance_obj.balance

            logger.warning(f"User {user_id} not found in database, returning 0")
            return 0

        except Exception as e:
            logger.error(f"Failed to see balance for {user_id}: {e}")
            raise


    async def set_user_balance(self, user_id: int, balance_value: int) -> bool:
        try:
            stmt = select(Balance).join(User).where(User.discord_id == user_id)
            result = await self.session.execute(stmt)
            balance_obj = result.scalar_one_or_none()

            if balance_obj:
                old_balance = balance_obj.balance
                balance_obj.balance = balance_value
                logger.debug(f"User: {user_id} | Balance set: {old_balance} -> {balance_value}")
                return True
            else:
                logger.warning(f"User {user_id} not found for balance update")
                return False

        except Exception as e:
            logger.error(f"Failed to set balance for {user_id}: {e}")
            raise


    async def set_user_status(self, user_id: int, status: int):
        try:
            stmt = select(Status).join(User).where(User.discord_id == user_id)
            result = await self.session.execute(stmt)
            user_status = result.scalar_one_or_none()

            user_status.status = status
            logger.info(f"User: {user_id} | Status set to -> {status}")
            return True

        except Exception as e:
            logger.error(f"Failed to set status for {user_id}: {e}")
            raise


    async def update_winstreak(self, user_id, win: int = 1):
        try:
            internal_id = select(User.id).where(User.discord_id == user_id).scalar_subquery()
            await self.session.execute(
                update(UserData)
                .where(UserData.id == internal_id)
                .values(
                    double_curr_row=(UserData.double_curr_row + 1) * win,
                    double_max_row=func.greatest((UserData.double_curr_row + 1) * win, UserData.double_max_row)
                )
            )
            stmt = select(UserData.double_curr_row, UserData.double_max_row).where(UserData.id == internal_id)
            result = await self.session.execute(stmt)
            curr, max_val = result.one()
            logger.debug(f"changed win streak for {user_id}: current={curr}, max={max_val}")
        except Exception as e:
            logger.warning(e)
            raise


    async def get_user_chances_data(self, user_id: int):
        day_ago_time = time.time() - 604800 // 7
        try:
            internal_id = (await self.session.scalar(select(User).where(User.discord_id == user_id))).id
            stmt = (
                select(Events.event_type, Events.profit, Events.multiplier)
                .where(Events.timestamp >= day_ago_time)
                .where(Events.user_id == internal_id)
            )
            result = await self.session.execute(stmt)
            return result.all()
        except Exception as e:
            logger.error(e)
            raise


    async def get_overall_user_info(self, user_id: int):
        try:
            stmt = (
                select(
                    func.min(BalanceHistory.timestamp),
                    Balance.balance,
                    Status.status,
                    UserData.luck_factor
                )
                .select_from(User)
                .join(BalanceHistory, BalanceHistory.user_id == User.id)
                .join(Balance, Balance.id == User.id)
                .join(Status, Status.id == User.id)
                .join(UserData, UserData.id == User.id)
                .where(User.discord_id == user_id)
                .group_by(Balance.balance, Status.status, UserData.luck_factor)
            )
            result = await self.session.execute(stmt)
            return result.one_or_none()
        except Exception as e:
            logger.error(f"DB Error get_overall_info: {e}")
            raise


    async def get_week_balance_history(self, user_id: int):
        week_ago_time = time.time() - 604800
        internal_id = (await self.session.scalar(select(User).where(User.discord_id == user_id))).id
        stmt = (
            select(BalanceHistory.cur_balance, BalanceHistory.timestamp)
            .where(BalanceHistory.user_id == internal_id)
            .where(BalanceHistory.timestamp >= week_ago_time)
        )
        stmt_last_before = (
            select(BalanceHistory.cur_balance)
            .where(BalanceHistory.user_id == internal_id)
            .where(BalanceHistory.timestamp < week_ago_time)
            .order_by(BalanceHistory.timestamp.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        result_first_time = await self.session.execute(stmt_last_before)

        history_data = [(row[0], row[1]) for row in result.all()]
        balance_before = result_first_time.scalar()

        return history_data, balance_before


    async def add_user_balance(self, user_id: int, amount: int) -> None:
        try:
            stmt = (
                update(Balance)
                .where(Balance.id == select(User.id).where(User.discord_id == user_id).scalar_subquery())
                .values(balance=Balance.balance + amount)
            )
            result = await self.session.execute(stmt)

            if not result.rowcount:
                raise ValueError(f"User {user_id} not found for balance update")

            logger.debug(f"User: {user_id} | Balance changed by {amount:+d}")

        except Exception as e:
            logger.error(f"Failed to add balance for {user_id}: {e}")
            raise


    async def multiply_user_balance(self, user_id: int, factor: float) -> int:
        """Atomically set balance = floor(balance * factor) and return the new balance."""
        try:
            stmt = (
                update(Balance)
                .where(Balance.id == select(User.id).where(User.discord_id == user_id).scalar_subquery())
                .values(balance=func.floor(Balance.balance * factor))
                .returning(Balance.balance)
            )
            result = await self.session.execute(stmt)
            new_balance = result.scalar_one_or_none()

            if new_balance is None:
                raise ValueError(f"User {user_id} not found for balance update")

            logger.debug(f"User: {user_id} | Balance multiplied by {factor}, now {new_balance}")
            return new_balance

        except Exception as e:
            logger.error(f"Failed to multiply balance for {user_id}: {e}")
            raise