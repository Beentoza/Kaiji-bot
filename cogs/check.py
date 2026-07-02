import discord
from discord import app_commands

from config import data_dict, GUILDS
from helpers.logger_config import internal_logger as logger
from controllers.check import check_monthly, check_weekly, check_pickupchange, check_daily


class CheckCommands(app_commands.Group):
    """
    /check daily, weekly, monthly
    """

    def __init__(self):
        super().__init__(
            name="check",
            description="Daily / weekly / monthly rewards"
        )
        logger.debug("CheckCommands group initialized")

    @app_commands.command(
        **data_dict['check']['daily']['metadata']
    )
    async def on_daily(self, interaction: discord.Interaction):
        logger.debug(f"check daily command called by {interaction.user}")
        await check_daily.handle(interaction)

    @app_commands.command(
        **data_dict['check']['weekly']['metadata']
    )
    async def on_weekly(self, interaction: discord.Interaction):
        logger.debug(f"check weekly command called by {interaction.user}")
        await check_weekly.handle(interaction)

    @app_commands.command(
        **data_dict['check']['monthly']['metadata']
    )
    async def on_monthly(self, interaction: discord.Interaction):
        logger.debug(f"check monthly command called by {interaction.user}")
        await check_monthly.handle(interaction)

    @app_commands.command(
        **data_dict['check']['pickupchange']['metadata']
    )
    async def on_pickupchange(self, interaction: discord.Interaction):
        logger.debug(f"check pickupchange command called by {interaction.user}")
        await check_pickupchange.handle(interaction)


async def setup(bot):
    bot.tree.add_command(CheckCommands(), guilds=GUILDS)
