import discord
from discord.ext import commands

import helpers.timed_tasks
from config import GUILDS
from helpers.logger_config import internal_logger as logger
from controllers.admin import set_balance, set_status


class Admin(commands.Cog):
    """
    Prefix admin commands + tree sync (owner only).
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="set_balance")
    async def set_balance_prefix(self, ctx, user: discord.Member, amount: int, flag: int):
        await set_balance.handle(ctx, user.id, amount, flag)

    @commands.command(name="set_status")
    async def set_status_prefix(self, ctx, user: discord.Member, role: int):
        await set_status.handle(ctx, user.id, role)

    @commands.command(name="add_data")
    @commands.is_owner()
    async def add_logs_into_DB(self, ctx):
        await helpers.timed_tasks.adding_logs_into_DB_by_command()
        await ctx.send('Added')

    @commands.command()
    @commands.is_owner()
    async def sync_all(self, ctx):
        for guild_obj in GUILDS:
            self.bot.tree.copy_global_to(guild=guild_obj)
            synced = await self.bot.tree.sync(guild=guild_obj)
            logger.info(f"Synced {len(synced)} commands for guild {guild_obj.id}")
        await ctx.send("Done!")


async def setup(bot):
    await bot.add_cog(Admin(bot))
