import discord
from discord import app_commands

from config import GUILDS
from helpers.logger_config import internal_logger as logger
from controllers.items import item_use
from helpers.auto_options import self_items_autocomplete, others_items_autocomplete


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

    # self-items (on_author)
    @app_commands.command(name="flex", description="Did you know, that man can produce milk?")
    @app_commands.describe(item="Item to use on yourself")
    @app_commands.autocomplete(item=self_items_autocomplete)
    async def on_flex(self, interaction: discord.Interaction, item: str):
        await item_use.handle(interaction, item, target=interaction.user)

    # everything else: thrown at another user
    @app_commands.command(name="yeet", description="Throw an item at another user")
    @app_commands.describe(member="Target", item="Item to throw")
    @app_commands.autocomplete(item=others_items_autocomplete)
    async def on_yeet(self, interaction: discord.Interaction, member: discord.Member, item: str):
        await item_use.handle(interaction, item, target=member)


async def setup(bot):
    bot.tree.add_command(ItemCommands(), guilds=GUILDS)
