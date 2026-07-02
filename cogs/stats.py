import discord
from discord import app_commands

from config import data_dict, GUILDS
from helpers.logger_config import internal_logger as logger
from controllers.statistic import statistic, get_user_data
from controllers.general import leaderboard, bank


class StatsCommands(app_commands.Group):
    """
    Stats & info: game stats, leaderboard, jackpot, user data
    """

    def __init__(self):
        super().__init__(name="stats", description="Stats & info")
        logger.debug("StatsCommands group initialized")

    @app_commands.command(**data_dict['stats']['games']['metadata'])
    @app_commands.choices(show=[
        app_commands.Choice(name=key, value=value) for key, value in data_dict['stats']['games']['show'].items()
    ])
    async def on_statistic(self, interaction: discord.Interaction, show: int = 0):
        logger.debug(f"stats games command called by {interaction.user}")
        await statistic.handle(interaction, show)

    @app_commands.command(**data_dict['stats']['data']['metadata'])
    @app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
    async def on_data(self, interaction: discord.Interaction):
        logger.debug(f"stats data command called by {interaction.user}")
        await get_user_data.handle(interaction)

    @app_commands.command(**data_dict['stats']['leaderboard']['metadata'])
    async def on_leaderboard(self, interaction: discord.Interaction):
        logger.debug(f"stats leaderboard command called by {interaction.user}")
        await leaderboard.handle(interaction, discord.Embed)

    @app_commands.command(**data_dict['stats']['jackpot']['metadata'])
    async def on_jackpot(self, interaction: discord.Interaction):
        logger.debug(f"stats jackpot command called by {interaction.user}")
        await bank.handle(interaction)


async def setup(bot):
    bot.tree.add_command(StatsCommands(), guilds=GUILDS)
