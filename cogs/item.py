import discord
from discord import app_commands

from config import GUILDS, data_dict
from helpers.logger_config import internal_logger as logger
from controllers.items import item_use, add_effect, change_effect, transfer
from helpers.auto_options import (
    self_items_autocomplete,
    others_items_autocomplete,
    owned_items_autocomplete,
    catalog_items_autocomplete,
)


class ItemCommands(app_commands.Group):
    """
    /item flex, yeet, send, add, change
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

    # hand one item over to another user, without using it
    @app_commands.command(name="send", description="Give one of your items to another user")
    @app_commands.describe(member="Who gets the item", item="Item to send")
    @app_commands.autocomplete(item=owned_items_autocomplete)
    async def on_send(self, interaction: discord.Interaction, member: discord.Member, item: str):
        await transfer.handle(interaction, item, target=member)

    # admin: create a new catalog item
    @app_commands.command(
        **data_dict['item']['add']['metadata'])
    async def on_add(self, interaction: discord.Interaction):
        logger.debug(f"item add command called by {interaction.user}")
        await add_effect.handle(interaction)

    # admin: edit an existing catalog item
    @app_commands.command(
        **data_dict['item']['change']['metadata'])
    @app_commands.describe(**data_dict['item']['change']['description'])
    @app_commands.autocomplete(item=catalog_items_autocomplete)
    async def on_change(self, interaction: discord.Interaction, item: str):
        logger.debug(f"item change command called by {interaction.user} for item: {item}")
        await change_effect.handle(interaction, item)


async def setup(bot):
    bot.tree.add_command(ItemCommands(), guilds=GUILDS)
