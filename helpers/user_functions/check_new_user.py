from database.db_functions import db_user
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from discord import Interaction


async def ensure_user_registered(interaction: Interaction) -> None:
    """Add user to DB if not exists, and send onboarding message."""
    async with UnitOfWork() as uow:
        if await db_user.check_user_exists(uow.session, interaction.user.id):
            return
        created = await db_user.add_new_user(uow.session, interaction.user.id)

    if created:
        logger.info(f"New user registered: {interaction.user.id}")
        await interaction.followup.send("Don't forget to check /help for information about commands")


async def is_user_registered(user_id: int) -> bool:
    """Check if user exists in DB."""
    async with UnitOfWork() as uow:
        return await db_user.check_user_exists(uow.session, user_id)
