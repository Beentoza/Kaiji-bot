from database.db_functions import db_user, db_effects, db_items
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
import discord


class _EffectAlreadyActive(Exception):
    # raised to roll back the consumed item when the effect is already active
    pass


async def handle(interaction: discord.Interaction, item_name: str, target: discord.Member):
    logger.debug(f"Use item handle: {interaction.user.id} uses {item_name} on {target.id}")

    await interaction.response.defer(thinking=True)

    if not await db_user.check_user_exists(user_id=interaction.user.id):
        return await interaction.followup.send("I have no idea who you even are! How you could have a item? Get a cat!")

    try:
        from database.models.Items import ItemType
        item_type = ItemType(item_name)

        # consume + effect share one transaction: if the effect is already
        # active we raise to roll back the consume, so the item is not lost
        async with UnitOfWork() as uow:
            success = await db_items.consume_item(uow.session, interaction.user.id, item_name)
            if not success:
                logger.warning(f"User {interaction.user.id} tried to use {item_name} but has 0 in DB")
                return await interaction.followup.send(
                    f"Why you don't have **{item_name}** and activating this command? Need a punishment?")

            role_id = await db_items.get_item_role(item_type)

            if role_id is not None:
                effect_added = await db_effects.add_user_effect(
                    uow.session,
                    discord_id=target.id,
                    guild_id=interaction.guild_id,
                    effect_name=item_name,
                    duration_minutes=180
                )

                if not effect_added:
                    raise _EffectAlreadyActive

                role = interaction.guild.get_role(role_id)
                if role:
                    try:
                        await target.add_roles(role)
                        logger.info(f"User {interaction.user.id} used {item_name} on {target.id}, granted role {role_id}")
                        return await interaction.followup.send(f"{target.mention} got the effect of **{item_type.value}**!")
                    except discord.Forbidden:
                        logger.error(f"Bot cannot add role {role_id} due to hierarchy/permissions")
                        return await interaction.followup.send("I don't have permissions to grant this role.")
                else:
                    logger.error(f"Role ID {role_id} not found in guild")
                    return await interaction.followup.send("Role not found.")
            else:
                # item without a role, just inform that it's used
                logger.warning(f"Item {item_name} has no role defined in DB")
                return await interaction.followup.send("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    except _EffectAlreadyActive:
        return await interaction.followup.send(f"**{item_type.value}** is already active on {target.mention}!")
    except Exception as e:
        logger.error(f"CRITICAL ERROR in use_item handle: {e}")
