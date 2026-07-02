import sys
import asyncio

import discord
from discord.ext import commands

from config import TOKEN, run_migrations, GUILDS
from helpers.logger_config import internal_logger as logger
from controllers.items import add_effect
from helpers.timed_tasks import (check_open_bets_status, set_bot_reference,
                                 check_bets_liquidity_task, auto_flush_timer,
                                 add_chances_data_into_DB, check_expired_effects_task)
from database.db_functions import db_internal


if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

EXTENSIONS = (
    "cogs.outcome",
    "cogs.bet",
    "cogs.try_cmds",
    "cogs.check",
    "cogs.item",
    "cogs.stats",
    "cogs.general",
    "cogs.admin",
)


class KaijiBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="$", intents=intents)

    async def setup_hook(self):
        for ext in EXTENSIONS:
            await self.load_extension(ext)
            logger.debug(f"Loaded extension {ext}")


bot = KaijiBot()
set_bot_reference(bot)


# --- TEST: opens the add-effect layout. Remove once wired into a real cog. ---
@bot.tree.command(name="test_add_effect", description="TEST: open the add-effect menu", guilds=GUILDS)
async def test_add_effect(interaction: discord.Interaction):
    await add_effect.handle(interaction)


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
