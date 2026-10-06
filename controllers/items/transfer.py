from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
import discord

async def handle(interaction: discord.Interaction, item_name: str, target: discord.Member):
    logger.debug(f"Transfer item handle: {interaction.user.id} transfers {item_name} to {target.id}")

    await interaction.response.defer(thinking=True)

    async with UnitOfWork() as uow:
        if not await uow.user.check_user_exists(user_id=target.id):
            return await interaction.followup.send("I have no idea who he even is! How you could het receive a item? Get a cat!")

        success = await uow.items.transfer_item(interaction.user.id, target.id, item_name)
        await uow.commit()

    if not success:
        logger.warning(f"User {interaction.user.id} tried to transfer {item_name} but has 0 in DB")
        return await interaction.followup.send(
            f"Why you don't have **{item_name}** and activating this command? Need a punishment?")

    logger.info(f"User {interaction.user.id} transferred {item_name} to {target.id}")
    return await interaction.followup.send(f"You gave **{item_name}** to {target.mention}")