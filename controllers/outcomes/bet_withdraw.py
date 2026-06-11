from helpers.logger_config import internal_logger as logger
from database.db_functions import db_user, db_bet
from helpers.time_handler import get_timestamp
from helpers.user_functions import check_new_user


async def handle(interaction, outcome):
    try:
        logger.debug(f"Started work for user {interaction.user.id}, {outcome}")
        await interaction.response.defer(thinking=True)
        await check_new_user.ensure_user_registered(interaction)

        status = await db_user.get_user_status(interaction.user.id)

        logger.debug(f"Checking if user {interaction.user.id} banned")

        if status == 0:
            logger.debug(f"User {interaction.user.id} banned")
            return await interaction.followup.send("You're banned, mate")

        logger.debug(f"Checking if user {interaction.user.id} tried to use not valid amount")
        status = await db_bet.withdraw_bet_for_user(outcome, interaction.user.id, interaction.guild_id, get_timestamp())
        answers = {
            "not_existent_bet": f"{interaction.user.mention} Didn't found outcome or bet",
            "closed_bet": f"{interaction.user.mention} this outcome already closed",
            "success": f" {interaction.user.mention} You got your money from bet back",
            "error": f" {interaction.user.mention} Error happened while trying to withdraw bet"
        }
        msg = answers.get(status, "Unknown error")

        return await interaction.followup.send(msg)


    except Exception as e:
        logger.warning(f"Error occurred when tried to withdraw bet for {interaction.user}: {e}")
        await interaction.followup.send("Error occurred", ephemeral=True)
        return None