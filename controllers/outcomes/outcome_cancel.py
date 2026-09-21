from database.db_functions import db_user, db_outcome_logic
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
import discord
from helpers.user_functions import check_new_user
from helpers.BetTypes import BetEndType
import constants

async def handle(interaction, outcome):
    """Command to end outcomes"""
    logger.debug(f"Bet closing handle started work for {interaction.user.id}: {outcome}")
    await interaction.response.defer(thinking=True)

    if not await check_new_user.is_user_registered(interaction.user.id): # if we didn't find ID in DB, we don't adding
        # him. Instead, just saying he can't use this command
        return await interaction.followup.send("Only authorized users can make bets")
    async with UnitOfWork() as uow:
        status_level = await db_user.get_user_status(uow.session, interaction.user.id)
    if status_level < constants.STATUS_REQUIRED_OUTCOME_COMMANDS: # if user status under authorizerd
        return await interaction.followup.send("Only authorized users can make bets")



    try:
        result = await db_outcome_logic.refund_bet(
            outcome_name=outcome,# name of outcome
            server_id=interaction.guild_id) # removing bet in DB,

        answers = {
            BetEndType.CANCELLED: f"{interaction.user.mention} cancelled outcome {outcome}",
            BetEndType.NO_PARTICIPANTS: f"{interaction.user.mention} cancelled outcome {outcome}",
            BetEndType.BET_NOT_FOUND: f"{interaction.user.mention} outcome with this name doesn't exist",
        }
        logger.info(f"Outcome **{outcome}** cancelled by {interaction.user.id}, status {result.outcome}")
        message_for_user = answers.get(result.outcome, f"{interaction.user.mention} unknown error happened")

        if result.outcome in (BetEndType.CANCELLED, BetEndType.NO_PARTICIPANTS):
            if result.channel_id is not None and result.message_id is not None:

                channel = interaction.client.get_channel(result.channel_id)
                message = await channel.fetch_message(result.message_id)
                if message.embeds:
                    logger.info(f"changing existent embed {outcome}")

                    embed = message.embeds[0]
                    if str(embed.color.value) != constants.OUTCOME_OPEN_BET_COLOR: # a closed outcome has an extra status field to strip
                        embed.remove_field(len(embed.fields) - 1)
                    embed.color = discord.Color.dark_gray()
                    embed.add_field(name='Status',
                                    value=f':no_entry_sign:  Bet was cancelled by {interaction.user.mention}')
                    await message.edit(embed=embed)

                else:
                    logger.info(f"{message} not embed")

        await interaction.followup.send(message_for_user)
    except Exception as e:
        await interaction.followup.send("Error occurred", ephemeral=True)
        logger.exception(f"Error occurred when tried to cancel outcome {outcome}: {e}")