import enum
import dataclasses
import datetime as dt
import random

from database.db_functions import db_user, db_economy, db_time
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from helpers.time_handler import get_timestamp, MONTH
from helpers.user_functions import check_new_user
from helpers.user_functions.check_ban import is_banned
from helpers import timed_tasks


MONTHLY_MULT_MIN = 0.5
MONTHLY_MULT_MAX = 3


class MonthlyOutcome(enum.Enum):
    BANNED = "banned"
    COOLDOWN = "cooldown"
    ROLLED = "rolled"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class MonthlyResult:
    outcome: MonthlyOutcome
    multiplier: float = 0.0
    new_balance: int = 0
    seconds_left: int = 0


def _format_monthly_message(result, mention):
    match result.outcome:
        case MonthlyOutcome.BANNED:
            return f"{mention} You're banned"
        case MonthlyOutcome.COOLDOWN:
            time = str(dt.timedelta(seconds=result.seconds_left))
            return f"{mention} You can roll the multiplier only once a month. You have {time} until your next monthly roll"
        case MonthlyOutcome.ROLLED:
            return f"{mention} You have rolled a monthly multiplier of {round(result.multiplier, 3)}. Your balance is now Đ{result.new_balance}."
    return f"{mention} Error occurred"


async def logic(interaction_user_id, interaction_guild_id):
    """User every month can use this commands to multiple his balance"""
    user_id = interaction_user_id

    async with UnitOfWork() as uow:
        data = await db_economy.get_timestamp_balance_status(session=uow.session, user_id=user_id, timestamp_column_name='monthly')
        if not data:
            return MonthlyResult(outcome=MonthlyOutcome.ERROR)
        monthly_timestamp, balance, status, luck_factor = data

        if is_banned(status):
            return MonthlyResult(outcome=MonthlyOutcome.BANNED)

        timestamp_now = get_timestamp()
        time_difference = abs(monthly_timestamp - timestamp_now)
        if monthly_timestamp != 0 and time_difference < MONTH:
            return MonthlyResult(outcome=MonthlyOutcome.COOLDOWN, seconds_left=MONTH - time_difference)

        monthly_multiplier = random.uniform(MONTHLY_MULT_MIN, MONTHLY_MULT_MAX)
        new_balance = await db_user.multiply_user_balance(session=uow.session, user_id=user_id, factor=monthly_multiplier)
        await db_time.set_monthly_time(session=uow.session, user_id=user_id, time=timestamp_now)

    await timed_tasks.add_balance_history(interaction_user_id, interaction_guild_id, 'check', 'monthly', new_balance - balance, new_balance)

    logger.info(f"User {user_id} rolled mult {round(monthly_multiplier, 3)}, new balance {new_balance}")
    return MonthlyResult(outcome=MonthlyOutcome.ROLLED, multiplier=monthly_multiplier, new_balance=new_balance)


async def handle(interaction):
    """User can roll a monthly multiplier, which is applied to balance"""
    await interaction.response.defer(thinking=True)
    logger.debug("Handler started work")
    await check_new_user.ensure_user_registered(interaction)
    try:
        result = await logic(interaction_user_id=interaction.user.id, interaction_guild_id=interaction.guild.id)
        message = _format_monthly_message(result, interaction.user.mention)
        await interaction.followup.send(message)
    except Exception as e:
        await interaction.followup.send("Error occurred")
        logger.warning(f"Error occurred when tried to process monthly for {interaction.user} {e}")
