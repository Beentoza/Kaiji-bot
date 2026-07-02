import enum
import dataclasses

from database.db_functions import db_user, db_effects, db_items
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
import discord


class ItemUseOutcome(enum.Enum):
    """A types of item-use outcome"""
    NO_USER = "no_user"
    UNKNOWN_ITEM = "unknown_item"
    NOT_OWNED = "not_owned"
    ALREADY_ACTIVE = "already_active"
    NO_ROLE = "no_role"
    GRANTED = "granted"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class ItemUseResult:
    """Logic function returning"""
    outcome: ItemUseOutcome
    item_name: str = ""
    role_id: int | None = None
    target_id: int | None = None


class _EffectAlreadyActive(Exception):
    # raised to roll back the consumed item when the effect is already active
    pass


def _format_item_use_message(result, target_mention):
    """From result making a message"""
    match result.outcome:
        case ItemUseOutcome.NO_USER:
            return "I have no idea who you even are! How you could have a item? Get a cat!"
        case ItemUseOutcome.UNKNOWN_ITEM:
            return f"There's no such item as **{result.item_name}**."
        case ItemUseOutcome.NOT_OWNED:
            return f"Why you don't have **{result.item_name}** and activating this command? Need a punishment?"
        case ItemUseOutcome.ALREADY_ACTIVE:
            return f"**{result.item_name}** is already active on {target_mention}!"
        case ItemUseOutcome.NO_ROLE:
            # item without a role, just inform that it's used
            return "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        case ItemUseOutcome.GRANTED:
            return f"{target_mention} got the effect of **{result.item_name}**!"
    return "Error occurred"


async def logic(interaction_user_id, interaction_guild_id, item_name: str, target_id: int):
    if not await db_user.check_user_exists(user_id=interaction_user_id):
        return ItemUseResult(outcome=ItemUseOutcome.NO_USER, item_name=item_name)

    settings = await db_items.get_item_settings(item_name)
    if settings is None:
        logger.warning(f"User {interaction_user_id} tried to use unknown item {item_name}")
        return ItemUseResult(outcome=ItemUseOutcome.UNKNOWN_ITEM, item_name=item_name)

    if settings.on_author:
        target_id = interaction_user_id

    role_id = settings.role
    # duration is in hours, effects work in minutes
    duration_minutes = (settings.duration or 1) * 60

    try:
        # consume + effect share one transaction: if the effect is already
        # active we raise to roll back the consume, so the item is not lost
        async with UnitOfWork() as uow:
            success = await db_items.consume_item(uow.session, interaction_user_id, item_name)
            if not success:
                logger.warning(f"User {interaction_user_id} tried to use {item_name} but has 0 in DB")
                return ItemUseResult(outcome=ItemUseOutcome.NOT_OWNED, item_name=item_name)

            if role_id is None:
                logger.warning(f"Item {item_name} has no role defined in DB")
                return ItemUseResult(outcome=ItemUseOutcome.NO_ROLE, item_name=item_name, target_id=target_id)

            effect_added = await db_effects.add_user_effect(
                uow.session,
                discord_id=target_id,
                guild_id=interaction_guild_id,
                effect_name=item_name,
                duration_minutes=duration_minutes
            )
            if not effect_added:
                raise _EffectAlreadyActive
    except _EffectAlreadyActive:
        return ItemUseResult(outcome=ItemUseOutcome.ALREADY_ACTIVE, item_name=item_name, target_id=target_id)

    logger.info(f"User {interaction_user_id} used {item_name} on {target_id}")
    return ItemUseResult(outcome=ItemUseOutcome.GRANTED, item_name=item_name, role_id=role_id, target_id=target_id)


async def _grant_role(guild, target_member, result):
    """Grants the item's role to the target member, returns the message to send back"""
    role = guild.get_role(result.role_id)
    if role is None:
        logger.error(f"Role ID {result.role_id} not found in guild")
        return "Role not found."
    try:
        await target_member.add_roles(role)
        logger.info(f"Granted role {result.role_id} to {target_member.id} via {result.item_name}")
        return _format_item_use_message(result, target_member.mention)
    except discord.Forbidden:
        logger.error(f"Bot cannot add role {result.role_id} due to hierarchy/permissions")
        return "I don't have permissions to grant this role."


async def handle(interaction, item_name: str, target: discord.Member):
    await interaction.response.defer(thinking=True)
    logger.debug(f"Use item handle: {interaction.user.id} uses {item_name} on {target.id}")
    try:
        result = await logic(
            interaction_user_id=interaction.user.id,
            interaction_guild_id=interaction.guild_id,
            item_name=item_name,
            target_id=target.id,
        )
        if not result:
            return await interaction.followup.send("Error occurred")

        # on_author redirects the effect onto the invoking user
        target_member = interaction.user if result.target_id == interaction.user.id else target

        if result.outcome is ItemUseOutcome.GRANTED:
            return await interaction.followup.send(await _grant_role(interaction.guild, target_member, result))

        await interaction.followup.send(_format_item_use_message(result, target_member.mention))
    except Exception as e:
        await interaction.followup.send("Error occurred")
        logger.warning(f"Error occurred for {interaction.user}: {e}")
