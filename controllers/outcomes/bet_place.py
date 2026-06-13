from helpers.logger_config import internal_logger as logger
from database.db_functions import db_user, db_bet
from helpers.user_functions import check_new_user
from database.uow import UnitOfWork
from helpers.user_functions.check_ban import is_banned
from helpers.BetTypes import BetType, BetResult



def _format_bet_message(result, mention):
    logger.warning(f"got {result}")
    match result.outcome: # preparing answer for user
        case BetType.SUCCESS:
            return f"{mention} Your bet on **{result.bet_name}** accepted. You placed Đ{int(result.amount)}, gl!"
        case BetType.TOO_HIGH:
            return f"{mention} you can't bet with more than you have, you anyway will lose."
        case BetType.CHOICE_NOT_FOUND:
            return f"{mention} didn't find this option, maybe because it doesn't exist?."
        case BetType.BET_NOT_FOUND:
            return f"{mention} didn't find a bet with this name."
        case BetType.ALREADY_BET:
            return (f"{mention} you can't place more than once on the same outcome\n"
                    f"You can use withdraw bet to change your option")
        case BetType.CLOSED:
            return f"{mention} oink, oink. I can't read and see than outcome is already closed"
        case BetType.NEGATIVE_AMOUNT:
            return f"{mention} PLEASE bet with a valid amount. You don't want to be banned, right?"
        case BetType.BANNED:
            return f"{mention} You're banned, duude"
        case BetType.ERROR:
            return f"Error occurred, stop breaking me!"
    return f"Error occurred, how did you even make it..."


async def logic(user_id: int, guild_id :int, amount: int, bet: str, choice: str) -> BetResult:
    async with UnitOfWork() as uow:
        # getting data, checking if it's valid
        data = await db_user.get_user_status_balance(session=uow.session, user_id=user_id)
        logger.debug("Data received", data)
        if not data:
            return BetResult(outcome=BetType.ERROR)


        # checking other variables if player chose them correctly
        status, balance = data

        if is_banned(status):
            logger.debug(f"User {user_id} is banned")
            return BetResult(outcome=BetType.BANNED)

        if amount < 1:
            logger.debug(f"Amount {amount} is less than 0 for user {user_id}")
            return BetResult(outcome=BetType.NEGATIVE_AMOUNT)

        if amount > balance:
            logger.debug(f"Amount {amount} is more than his balance {balance} for user {user_id}")
            return BetResult(outcome=BetType.TOO_HIGH)

        # placing bet in DB and getting result
        result =  await db_bet.process_place_bet(uow.session, user_id, bet, choice, amount, guild_id)
        logger.debug(f"Result received from DB_place_bet", result)
        return result


async def handle(interaction, bet: str, choice: str, amount: int):
    try:
        await interaction.response.defer(thinking=True)
        logger.debug(f"Started work for user {interaction.user.id}, {bet}, {choice}, {amount}")

        await check_new_user.ensure_user_registered(interaction)

        result = await logic(interaction.user.id, interaction.guild_id, amount, bet, choice)

        message_for_user = _format_bet_message(result, interaction.user.mention)
        logger.info(f"User {interaction.user.id} placed bet on {bet}, {choice}: {amount}")
        return await interaction.followup.send(message_for_user)
    except Exception as e:
        logger.warning(f"Unexpected error {e}")
        return await interaction.followup.send("Error happened")

