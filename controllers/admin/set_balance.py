import enum
import dataclasses

from database.db_functions import db_admin
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from helpers import timed_tasks


class SetBalanceOutcome(enum.Enum):
    NOT_ADMIN = "not_admin"
    USER_NOT_FOUND = "user_not_found"
    ADDED = "added"
    SET = "set"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class SetBalanceResult:
    outcome: SetBalanceOutcome
    amount: int = 0
    new_balance: int = 0


def _format_set_balance_message(result, setter_mention, target_id):
    match result.outcome:
        case SetBalanceOutcome.NOT_ADMIN:
            return "Only admins can call this command"
        case SetBalanceOutcome.USER_NOT_FOUND:
            return "You can change status of users which already exists in DB"
        case SetBalanceOutcome.ADDED:
            return f"{setter_mention} added {result.amount} to <@{target_id}> balance"
        case SetBalanceOutcome.SET:
            return f"{setter_mention} changed balance <@{target_id}> to {result.amount}"
    return "Error occurred. Never use this bot again."


async def logic(setter_user_id, target_user_id, amount: int, add: bool):
    async with UnitOfWork() as uow:
        if not await db_admin.is_admin(uow.session, setter_user_id):
            return SetBalanceResult(outcome=SetBalanceOutcome.NOT_ADMIN)

        if add:
            new_balance = await db_admin.add_target_balance(uow.session, target_user_id, amount)
        else:
            new_balance = await db_admin.set_target_balance(uow.session, target_user_id, amount)

        if new_balance is None:
            return SetBalanceResult(outcome=SetBalanceOutcome.USER_NOT_FOUND)

    outcome = SetBalanceOutcome.ADDED if add else SetBalanceOutcome.SET
    return SetBalanceResult(outcome=outcome, amount=amount, new_balance=new_balance)


async def handle(ctx, user_id: int, set_balance: int, flag):
    """Admin command to set/add user balance"""
    logger.debug("Started work")
    try:
        add = bool(flag)
        result = await logic(setter_user_id=ctx.author.id, target_user_id=user_id, amount=set_balance, add=add)

        if result.outcome in (SetBalanceOutcome.ADDED, SetBalanceOutcome.SET):
            command = 'add_balance' if add else 'set_balance'
            await timed_tasks.add_balance_history(user_id, ctx.guild.id, 'admin', command, set_balance, result.new_balance)

        response = _format_set_balance_message(result, ctx.author.mention, user_id)
        return await ctx.send(response)

    except Exception as e:
        logger.error(f"ERROR: {e}")
