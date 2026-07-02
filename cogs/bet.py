import discord
from discord import app_commands

from config import data_dict, GUILDS
from helpers.logger_config import internal_logger as logger
from controllers.outcomes import bet_withdraw, bet_place
from helpers.auto_options import (dynamic_autocomplete, dynamic_autocomplete_open,
                                  sub_dynamic_autocomplete)


class BetCommands(app_commands.Group):
    """
    Commands for auth users or auth users. Can make/end/cancel bets
    """

    def __init__(self):
        super().__init__(name='bet', description='Place/Withdraw bets')
        logger.debug("BetCommands group initialized")

    @app_commands.command(
        **data_dict['bet']['place']['metadata'])
    @app_commands.describe(**data_dict['bet']['place']['description'])
    @app_commands.autocomplete(bet=dynamic_autocomplete_open, choice=sub_dynamic_autocomplete)
    async def on_bet_place(self, interaction: discord.Interaction, bet: str, choice: str, amount: int):
        logger.debug(f"bet place command called by {interaction.user} for bet: {bet}, amount: {amount}")
        await bet_place.handle(interaction, bet, choice, amount)

    # didn't make proper logic for this function yet
    @app_commands.command(
        **data_dict['bet']['withdraw']['metadata'])
    @app_commands.describe(**data_dict['bet']['withdraw']['description'])
    @app_commands.autocomplete(outcome=dynamic_autocomplete)
    async def on_bet_withdraw(self, interaction: discord.Interaction, outcome: str):
        logger.debug(f"bet withdraw command called by {interaction.user} for outcome: {outcome}")
        await bet_withdraw.handle(interaction, outcome)


async def setup(bot):
    bot.tree.add_command(BetCommands(), guilds=GUILDS)
