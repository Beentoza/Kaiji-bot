import enum
import dataclasses

from database.db_functions import db_user
from helpers.logger_config import internal_logger as logger
from helpers.user_functions import check_new_user
import constants


BALANCE_EMBED_COLOR = 0xFFD700


class BalanceOutcome(enum.Enum):
    KAIJI_BALANCE = "kaiji_balance"
    BOT_BALANCE = "bot_balance"
    NOT_REGISTERED = "not_registered"
    SUCCESS = "success"


@dataclasses.dataclass(frozen=True)
class BalanceResult:
    outcome: BalanceOutcome
    balance: int = 0


async def logic(target_user_id, is_bot, is_self):
    if is_bot:
        if target_user_id == constants.KAIJI_ID:
            logger.info("User asked kaiji balance")
            return BalanceResult(outcome=BalanceOutcome.KAIJI_BALANCE)
        logger.info(f"Bot balance check: {target_user_id}")
        return BalanceResult(outcome=BalanceOutcome.BOT_BALANCE)

    # checking someone else's balance: don't register them, just verify they exist
    if not is_self and not await check_new_user.is_user_registered(target_user_id):
        logger.info(f"Non-existent user check by third party: {target_user_id}")
        return BalanceResult(outcome=BalanceOutcome.NOT_REGISTERED)

    current_balance = await db_user.get_user_balance(target_user_id)
    if current_balance < 0:  # Easter egg if someone breaks it
        logger.warning(f"Negative balance detected for user {target_user_id}: {current_balance}")

    logger.info(f"Sent balance info for user {target_user_id}")
    return BalanceResult(outcome=BalanceOutcome.SUCCESS, balance=current_balance)


def _format_balance_message(result, embed, display_name, avatar_url):
    match result.outcome:
        case BalanceOutcome.KAIJI_BALANCE:
            return {"content": "More than you do :sunglasses: "}
        case BalanceOutcome.BOT_BALANCE:
            return {"content": "Bots aren't playing with Kaiji :("}
        case BalanceOutcome.NOT_REGISTERED:
            return {"content": "This user didn't use bot *yet*"}
        case BalanceOutcome.SUCCESS:
            embed_var = embed(color=BALANCE_EMBED_COLOR)
            embed_var.set_author(name=display_name, icon_url=avatar_url)
            embed_var.description = f"Balance is **Đ{result.balance}**"
            if result.balance < 0:
                embed_var.set_footer(text="How you got minus balance?? ")
            return {"embed": embed_var}
    return {"content": "Error occurred"}


async def handle(interaction, embed, user):
    """Send balance to user"""
    await interaction.response.defer(thinking=True)
    logger.debug("Handle started work")
    await check_new_user.ensure_user_registered(interaction)
    try:
        if user is None:  # no target picked -> show requester's own balance
            user = interaction.user

        result = await logic(target_user_id=user.id, is_bot=user.bot, is_self=user.id == interaction.user.id)
        payload = _format_balance_message(result, embed, user.display_name, user.display_avatar.url)
        await interaction.followup.send(**payload)
    except Exception as e:
        await interaction.followup.send("Error occurred")
        logger.warning(f"Error occurred when tried to ask DB about {user} {e}")
