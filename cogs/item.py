import discord
from discord import app_commands

from config import GUILDS
from helpers.logger_config import internal_logger as logger
from controllers.items import item_use
from helpers.auto_options import items_autocomplete


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


async def setup(bot):
    bot.tree.add_command(ItemCommands(), guilds=GUILDS)
