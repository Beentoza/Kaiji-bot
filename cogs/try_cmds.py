import discord
from discord import app_commands

from config import data_dict, GUILDS
from helpers.logger_config import internal_logger as logger
from controllers.try_cmds import lottery as try_lottery
from controllers.try_cmds import market as try_market
from controllers.try_cmds import double as try_double
from helpers.auto_options import market_autocomplete


class TryCommands(app_commands.Group):
    """
    Try market/jackpot e.t.c
    """

    def __init__(self):
        super().__init__(name='try', description='use market/jackpot')
        logger.debug("TryCommands group initialized (empty)")

    @app_commands.command(
        **data_dict['try']['lottery']['metadata']
    )
    async def on_lottery(self, interaction: discord.Interaction):
        logger.debug(f"try lottery command called by {interaction.user}")
        await try_lottery.handle(interaction)

    @app_commands.command(
        **data_dict['try']['market']['metadata'])
    @app_commands.describe(**data_dict['try']['market']['description'])
    @app_commands.autocomplete(amount=market_autocomplete)
    async def on_market(self, interaction: discord.Interaction, amount: int):
        logger.debug(f"Try market command called by {interaction.user} for amount: {amount}")
        await try_market.handle(interaction, amount)

    @app_commands.command(
        **data_dict['try']['double_or_nothing']['metadata'])
    @app_commands.describe(**data_dict['try']['double_or_nothing']['description'])
    async def on_double_or_nothing(self, interaction: discord.Interaction, amount: int):
        logger.debug(f"Try double_or_nothing command called by {interaction.user} for amount: {amount}")
        await try_double.handle(interaction, amount)


async def setup(bot):
    bot.tree.add_command(TryCommands(), guilds=GUILDS)
