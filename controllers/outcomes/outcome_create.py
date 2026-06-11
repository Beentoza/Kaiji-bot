import discord
from database.db_functions import db_user, db_outcome
from discord import ui
from helpers.logger_config import internal_logger as logger
import time
from helpers.user_functions import check_new_user
import constants

numeral = {0: 'st', 1: 'nd', 2: 'rd'}

class SettingsView(ui.LayoutView):
    """"UI which player will show before create bet"""
    row = ui.ActionRow()

    def __init__(self, interaction, theme, choices, timer, meas, end_timestamp):
        self.theme = theme
        self.choices = choices
        self.timer = timer
        self.measure = meas
        self.interaction = interaction
        self.end_timestamp = end_timestamp
        super().__init__()

        self.is_notifications_silent = False
        container = ui.Container()
        header = ui.TextDisplay(f"# {theme}")
        container.add_item(header)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))

        for i in range(len(choices)):
            choice = choices[i]
            n = i + 1
            container.add_item(ui.TextDisplay(f"### {n}. {choice}"))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        container.add_item(ui.TextDisplay(f" Time {timer} {meas}"))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))
        self.add_item(container)

        self.remove_item(self.row)
        self.add_item(self.row)

    @row.button(label='Finish', style=discord.ButtonStyle.green)
    async def finish_button(self, interaction: discord.Interaction, button: ui.Button):
        """
        User accepted settings and outcome will create
        """
        await interaction.response.edit_message(view=self)
        await interaction.delete_original_response()
        await sending_message(self.interaction, self.theme, self.choices, self.end_timestamp)

    @row.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def finish_button1(self, interaction: discord.Interaction, button: ui.Button):
        """
        Outcome will be canceled
        """
        await interaction.response.edit_message(view=self)
        await interaction.delete_original_response()
        await interaction.followup.send(f"Starting of outcome canceled",ephemeral=True)






async def handle(interaction,preset, theme, choices, timer, meas):
    logger.debug("Bet creation handle started work")

    """
    User creating outcome handle
    """
    await interaction.response.defer(thinking=True, ephemeral=True)

    await check_new_user.ensure_user_registered(interaction) # adding new user

    status = await db_user.get_user_status(interaction.user.id)
    if status < constants.STATUS_REQUIRED_OUTCOME_COMMANDS:
        return await interaction.followup.send("You can't create outcomes :(")
    if preset == 1:
        pass
    if preset == 2:
        theme = "Who will die first?"
        choices = "1;2;3;4;5;6;7;8"
    try:
        choice_list = [c.strip() for c in choices.split(';') if c.strip()] # changing yes;no to [yes, no]

        if len(choice_list) < 2: # outcome should have ATLEAST 2 options
            logger.info(f"{interaction.user.id} had {choice_list} with only 1 option")
            return await interaction.followup.send("You need to have at"
                                                   " least 2 options, which separated with `;`", ephemeral=True)

        multiplier = 60 if meas == 'minute' else 3600 # in menu user can pick either minute or hours
        delta_seconds = timer * multiplier # we can't work with minutes and hours, so transfering into seconds
        if not (180 <= delta_seconds <= 86400):  # we have a limit from 3 minutes to 24 hours
            logger.info(f"{interaction.user.id} tried to make {theme} with {delta_seconds}")
            return await interaction.followup.send("Timer should be from 3 min to 24 hours")

        if await db_outcome.get_bet_with_same_name(theme, interaction.guild_id): # checking if bet with the
            # same name already exists
            logger.info(f"{interaction.user.id} tried to make {theme} which already exists")
            return await interaction.followup.send("Outcome with same name exists already")

        end_timestamp = int(time.time() + delta_seconds)
        view = SettingsView(interaction, theme, choice_list, timer, meas, end_timestamp)
        await interaction.followup.send(view=view)
        # making a test view for user, so before creating he can see
        # if everything what he did doesn't have mistake
        logger.debug(f"Create view for user {interaction.user.id} successful")


    except Exception as e:
        await interaction.followup.send("Error occurred", ephemeral=True)
        logger.warning(f"Error occurred when tried to create bet {theme} {e}")
        logger.debug("Bet creation handle finished with error")



async def sending_message(interaction: discord.Interaction, theme, choices, end_timestamp):
    """
    If user accepted with settings
    We're creating outcome and showing it to everyone
    """


    embedVar = discord.Embed(title=theme, color=0x00ff00)
    for i, choice in enumerate(choices, start=1):
        num = numeral.get(i - 1, 'th')

        embedVar.add_field(
            name=f'{i}{num} choice : {choice}',
            value='\u200b',
            inline=False
        )

    embedVar.add_field(name=f'You can place bets before: <t:{end_timestamp}:f>\n ', value='\u200b', inline=False)
    embedVar.set_footer(text=f"Author of outcome: {interaction.user.display_name}",
                        icon_url=interaction.user.display_avatar.url)
    msg = await interaction.followup.send(
        embed=embedVar,
        allowed_mentions=discord.AllowedMentions(roles=True),
        wait=True
    )
    logger.debug(f"Captured message ID: {msg.id}")
    try:
        await db_outcome.add_new_bet(theme, choices, end_timestamp, msg.id, interaction.channel_id, interaction.guild_id, user_id=interaction.user.id)
    except Exception as e:
        await msg.delete()
        logger.warning("Error while tried add outcome into DB", e)
        return await interaction.followup.send("Error")



