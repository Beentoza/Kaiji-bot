import enum
import dataclasses

import constants
from database.db_functions import db_user
from helpers.logger_config import internal_logger as logger
from helpers.user_functions import check_new_user
from helpers.user_functions.status_names import give_role_name


class StatusOutcome(enum.Enum):
    KAIJI = "kaiji"
    OTHER_USER = "other_user"
    SUCCESS = "success"


@dataclasses.dataclass(frozen=True)
class StatusResult:
    outcome: StatusOutcome
    status_id: int = 0


async def logic(target_user_id, is_self):
    if target_user_id == constants.KAIJI_ID:
        return StatusResult(outcome=StatusOutcome.KAIJI)
    # asking about someone else: we don't register them, just say they're unknown
    if not is_self:
        return StatusResult(outcome=StatusOutcome.OTHER_USER)

    status = await db_user.get_user_status(target_user_id)
    return StatusResult(outcome=StatusOutcome.SUCCESS, status_id=status)


def _format_status_message(result, display_name):
    match result.outcome:
        case StatusOutcome.KAIJI:
            return "Higher than yours"
        case StatusOutcome.OTHER_USER:
            return "User didn't use bot *yet*"
        case StatusOutcome.SUCCESS:
            status_name = give_role_name(result.status_id)
            return f"user {display_name} has status **{status_name}**"
    return "Error occurred"


async def handle(interaction, member):
    await interaction.response.defer(thinking=True)
    logger.debug(f"Controller called for user {member.id}")
    await check_new_user.ensure_user_registered(interaction)
    result = await logic(target_user_id=member.id, is_self=member.id == interaction.user.id)
    message = _format_status_message(result, member.display_name)
    await interaction.followup.send(message)
    logger.info(f"{interaction.user.id} checked status for {member.id}")
