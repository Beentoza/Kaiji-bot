import enum
import dataclasses

from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger


class BankOutcome(enum.Enum):
    SUCCESS = "success"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class BankResult:
    outcome: BankOutcome
    jackpot: int = 0


async def logic(unit_of_work):
    try:
        async with unit_of_work as uow:
            jackpot_amount = await uow.economy.get_jackpot_info()
            await uow.commit()
        return BankResult(outcome=BankOutcome.SUCCESS, jackpot=int(jackpot_amount))
    except Exception as e:
        logger.exception(f"Failed to get jackpot: {e}")
        return BankResult(outcome=BankOutcome.ERROR)


def _format_bank_message(result):
    match result.outcome:
        case BankOutcome.SUCCESS:
            return f"In bank right now Đ{result.jackpot}"
        case BankOutcome.ERROR:
            return "Error occurred"
    return "Error occurred"


async def handle(interaction):
    """Handler sending info about amount Đ in bank (jackpot)"""
    await interaction.response.defer(thinking=True)
    logger.debug("Handler started work")
    result = await logic(unit_of_work=UnitOfWork())
    message = _format_bank_message(result)
    await interaction.followup.send(message)
    logger.info(f"Handler worked for {interaction.user.id}")
