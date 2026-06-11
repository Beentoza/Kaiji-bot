import os
import discord
import json

import constants
import helpers.timed_tasks
from helpers.logger_config import internal_logger as logger
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from controllers.outcomes import outcomes
from controllers.statistic import statistic
from controllers.try_cmds import lottery as try_lottery
from controllers.try_cmds import market as try_market
from controllers.try_cmds import double as try_double
from controllers.admin import set_balance, set_status
from controllers.statistic import get_user_data
from controllers.general import balance, bank, leaderboard, profile, help, get_status
from controllers.outcomes import outcome_create, outcome_cancel, outcome_end, bet_withdraw, bet_place
from controllers.check import check_monthly, check_weekly, check_pickupchange, check_daily
from controllers.items import item_use
from controllers.casino import casino
from database.db_functions import db_internal
from helpers.auto_options import (sub_dynamic_autocomplete, dynamic_autocomplete, dynamic_autocomplete_closed,
                                  sub_closed_dynamic_autocomplete, \
                                  help_group_list, help_command_list, dynamic_autocomplete_open, market_autocomplete,
                                  items_autocomplete)
from helpers.timed_tasks import (check_open_bets_status, set_bot_reference,
                                 check_bets_liquidity_task, auto_flush_timer, add_chances_data_into_DB, check_expired_effects_task)
import asyncio
import sys
from alembic.config import Config
from alembic import command



if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="$", intents=intents)


set_bot_reference(bot)

GUILD_IDS = [int(x) for x in os.getenv("GUILD_ID", "").split(",")]
GUILDS = [discord.Object(id=gid) for gid in GUILD_IDS]

with open('parameters.json', 'r') as file:
    data_dict = json.load(file)

def run_migrations():
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

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

"""Admin commands"""
@bot.command(name="set_balance")
async def set_balance_prefix(ctx, user: discord.Member, amount: int, flag: int):
    await set_balance.handle(ctx, user.id, amount, flag)

@bot.command(name="set_status")
async def set_status_prefix(ctx, user: discord.Member, role: int):
    await set_status.handle(ctx, user.id, role)

@bot.command(name="add_data")
@commands.is_owner()
async def add_logs_into_DB(ctx):
    await helpers.timed_tasks.adding_logs_into_DB_by_command()
    await ctx.send('Added')



@bot.tree.command(**data_dict['general']['help']['metadata'])
@app_commands.describe(**data_dict['general']['help']['description'])
@app_commands.autocomplete(group=help_group_list, command=help_command_list)
@app_commands.choices(show=[
    app_commands.Choice(name=key, value=value) for key, value in data_dict['general']['help']['show'].items()
])
async def on_help(interaction: discord.Interaction, group: str = None, command: str = None, show: int = 0):
    logger.debug(f"general help command called by {interaction.user}, group: {group}, command: {command}")
    await help.handle(interaction, group, command, show)

@bot.tree.command(
    **data_dict['general']['balance']['metadata'])
@app_commands.describe(**data_dict['general']["balance"]["description"])
async def on_balance(interaction: discord.Interaction, user: discord.Member = None):
    logger.debug(f"balance command called by {interaction.user} for user: {user}")
    await balance.handle(interaction, discord.Embed, user)

@bot.tree.context_menu(name="View player balance")
async def on_balance_app(interaction: discord.Interaction, member: discord.Member):
    logger.debug(f"balance command called by {interaction.user} for user: {member} via app")
    await balance.handle(interaction, discord.Embed, member)

@bot.tree.context_menu(name="View player status")
async def on_status_app(interaction: discord.Interaction, member: discord.Member):
    logger.debug(f"get status command called by {interaction.user} for user: {member} via app")
    await get_status.handle(interaction, member)

@bot.tree.command(**data_dict['general']['outcomes']['metadata'])
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

"""General commands"""
@bot.tree.command(name="statistic", description="see jackpot money amount")
@app_commands.choices(show=[
    app_commands.Choice(name=key, value=value) for key, value in data_dict['general']['outcomes']['show'].items()
])
async def on_statistic(interaction: discord.Interaction, show: int = 0):
    await statistic.handle(interaction, show)

@bot.tree.command(name="jackpot", description="see jackpot money amount")
async def on_bank(interaction: discord.Interaction):
    await bank.handle(interaction)

@bot.tree.command(name="leaderboard", description="see richest players")
async def on_leaderboard(interaction: discord.Interaction):
    await leaderboard.handle(interaction, discord.Embed)

@bot.tree.command(name="profile", description="Check info about yourself")
async def on_profile(interaction: discord.Interaction):
    await profile.handle(interaction)

@bot.tree.command(name="casino", description="check your luck or be retard")
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



@app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id) # send a timer to 24h
@bot.tree.command(name="data", description="Check version of bot")
async def on_data(interaction: discord.Interaction):
    await get_user_data.handle(interaction)


@bot.command()
@commands.is_owner()
async def sync_all(ctx):
    for guild_obj in GUILDS:
        bot.tree.copy_global_to(guild=guild_obj)
        synced = await bot.tree.sync(guild=guild_obj)
        logger.info(f"Synced {len(synced)} commands for guild {guild_obj.id}")
    await ctx.send("Done!")


class ItemCommands(app_commands.Group):
    """
    /check daily, weekly, monthly
    """

    def __init__(self):
        super().__init__(
            name="item",
            description="Item commands"
        )
        logger.debug("ItemCommands group initialized")

    # admin-only command
    @app_commands.command(name="fake_admin", description="Activate admin mode")
    async def on_fake_admin(self, interaction: discord.Interaction):
        # pass a hardcoded item name to the handler
        await item_use.handle(interaction, "fake_admin", target=interaction.user)

    # command for everything else
    @app_commands.command(name="use", description="Use item on user")
    @app_commands.describe(member="Target", item="Item")
    @app_commands.autocomplete(item=items_autocomplete)
    async def on_use_target(self, interaction: discord.Interaction, member: discord.Member, item: str):
        await item_use.handle(interaction, item, target=member)


for guild_obj in GUILDS:
    bot.tree.add_command(AuthCommands(), guild=guild_obj)
    bot.tree.add_command(BetCommands(), guild=guild_obj)
    bot.tree.add_command(TryCommands(), guild=guild_obj)
    bot.tree.add_command(CheckCommands(), guild=guild_obj)
    bot.tree.add_command(ItemCommands(), guild=guild_obj)
    # bot.tree.add_command(AdminCommands(), guild=guild_obj)


@bot.event
async def on_ready():
    logger.debug("on_ready event triggered")
    try:
        await db_internal.check_db_connections()
        if not check_open_bets_status.is_running():
            check_open_bets_status.start()

        await asyncio.sleep(5)

        if not check_bets_liquidity_task.is_running():
            check_bets_liquidity_task.start()
        if not check_expired_effects_task.is_running():
            check_expired_effects_task.start()

        logger.info(f"Bot {bot.user} is fully ready and operational")
        asyncio.create_task(auto_flush_timer())
        add_chances_data_into_DB.start()
    except Exception as e:
        logger.error(f"Error during bot launch/sync: {e}", exc_info=True)





try:
    run_migrations()
    bot.run(TOKEN)
except KeyboardInterrupt:
    pass