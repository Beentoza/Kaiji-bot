from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger


async def ensure_user_registered(user_id: int) -> bool:
    """Add user to DB if not exists. True if this call created the user.

    Called by the command tree before every slash command (helpers/command_tree.py).
    """
    async with UnitOfWork() as uow:
        if await uow.user.check_user_exists(user_id):
            return False
        created = await uow.user.add_new_user(user_id)
        await uow.commit()

    if created:
        logger.info(f"New user registered: {user_id}")
    return created


async def is_user_registered(user_id: int) -> bool:
    """Check if user exists in DB."""
    async with UnitOfWork() as uow:
        exists = await uow.user.check_user_exists(user_id)
        await uow.commit()
        return exists
