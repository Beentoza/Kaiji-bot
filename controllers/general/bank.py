import enum
import dataclasses

from database.db_functions import db_economy
from helpers.logger_config import internal_logger as logger
from helpers.user_functions import check_new_user


class BankOutcome(enum.Enum):
    SUCCESS = "success"


@dataclasses.dataclass(frozen=True)
class BankResult:
    outcome: BankOutcome
    jackpot: int = 0


async def logic():
    jackpot_amount = await db_economy.get_jackpot_info()
    return BankResult(outcome=BankOutcome.SUCCESS, jackpot=int(jackpot_amount))


def _format_bank_message(result):
    match result.outcome:
        case BankOutcome.SUCCESS:
            return f"In bank right now Đ{result.jackpot}"
    return "Error occurred"


async def handle(interaction):
    """Handler sending info about amount Đ in bank (jackpot)"""
    await interaction.response.defer(thinking=True)
    logger.debug("Handler started work")
    await check_new_user.ensure_user_registered(interaction)
    result = await logic()
    message = _format_bank_message(result)
    await interaction.followup.send(message)
    logger.info(f"Handler worked for {interaction.user.id}")
