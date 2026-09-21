import discord
from discord import app_commands

from helpers.logger_config import internal_logger as logger
from helpers.user_functions import check_new_user


ONBOARDING_MESSAGE = "Don't forget to check /help for information about commands"
# commands after which the onboarding hint makes no sense
NO_ONBOARDING = {"help"}
NEW_USER_KEY = "new_user"


class KaijiTree(app_commands.CommandTree):
    """Registers the author of every slash command before the command runs.

    Runs before the command's own defer(), so it shares Discord's 3-second
    window for the first response.
    """

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # autocomplete fires on every keystroke with its own Interaction:
        # registering there would hit the DB per letter and lose the onboarding flag
        if interaction.type is discord.InteractionType.autocomplete:
            return True
        try:
            interaction.extras[NEW_USER_KEY] = await check_new_user.ensure_user_registered(interaction.user.id)
        except Exception as e:
            # the tree routes only AppCommandError to on_error, anything else would
            # be lost in its task, so answer here and stop the command
            logger.error(f"Failed to register user {interaction.user.id}: {e}", exc_info=True)
            await interaction.response.send_message("Error occurred", ephemeral=True)
            return False
        return True


async def send_onboarding(interaction: discord.Interaction, command) -> None:
    """Greet a user the tree has just registered, once their command has finished."""
    if interaction.extras.get(NEW_USER_KEY) and command.name not in NO_ONBOARDING:
        await interaction.followup.send(ONBOARDING_MESSAGE)
