import enum
import dataclasses
import random

from database.db_functions import db_user, db_economy
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from helpers.time_handler import get_timestamp
from helpers.user_functions import check_new_user
from helpers.user_functions.check_ban import is_banned
from helpers import timed_tasks


PERSONAL_TIMER_MIN = 60
PERSONAL_TIMER_MAX = 180
GLOBAL_TIMER_MIN = 180
GLOBAL_TIMER_MAX = 300
CHANGE_MIN = 1
CHANGE_MAX = 3


class PickupChangeOutcome(enum.Enum):
    BANNED = "banned"
    PERSONAL_COOLDOWN = "personal_cooldown"
    GLOBAL_COOLDOWN = "global_cooldown"
    RECEIVED = "received"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class PickupChangeResult:
    outcome: PickupChangeOutcome
    amount: int = 0


def _format_pickupchange_message(result, mention):
    match result.outcome:
        case PickupChangeOutcome.BANNED:
            return f"{mention} You're banned"
        case PickupChangeOutcome.PERSONAL_COOLDOWN:
            return (f"{mention} you're too tired from the last time you looked for change."
                    f" Now you're tired again and need some rest.")
        case PickupChangeOutcome.GLOBAL_COOLDOWN:
            return (f"{mention} you couldn't find any change on the ground. Look again later,"
                    f" but make sure to grab it before anyone else.")
        case PickupChangeOutcome.RECEIVED:
            return f"{mention} You have received Đ{result.amount}."
    return f"{mention} Error occurred"


async def logic(interaction_user_id, interaction_guild_id):
    user_id = interaction_user_id

    async with UnitOfWork() as uow:
        data = await db_economy.get_pickup_change_info(session=uow.session, user_id=user_id)
        if data is None:
            return PickupChangeResult(outcome=PickupChangeOutcome.ERROR)

        if is_banned(data["status"]):
            return PickupChangeResult(outcome=PickupChangeOutcome.BANNED)

        timestamp_now = get_timestamp()

        # personal cooldown: not passed -> reset personal timer and bail
        if timestamp_now - data["user_timestamp"] < data["user_cooldown"]:
            user_timer = random.randint(PERSONAL_TIMER_MIN, PERSONAL_TIMER_MAX)
            await db_economy.update_personal_pickupchange_info(session=uow.session, user_id=user_id, timestamp=timestamp_now, cooldown=user_timer)
            return PickupChangeResult(outcome=PickupChangeOutcome.PERSONAL_COOLDOWN)

        # global cooldown (for everyone): not passed -> reset personal timer and bail
        if timestamp_now - data["global_timestamp"] < data["global_cooldown"]:
            user_timer = random.randint(PERSONAL_TIMER_MIN, PERSONAL_TIMER_MAX)
            await db_economy.update_personal_pickupchange_info(session=uow.session, user_id=user_id, timestamp=timestamp_now, cooldown=user_timer)
            return PickupChangeResult(outcome=PickupChangeOutcome.GLOBAL_COOLDOWN)

        user_timer = random.randint(PERSONAL_TIMER_MIN, PERSONAL_TIMER_MAX)
        global_timer = random.randint(GLOBAL_TIMER_MIN, GLOBAL_TIMER_MAX)
        change_amount = random.randint(CHANGE_MIN, CHANGE_MAX)
        balance = data["balance"]

        await db_user.add_user_balance(session=uow.session, user_id=user_id, amount=change_amount)
        await db_economy.update_personal_pickupchange_info(session=uow.session, user_id=user_id, timestamp=timestamp_now, cooldown=user_timer)
        await db_economy.update_global_pickupchange_info(session=uow.session, timestamp=timestamp_now, cooldown=global_timer)

    new_balance = balance + change_amount
    await timed_tasks.add_balance_history(interaction_user_id, interaction_guild_id, 'check', 'pickup_change', change_amount, new_balance)

    logger.info(f"Pickup Change completed for {user_id}, he got {change_amount}")
    return PickupChangeResult(outcome=PickupChangeOutcome.RECEIVED, amount=change_amount)


async def handle(interaction):
    """Can get a small amount of money once in a while"""
    await interaction.response.defer(thinking=True)
    logger.debug("Handler started work")
    await check_new_user.ensure_user_registered(interaction)
    try:
        result = await logic(interaction_user_id=interaction.user.id, interaction_guild_id=interaction.guild.id)
        message = _format_pickupchange_message(result, interaction.user.mention)
        await interaction.followup.send(message)
    except Exception as e:
        await interaction.followup.send("Error occurred")
        logger.warning(f"Error occurred when tried to process pickup change for {interaction.user} {e}")
