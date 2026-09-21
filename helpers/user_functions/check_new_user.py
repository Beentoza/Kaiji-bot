from database.db_functions import db_user
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger


async def ensure_user_registered(user_id: int) -> bool:
    """Add user to DB if not exists. True if this call created the user.

    Called by the command tree before every slash command (helpers/command_tree.py).
    """
    async with UnitOfWork() as uow:
        if await db_user.check_user_exists(uow.session, user_id):
            return False
        created = await db_user.add_new_user(uow.session, user_id)

    if created:
        logger.info(f"New user registered: {user_id}")
    return created


async def is_user_registered(user_id: int) -> bool:
    """Check if user exists in DB."""
    async with UnitOfWork() as uow:
        return await db_user.check_user_exists(uow.session, user_id)
