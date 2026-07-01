import discord
from discord import app_commands

from config import data_dict, GUILDS
from helpers.logger_config import internal_logger as logger
from controllers.outcomes import outcome_create, outcome_cancel, outcome_end
from helpers.auto_options import (dynamic_autocomplete, dynamic_autocomplete_closed,
                                  sub_closed_dynamic_autocomplete)


class AuthCommands(app_commands.Group):
    """
    Commands for auth users. Can make/end/cancel bets
    """

    def __init__(self):
        super().__init__(name='outcome', description='Open/close/cancel outcomes')
        logger.debug("AuthCommands (outcome) group initialized")

    @app_commands.command(
        **data_dict['outcome']['create']['metadata'])
    @app_commands.describe(**data_dict['outcome']['create']['description'])
    @app_commands.choices(preset=[
        app_commands.Choice(name=key, value=value) for key, value in data_dict['outcome']['create']['preset'].items()
    ])
    @app_commands.choices(meas=[
        app_commands.Choice(name=key, value=value) for key, value in data_dict['outcome']['create']['meas'].items()
    ])
    @app_commands.describe(theme="Theme of the outcome", preset="Custom or preset",choices="Choices separated by ;", timer="Duration", meas="Unit of time")
    async def on_outcome_create(self, interaction: discord.Interaction, preset: int, theme: str = "Will survivors win?", choices: str = 'Yes;No', timer: int = 7,
                     meas: str = 'minute'):
        """
        Auth user creating outcome
        """
        logger.debug(f"outcome create command called by {interaction.user} with theme: {theme}")
        await outcome_create.handle(interaction, preset, theme, choices, timer, meas)

    @app_commands.command(
        **data_dict['outcome']['end']['metadata'])
    @app_commands.describe(
        outcome=data_dict['outcome']['end']['description']['outcome'],
        choice=data_dict['outcome']['end']['description']['choice']
    )
    @app_commands.autocomplete(outcome=dynamic_autocomplete_closed, choice=sub_closed_dynamic_autocomplete)
    async def on_outcome_end(self, interaction: discord.Interaction, outcome: str, choice: str):
        logger.debug(f"outcome end command called by {interaction.user} for outcome: {outcome}, choice: {choice}")
        await outcome_end.handle(interaction, discord.Embed, outcome, choice)


    @app_commands.command(
        **data_dict['outcome']['cancel']['metadata'])
    @app_commands.describe(
        outcome=data_dict['outcome']['cancel']['description']['outcome']
    )
    @app_commands.autocomplete(outcome=dynamic_autocomplete)
    async def on_outcome_cancel(self, interaction: discord.Interaction, outcome: str):
        logger.debug(f"outcome cancel command called by {interaction.user} for outcome: {outcome}")
        await outcome_cancel.handle(interaction, outcome)


async def setup(bot):
    bot.tree.add_command(AuthCommands(), guilds=GUILDS)
