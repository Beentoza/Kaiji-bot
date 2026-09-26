"""Discord side of a finished bet: find its message and stamp a status on the embed."""
import discord
from helpers.logger_config import internal_logger as logger
import constants


async def fetch_bet_message(client, channel_id, message_id) -> discord.Message | None:
    """The bet's original message, or None if it has no location stored."""
    if channel_id is None or message_id is None:
        return None
    channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)
    return await channel.fetch_message(message_id)


async def set_bet_status(message: discord.Message, status_text: str) -> bool:
    """Grey out the bet embed and put status_text in its Status field. False if there's no embed."""
    if not message.embeds:
        logger.info(f"Message {message.id} has no embed to update")
        return False
    embed = message.embeds[0]
    if embed.color.value != constants.OUTCOME_OPEN_BET_COLOR:  # a closed outcome already has a Status field
        embed.remove_field(len(embed.fields) - 1)
    embed.color = discord.Color.dark_gray()
    embed.add_field(name='Status', value=status_text)
    await message.edit(embed=embed)
    return True
