import enum
import dataclasses

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
        case SetStatusOutcome.ERROR:
            return "Error occurred"
    return "Error occurred. Never use this bot again."


async def logic(setter_user_id, target_user_id, status: int, unit_of_work):
    try:
        async with unit_of_work as uow:
            if not await uow.admin.is_admin(setter_user_id):
                return SetStatusResult(outcome=SetStatusOutcome.NOT_ADMIN)

            updated = await uow.admin.set_target_status(target_user_id, status)
            if not updated:
                return SetStatusResult(outcome=SetStatusOutcome.USER_NOT_FOUND)
            await uow.commit()

        return SetStatusResult(outcome=SetStatusOutcome.SUCCESS, status=status)
    except Exception as e:
        logger.exception(f"{setter_user_id} failed to set status {status} for {target_user_id}: {e}")
        return SetStatusResult(outcome=SetStatusOutcome.ERROR)


async def handle(ctx, user_id: int, user_status: int):
    """Admin command to set user status"""
    logger.debug("Started work")
    result = await logic(setter_user_id=ctx.author.id, target_user_id=user_id, status=user_status, unit_of_work=UnitOfWork())
    response = _format_set_status_message(result, ctx.author.mention, user_id)
    return await ctx.send(response)
