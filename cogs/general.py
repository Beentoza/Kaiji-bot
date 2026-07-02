import discord
from discord import app_commands

import constants
from config import data_dict
from helpers.logger_config import internal_logger as logger
from controllers.general import balance, profile, help, get_status
from controllers.outcomes import outcomes
from controllers.casino import casino
from helpers.auto_options import help_group_list, help_command_list


@app_commands.command(**data_dict['general']['help']['metadata'])
@app_commands.describe(**data_dict['general']['help']['description'])
@app_commands.autocomplete(group=help_group_list, command=help_command_list)
@app_commands.choices(show=[
    app_commands.Choice(name=key, value=value) for key, value in data_dict['general']['help']['show'].items()
])
async def on_help(interaction: discord.Interaction, group: str = None, command: str = None, show: int = 0):
    logger.debug(f"general help command called by {interaction.user}, group: {group}, command: {command}")
    await help.handle(interaction, group, command, show)


@app_commands.command(
    **data_dict['general']['balance']['metadata'])
@app_commands.describe(**data_dict['general']["balance"]["description"])
async def on_balance(interaction: discord.Interaction, user: discord.Member = None):
    logger.debug(f"balance command called by {interaction.user} for user: {user}")
    await balance.handle(interaction, discord.Embed, user)


@app_commands.command(**data_dict['general']['outcomes']['metadata'])
@app_commands.describe(**data_dict['general']["outcomes"]["description"])
@app_commands.choices(open=[
    app_commands.Choice(name=key, value=value) for key, value in data_dict['general']['outcomes']['open'].items()
])
@app_commands.choices(participation=[
    app_commands.Choice(name=key, value=value) for key, value in data_dict['general']['outcomes']['participation'].items()
])
@app_commands.choices(show=[
    app_commands.Choice(name=key, value=value) for key, value in data_dict['general']['outcomes']['show'].items()
])
async def on_outcomes(interaction: discord.Interaction, open: int = 2, participation: int = 2, show: int = 0):
    await outcomes.handle(interaction, open, participation, show)


@app_commands.command(**data_dict['general']['profile']['metadata'])
async def on_profile(interaction: discord.Interaction):
    await profile.handle(interaction)


@app_commands.command(**data_dict['casino']['casino']['metadata'])
@app_commands.checks.cooldown(1, constants.CASINO_COOLDOWN*60*60)
async def on_casino(interaction: discord.Interaction):
    await casino.handle(interaction)


@on_casino.error
async def on_casino_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        # intentional glitch text, hides real cooldown by design
        await interaction.response.send_message(
            f"Come back in **EWR3G**h **DXWDWDD**m!", ephemeral=True
        )


async def on_balance_app(interaction: discord.Interaction, member: discord.Member):
    logger.debug(f"balance command called by {interaction.user} for user: {member} via app")
    await balance.handle(interaction, discord.Embed, member)


async def on_status_app(interaction: discord.Interaction, member: discord.Member):
    logger.debug(f"get status command called by {interaction.user} for user: {member} via app")
    await get_status.handle(interaction, member)


balance_menu = app_commands.ContextMenu(name="View player balance", callback=on_balance_app)
status_menu = app_commands.ContextMenu(name="View player status", callback=on_status_app)


async def setup(bot):
    # top-level commands and context menus are registered GLOBALLY (as in the original main.py)
    bot.tree.add_command(on_help)
    bot.tree.add_command(on_balance)
    bot.tree.add_command(on_outcomes)
    bot.tree.add_command(on_profile)
    bot.tree.add_command(on_casino)
    bot.tree.add_command(balance_menu)
    bot.tree.add_command(status_menu)
