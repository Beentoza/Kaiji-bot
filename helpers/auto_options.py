from discord import app_commands, Interaction

import constants
from helpers.logger_config import internal_logger as logger
from helpers import work_with_parameters
from helpers.roles_and_rights import roles_for_certain_roles
from database.db_functions import db_items, db_outcome


async def dynamic_autocomplete_open(interaction: Interaction, current: str):
    """Autocomplete for bet place command. User will see which bet open"""
    try:
        active_themes = await db_outcome.get_all_bet_themes(interaction.guild_id, 1)


        choices = [
            app_commands.Choice(name=theme, value=theme)
            for theme in active_themes
            if current.lower() in theme.lower()
        ]


        return choices[:25] # 25 Because it's discord limit

    except Exception as e:
        logger.error(f"Error in autocomplete: {e}")
        return []

async def dynamic_autocomplete(interaction: Interaction, current: str):
    """Using it for withdraw bet or outcome cancel (shows all closed bets)  """
    try:
        active_themes = await db_outcome.get_all_bet_themes(interaction.guild_id, 2)


        choices = [
            app_commands.Choice(name=theme, value=theme)
            for theme in active_themes
            if current.lower() in theme.lower()
        ]


        return choices[:25]

    except Exception as e:
        logger.error(f"Error in autocomplete: {e}")
        return []

async def dynamic_autocomplete_closed(interaction: Interaction, current: str):
    """Using it for withdraw bet or outcome cancel (shows all closed bets)  """
    try:
        active_themes = await db_outcome.get_all_bet_themes(interaction.guild_id, 0)


        choices = [
            app_commands.Choice(name=theme, value=theme)
            for theme in active_themes
            if current.lower() in theme.lower()
        ]


        return choices[:25]

    except Exception as e:
        logger.error(f"Error in autocomplete: {e}")
        return []

async def sub_closed_dynamic_autocomplete(interaction: Interaction, current: str):
    try:

        selected_theme = interaction.namespace.outcome

        if not selected_theme:
            return [app_commands.Choice(name="Choose outcome before!", value="none")]

        options = await db_outcome.get_bet_options_by_theme(selected_theme, interaction.guild_id)

        return [
            app_commands.Choice(name=name, value=name)
            for name in options
            if current.lower() in name.lower()
        ][:25]

    except Exception as e:
        logger.error(f"Error in sub_autocomplete: {e}")
        return [app_commands.Choice(name="Error loading", value="error")]

async def sub_dynamic_autocomplete(interaction: Interaction, current: str):
    try:

        selected_theme = interaction.namespace.bet

        if not selected_theme:
            return [app_commands.Choice(name="Choose outcome before!", value="none")]

        options = await db_outcome.get_bet_options_by_theme(selected_theme, interaction.guild_id)

        return [
            app_commands.Choice(name=name, value=name)
            for name in options
            if current.lower() in name.lower()
        ][:25]

    except Exception as e:
        logger.error(f"Error in sub_autocomplete: {e}")
        return [app_commands.Choice(name="Error loading", value="error")]


async def help_group_list(interaction: Interaction, current: str):
    logger.debug(f"help_group_list called by user {interaction.user.id}")

    try:
        roles = interaction.user.roles
        groups = work_with_parameters.get_list_of_groups()
        groups = roles_for_certain_roles(groups, roles, interaction.user.id)

        choices = [
            app_commands.Choice(name=group, value=group)
            for group in groups
        ]

        logger.debug(f"Returning {len(choices)} groups for user {interaction.user.id}")
        return choices

    except Exception as e:
        logger.warning(f"Error in help_group_list for user {interaction.user.id}: {e}")
        return []


async def help_command_list(interaction: Interaction, current: str):
    logger.debug(f"help_command_list called by user {interaction.user.id}")

    try:
        selected_choice = interaction.namespace.group

        if selected_choice is None:
            logger.debug(f"No group selected by user {interaction.user.id} but commands did, getting answer")
            commands = ['At first you have to choose group']
        else:
            logger.debug(f"User {interaction.user.id} selected group: '{selected_choice}'")
            commands = work_with_parameters.get_commands_by_group(selected_choice, True, True)

        choices = [
            app_commands.Choice(name=name, value=name)
            for name in commands
        ]

        logger.debug(f"Returning {len(choices)} commands for group '{selected_choice}'")
        return choices

    except Exception as e:
        logger.warning(f"Failed to get command list for user {interaction.user.id}: {e}")
        return [app_commands.Choice(name="Error loading commands", value="error")]


async def market_autocomplete(interaction: Interaction, current: str, ) -> list[app_commands.Choice[int]]:
    choices = [
        app_commands.Choice(name="All-in", value=constants.MARKET_ALL_IN_NUMBER),
        app_commands.Choice(name="75%", value=constants.MARKET_75_PERCENTS_NUMBER),
        app_commands.Choice(name='50%', value=constants.MARKET_50_PERCENTS_NUMBER),
        app_commands.Choice(name='25%', value=constants.MARKET_25_PERCENTS_NUMBER),
    ]


    return choices


async def items_autocomplete(interaction: Interaction, current: str):
    try:
        inventory = await db_items.get_user_inventory(interaction.user.id)

        choices = []
        for item in inventory:
            item_val = item.item_type.value

            # skip the admin item, it's for another command
            if item_val == "fake_admin":
                continue

            if current.lower() in item_val.lower():
                choices.append(
                    app_commands.Choice(
                        name=f"{item_val} ({item.item_count})",
                        value=item_val
                    )
                )
        return choices[:25]
    except Exception as e:
        logger.error(f"Autocomplete error: {e}")
        return []