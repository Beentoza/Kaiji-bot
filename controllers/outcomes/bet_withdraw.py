from helpers.logger_config import internal_logger as logger
from database.db_functions import db_bet
from database.uow import UnitOfWork
from helpers.time_handler import get_timestamp
from helpers.user_functions import check_ban
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


async def logic(user_id: int, guild_id: int, outcome_name: str, unit_of_work):
    try:
        async with unit_of_work as uow:
            # getting status, checking if user banned
            status = await uow.user.get_user_status(user_id)

            logger.debug(f"Checking if user {user_id} banned")

            if check_ban.is_banned(status):
                logger.debug(f"User {user_id} banned")
                return BetWithdrawResult(outcome=BetWithdrawType.BANNED)

            # withdrawing bet and returning status
            logger.debug(f"Withdrawing bet for {user_id}")
            withdraw_status = await uow.bets.withdraw_bet_for_user(outcome_name, user_id, guild_id, get_timestamp())
            await uow.commit()
        return withdraw_status
    except Exception as e:
        logger.exception(f"Failed to withdraw bet on {outcome_name} for {user_id}: {e}")
        return BetWithdrawResult(outcome=BetWithdrawType.ERROR)


async def handle(interaction, outcome):
    logger.debug(f"Started work for user {interaction.user.id}, {outcome}")
    await interaction.response.defer(thinking=True)

    result = await logic(interaction.user.id, interaction.guild_id, outcome, unit_of_work=UnitOfWork())
    message_for_user = _format_message(result, interaction.user.mention)
    return await interaction.followup.send(message_for_user, ephemeral=True)
