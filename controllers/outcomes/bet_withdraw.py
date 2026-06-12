from helpers.logger_config import internal_logger as logger
from database.db_functions import db_user, db_bet
from helpers.time_handler import get_timestamp
from helpers.user_functions import check_new_user, check_ban
from helpers.BetTypes import BetWithdrawType, BetWithdrawResult

def _format_message(result, mention):
    logger.debug(f"got {result}")
    match result.outcome:
        case BetWithdrawType.SUCCESS:
            return f"{mention} Your bet was successfully withdrawn, next time come with bigger balls"
        case BetWithdrawType.BET_NOT_FOUND:
            return f"{mention} didn't find a outcome or didn't find your bet, maybe you didn't even place it?"
        case BetWithdrawType.CLOSED:
            return f"{mention} oink, oink. I can't read and see than outcome is already closed"
        case BetWithdrawType.BANNED:
            return f"{mention} You're banned, duude. Next time be"
        case BetWithdrawType.ERROR:
            return f"Error occurred, stop breaking me!"
    return f"Error occurred, how did you even make it..."


async def logic(user_id: int, guild_id: int, outcome_name: str):
    # getting status, checking if user banned
    status = await db_user.get_user_status(user_id)

    logger.debug(f"Checking if user {user_id} banned")

    if check_ban.is_banned(status):
        logger.debug(f"User {user_id} banned")
        return BetWithdrawResult(outcome=BetWithdrawType.BANNED)

    # withdrawing bet and returning status
    logger.debug(f"Withdrawing bet for {user_id}")
    withdraw_status = await db_bet.withdraw_bet_for_user(outcome_name, user_id, guild_id, get_timestamp())
    return withdraw_status


async def handle(interaction, outcome):
    try:
        logger.debug(f"Started work for user {interaction.user.id}, {outcome}")
        await interaction.response.defer(thinking=True)
        await check_new_user.ensure_user_registered(interaction) # cheecking if user in DB

        result = await logic(interaction.user.id, interaction.guild_id, outcome)
        message_for_user = _format_message(result, interaction.user.mention)
        return await interaction.followup.send(message_for_user, ephemeral=True)


    except Exception as e:
        logger.warning(f"Error occurred when tried to withdraw bet for {interaction.user}: {e}")
        return await interaction.followup.send("Error occurred", ephemeral=True)
