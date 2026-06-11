import enum
import dataclasses
import datetime as dt
import random

from database.db_functions import db_user, db_economy, db_time
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from helpers.time_handler import get_timestamp, WEEK
from helpers.user_functions import check_new_user
from helpers.user_functions.check_ban import is_banned
from helpers import timed_tasks


WEEKLY_MIN_AMOUNT = -50
WEEKLY_MAX_AMOUNT = 100


class WeeklyOutcome(enum.Enum):
    BANNED = "banned"
    COOLDOWN = "cooldown"
    WON = "won"
    LOST = "lost"


@dataclasses.dataclass(frozen=True)
class WeeklyResult:
    outcome: WeeklyOutcome
    delta: int = 0
    seconds_left: int = 0


def _format_weekly_message(result, mention):
    match result.outcome:
        case WeeklyOutcome.BANNED:
            return f"{mention} You're banned"
        case WeeklyOutcome.COOLDOWN:
            time_left = str(dt.timedelta(seconds=result.seconds_left))
            return f"{mention} You can receive your weekly allowance once a week. You have {time_left} until your next weekly allowance."
        case WeeklyOutcome.WON:
            return f"{mention} You have won Đ{result.delta}."
        case WeeklyOutcome.LOST:
            return f"{mention} You have lost Đ{abs(result.delta)}."
    return f"{mention} Error occurred"


async def logic(interaction_user_id, interaction_guild_id):
    user_id = interaction_user_id

    async with UnitOfWork() as uow:
        data = await db_economy.get_timestamp_balance_status(session=uow.session, user_id=user_id, timestamp_column_name='weekly')
        weekly_timestamp, balance, status, luck_factor = data

        if is_banned(status):
            return WeeklyResult(outcome=WeeklyOutcome.BANNED)

        timestamp_now = get_timestamp()
        time_difference = abs(weekly_timestamp - timestamp_now)
        if weekly_timestamp != 0 and time_difference < WEEK:
            return WeeklyResult(outcome=WeeklyOutcome.COOLDOWN, seconds_left=WEEK - time_difference)

        # giving user random number, capping a loss so balance can't go negative
        weekly_amount = random.randint(WEEKLY_MIN_AMOUNT, WEEKLY_MAX_AMOUNT)
        if weekly_amount < 0 and abs(weekly_amount) > balance:
            weekly_amount = -balance
            logger.debug(f"Adjusting loss for user {user_id}")

        await db_user.add_user_balance(session=uow.session, user_id=user_id, amount=weekly_amount)
        await db_time.set_weekly_time(session=uow.session, user_id=user_id, time=timestamp_now)

    new_balance = balance + weekly_amount
    await timed_tasks.add_balance_history(interaction_user_id, interaction_guild_id, 'check', 'weekly', weekly_amount, new_balance)

    action = "won" if weekly_amount >= 0 else "lost"
    logger.info(f"Weekly result: user {user_id} {action} {abs(weekly_amount)}")

    if weekly_amount >= 0:
        return WeeklyResult(outcome=WeeklyOutcome.WON, delta=weekly_amount)
    return WeeklyResult(outcome=WeeklyOutcome.LOST, delta=weekly_amount)


async def handle(interaction):
    """User can receive random allowance weekly"""
    await interaction.response.defer(thinking=True)
    logger.debug("Handler started work")
    await check_new_user.ensure_user_registered(interaction)
    try:
        result = await logic(interaction_user_id=interaction.user.id, interaction_guild_id=interaction.guild.id)
        message = _format_weekly_message(result, interaction.user.mention)
        await interaction.followup.send(message)
    except Exception as e:
        logger.warning(f"Error occurred when tried to process weekly for {interaction.user} {e}")
