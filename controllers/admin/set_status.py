import enum
import dataclasses

from database.db_functions import db_admin
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from helpers.user_functions.status_names import give_role_name


class SetStatusOutcome(enum.Enum):
    NOT_ADMIN = "not_admin"
    USER_NOT_FOUND = "user_not_found"
    SUCCESS = "success"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class SetStatusResult:
    outcome: SetStatusOutcome
    status: int = 0


def _format_set_status_message(result, setter_mention, target_id):
    match result.outcome:
        case SetStatusOutcome.NOT_ADMIN:
            return "Only admins can call this command"
        case SetStatusOutcome.USER_NOT_FOUND:
            return "You can change status of users which already exists in DB"
        case SetStatusOutcome.SUCCESS:
            return f"{setter_mention} changed status <@{target_id}> to {give_role_name(result.status)}"
    return "Error occurred. Never use this bot again."


async def logic(setter_user_id, target_user_id, status: int):
    async with UnitOfWork() as uow:
        if not await db_admin.is_admin(uow.session, setter_user_id):
            return SetStatusResult(outcome=SetStatusOutcome.NOT_ADMIN)

        updated = await db_admin.set_target_status(uow.session, target_user_id, status)
        if not updated:
            return SetStatusResult(outcome=SetStatusOutcome.USER_NOT_FOUND)

    return SetStatusResult(outcome=SetStatusOutcome.SUCCESS, status=status)


async def handle(ctx, user_id: int, user_status: int):
    """Admin command to set user status"""
    logger.debug("Started work")
    try:
        result = await logic(setter_user_id=ctx.author.id, target_user_id=user_id, status=user_status)
        response = _format_set_status_message(result, ctx.author.mention, user_id)
        return await ctx.send(response)

    except Exception as e:
        logger.error(f"ERROR: {e}")
