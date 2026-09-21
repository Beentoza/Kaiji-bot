import discord
from database.db_functions import db_user, db_outcome
from database.uow import UnitOfWork
from discord import ui
from helpers.logger_config import internal_logger as logger
from helpers.BetTypes import BetCreateType, BetCreateResult
import time
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






def _format_create_message(result: BetCreateResult) -> str:
    """From result making a message. VALID and CREATED have none: the preview / the outcome itself is the answer"""
    match result.outcome:
        case BetCreateType.NO_RIGHTS:
            return "You can't create outcomes :("
        case BetCreateType.TOO_FEW_OPTIONS:
            return "You need to have at least 2 options, which separated with `;`"
        case BetCreateType.BAD_TIMER:
            return "Timer should be from 3 min to 24 hours"
        case BetCreateType.ALREADY_EXISTS:
            return "Outcome with same name exists already"
    return "Error occurred"


def _build_outcome_embed(theme, choices, end_timestamp, author) -> discord.Embed:
    """Public message everyone sees once the outcome is created"""
    embed = discord.Embed(title=theme, color=0x00ff00)
    for i, choice in enumerate(choices, start=1):
        num = numeral.get(i - 1, 'th')

        embed.add_field(
            name=f'{i}{num} choice : {choice}',
            value='\u200b',
            inline=False
        )

    embed.add_field(name=f'You can place bets before: <t:{end_timestamp}:f>\n ', value='\u200b', inline=False)
    embed.set_footer(text=f"Author of outcome: {author.display_name}",
                     icon_url=author.display_avatar.url)
    return embed


async def check_logic(user_id: int, guild_id: int, theme: str, choices: str, timer: int, meas: str) -> BetCreateResult:
    """Checks before the preview: rights, options, timer, same name"""
    choice_list = tuple(c.strip() for c in choices.split(';') if c.strip())  # changing yes;no to (yes, no)
    multiplier = 60 if meas == 'minute' else 3600  # in menu user can pick either minute or hours
    delta_seconds = timer * multiplier  # we can't work with minutes and hours, so transfering into seconds

    async with UnitOfWork() as uow:
        status = await db_user.get_user_status(uow.session, user_id)
        if status is None or status < constants.STATUS_REQUIRED_OUTCOME_COMMANDS:
            return BetCreateResult(outcome=BetCreateType.NO_RIGHTS)

        if len(choice_list) < 2:  # outcome should have ATLEAST 2 options
            logger.info(f"{user_id} had {choice_list} with only 1 option")
            return BetCreateResult(outcome=BetCreateType.TOO_FEW_OPTIONS)

        if not (180 <= delta_seconds <= 86400):  # we have a limit from 3 minutes to 24 hours
            logger.info(f"{user_id} tried to make {theme} with {delta_seconds}")
            return BetCreateResult(outcome=BetCreateType.BAD_TIMER)

        # a fast answer before the form; the unique constraint in add_new_bet is the guarantee
        if await db_outcome.get_bet_with_same_name(uow.session, theme, guild_id):
            logger.info(f"{user_id} tried to make {theme} which already exists")
            return BetCreateResult(outcome=BetCreateType.ALREADY_EXISTS)

    return BetCreateResult(outcome=BetCreateType.VALID, choices=choice_list,
                           end_timestamp=int(time.time() + delta_seconds))


async def create_logic(theme: str, choices: tuple, end_timestamp: int, message_id: int, channel_id: int,
                       guild_id: int, user_id: int) -> BetCreateResult:
    """Saving the outcome the user confirmed"""
    async with UnitOfWork() as uow:
        bet_id = await db_outcome.add_new_bet(uow.session, theme, choices, end_timestamp, message_id,
                                              channel_id, guild_id, user_id=user_id)
    if bet_id is None:  # the same theme was created on this server while the preview was open
        logger.info(f"{user_id} tried to make {theme} which already exists")
        return BetCreateResult(outcome=BetCreateType.ALREADY_EXISTS)

    logger.info(f"{user_id} created outcome {theme} with id {bet_id}")
    return BetCreateResult(outcome=BetCreateType.CREATED, bet_id=bet_id)


async def handle(interaction, preset, theme, choices, timer, meas):
    """
    User creating outcome handle
    """
    logger.debug("Bet creation handle started work")
    await interaction.response.defer(thinking=True, ephemeral=True)

    if preset == 2:
        theme = "Who will die first?"
        choices = "1;2;3;4;5;6;7;8"
    try:
        result = await check_logic(interaction.user.id, interaction.guild_id, theme, choices, timer, meas)
        if result.outcome is not BetCreateType.VALID:
            return await interaction.followup.send(_format_create_message(result), ephemeral=True)

        # making a test view for user, so before creating he can see
        # if everything what he did doesn't have mistake
        view = SettingsView(interaction, theme, result.choices, timer, meas, result.end_timestamp)
        await interaction.followup.send(view=view)
        logger.debug(f"Create view for user {interaction.user.id} successful")

    except Exception as e:
        await interaction.followup.send("Error occurred", ephemeral=True)
        logger.warning(f"Error occurred when tried to create bet {theme} {e}", exc_info=True)
        logger.debug("Bet creation handle finished with error")


async def sending_message(interaction: discord.Interaction, theme, choices, end_timestamp):
    """
    If user accepted with settings
    We're showing outcome to everyone and saving it.
    Message goes first: the bet row needs its id
    """
    embed = _build_outcome_embed(theme, choices, end_timestamp, interaction.user)
    msg = await interaction.followup.send(
        embed=embed,
        allowed_mentions=discord.AllowedMentions(roles=True),
        wait=True
    )
    logger.debug(f"Captured message ID: {msg.id}")
    try:
        result = await create_logic(theme, choices, end_timestamp, msg.id,
                                    interaction.channel_id, interaction.guild_id, interaction.user.id)
    except Exception as e:
        logger.warning(f"Error while tried add outcome {theme} into DB: {e}", exc_info=True)
        result = BetCreateResult(outcome=BetCreateType.ERROR)

    if result.outcome is not BetCreateType.CREATED:
        await msg.delete()
        await interaction.followup.send(_format_create_message(result), ephemeral=True)
