from database.models.Users import User
from database.models.Statuses import Status
from database.models.Balances import Balance
from helpers.logger_config import internal_logger as logger
from sqlalchemy import select, update

import constants


async def is_admin(session, user_id: int) -> bool:
    """True if the user is an admin. Session-based: execute + raise, no commit."""
    stmt = (
        select(Status.status)
        .join(User, User.id == Status.id)
        .where(User.discord_id == user_id)
    )
    result = await session.execute(stmt)
    status = result.scalar()
    logger.debug(f"Admin check for {user_id}: status={status}")
    return status == constants.STATUS_ADMIN


async def set_target_balance(session, user_id: int, balance: int) -> int | None:
    """Set a user's balance to `balance`. Returns the new balance, or None if the user doesn't exist."""
    stmt = (
        update(Balance)
        .where(Balance.id == select(User.id).where(User.discord_id == user_id).scalar_subquery())
        .values(balance=balance)
        .returning(Balance.balance)
    )
    result = await session.execute(stmt)
    new_balance = result.scalar_one_or_none()
    if new_balance is None:
        logger.debug(f"User {user_id} wasn't found for balance set")
        return None
    logger.info(f"{user_id} balance was set to {new_balance}")
    return new_balance


async def add_target_balance(session, user_id: int, amount: int) -> int | None:
    """Atomically add `amount` to a user's balance (balance = balance + amount).

    Returns the new balance, or None if the user doesn't exist.
    """
    stmt = (
        update(Balance)
        .where(Balance.id == select(User.id).where(User.discord_id == user_id).scalar_subquery())
        .values(balance=Balance.balance + amount)
        .returning(Balance.balance)
    )
    result = await session.execute(stmt)
    new_balance = result.scalar_one_or_none()
    if new_balance is None:
        logger.debug(f"User {user_id} wasn't found for balance add")
        return None
    logger.info(f"{user_id} balance changed by {amount:+d}, now {new_balance}")
    return new_balance


async def set_target_status(session, user_id: int, status: int) -> bool:
    """Set a user's status. Returns True if updated, False if the user doesn't exist."""
    stmt = (
        update(Status)
        .where(Status.id == select(User.id).where(User.discord_id == user_id).scalar_subquery())
        .values(status=status)
    )
    result = await session.execute(stmt)
    if result.rowcount == 0:
        logger.debug(f"User {user_id} wasn't found for status set")
        return False
    logger.info(f"{user_id} status was changed to {status}")
    return True
