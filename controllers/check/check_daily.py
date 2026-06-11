import enum
import dataclasses
import datetime as dt

from database.db_functions import db_user, db_economy, db_time
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from helpers.time_handler import get_timestamp, DAY
from helpers.user_functions import check_new_user
from helpers.user_functions.check_ban import is_banned
from helpers import timed_tasks


DAILY_ALLOWANCE = 20


class DailyOutcome(enum.Enum):
    BANNED = "banned"
    COOLDOWN = "cooldown"
    RECEIVED = "received"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class DailyResult:
    outcome: DailyOutcome
    amount: int = 0
    seconds_left: int = 0


def _format_daily_message(result, mention):
    match result.outcome:
        case DailyOutcome.BANNED:
            return f"{mention} You're banned"
        case DailyOutcome.COOLDOWN:
            time = str(dt.timedelta(seconds=result.seconds_left))
            return f"{mention} You can receive Đ{DAILY_ALLOWANCE} only once per day. You have {time} until your next daily allowance."
        case DailyOutcome.RECEIVED:
            return f"{mention} You have received Đ{result.amount}."
    return f"{mention} Error occurred"


async def logic(interaction_user_id, interaction_guild_id):
    user_id = interaction_user_id

    async with UnitOfWork() as uow:
        data = await db_economy.get_timestamp_balance_status(session=uow.session, user_id=user_id, timestamp_column_name='daily')
        if not data:
            return DailyResult(outcome=DailyOutcome.ERROR)
        daily_timestamp, balance, status, luck_factor = data

        if is_banned(status):
            return DailyResult(outcome=DailyOutcome.BANNED)

        timestamp_now = get_timestamp()
        time_difference = abs(daily_timestamp - timestamp_now)
        if daily_timestamp != 0 and time_difference < DAY:
            return DailyResult(outcome=DailyOutcome.COOLDOWN, seconds_left=DAY - time_difference)

        await db_user.add_user_balance(session=uow.session, user_id=user_id, amount=DAILY_ALLOWANCE)
        await db_time.set_daily_time(session=uow.session, user_id=user_id, time=timestamp_now)

    new_balance = balance + DAILY_ALLOWANCE
    await timed_tasks.add_balance_history(interaction_user_id, interaction_guild_id, 'check', 'daily', DAILY_ALLOWANCE, new_balance)

    logger.info(f"User {user_id} got Đ{DAILY_ALLOWANCE}")
    return DailyResult(outcome=DailyOutcome.RECEIVED, amount=DAILY_ALLOWANCE)


async def handle(interaction):
    """Per a day gives user some amount of money"""
    await interaction.response.defer(thinking=True)
    logger.debug("Handler started work")
    await check_new_user.ensure_user_registered(interaction)
    try:
        result = await logic(interaction_user_id=interaction.user.id, interaction_guild_id=interaction.guild.id)
        message = _format_daily_message(result, interaction.user.mention)
        await interaction.followup.send(message)
    except Exception as e:
        await interaction.followup.send("Error occurred")
        logger.warning(f"Error occurred when tried to process daily for {interaction.user} {e}")
