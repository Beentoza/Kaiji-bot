import enum
import dataclasses
import random

from database.db_functions import db_user, db_economy, db_internal, db_logs
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from helpers.user_functions import check_new_user
from helpers.user_functions.check_ban import is_banned
import constants


LOWEST_DOUBLE_PROB = 1000
HIGHEST_DOUBLE_PROB = 2000


class DoubleOutcome(enum.Enum):
    """A types of double outcome"""
    BANNED = "banned"
    NEGATIVE_AMOUNT = "negative_amount"
    TOO_LOW = "too_low"
    TOO_HIGH = "too_high"
    DRAW = "draw"
    WON = "won"
    LOST = "lost"
    ERROR = 'error'


@dataclasses.dataclass(frozen=True)
class DoubleResult:
    """Logic function returning"""
    outcome: DoubleOutcome
    amount: int = 0
    delta: int = 0
    jackpot_cut: int = 0


def _resolve_double_outcome(double_prob: int, amount: int) -> tuple[None, None] | tuple[int, bool]:
    """Deciding win or lose from probability, returns delta and won flag"""
    prob_to_win = (HIGHEST_DOUBLE_PROB + LOWEST_DOUBLE_PROB)*0.5
    if double_prob < prob_to_win:
        delta = - amount
        won = False
    elif double_prob > prob_to_win:
        delta = int(amount * 0.95)
        won = True
    else:
        return None, None
    return delta, won


def _format_double_message(result, mention):
    """From result making a message"""
    match result.outcome:
        case DoubleOutcome.BANNED:
            return f"{mention} You're banned, duude"
        case DoubleOutcome.NEGATIVE_AMOUNT:
            return f"{mention} please deposit with a valid amount."
        case DoubleOutcome.TOO_LOW:
            return f"{mention} the minimum deposit for a double run is 20."
        case DoubleOutcome.TOO_HIGH:
            return f"{mention} the maximum bet for Double-Or-Nothing is 75% of your bank."
        case DoubleOutcome.DRAW:
            # Easter egg for users, which will get 0.1% chance
            return f"{mention} you didn't win or lose ????"
        case DoubleOutcome.WON:
            return f"{mention} you've won Đ{int(result.amount)}. 5% of your winnings, valued at Đ{int(result.jackpot_cut)}, has been added to the jackpot."
        case DoubleOutcome.LOST:
            return f"{mention} you've lost Đ{int(result.amount)}."
    return f"Error occurred"


async def logic(interaction_user_id, interaction_guild_id, amount: int):
    user_id = interaction_user_id

    async with UnitOfWork() as uow:
        data = await db_economy.get_balance_status_luckfactor(user_id, uow.session)
        if not data:
            return DoubleResult(outcome=DoubleOutcome.ERROR)
        balance, status, luck_factor = data

        if is_banned(status):
            return DoubleResult(outcome=DoubleOutcome.BANNED)

        # to play user need place atleast 20 and not more than 75% of his bank
        if amount < 0:
            return DoubleResult(outcome=DoubleOutcome.NEGATIVE_AMOUNT)
        if amount < 20:
            return DoubleResult(outcome=DoubleOutcome.TOO_LOW)
        if amount > 0.75 * balance:
            return DoubleResult(outcome=DoubleOutcome.TOO_HIGH)

        double_luck = min(luck_factor * int(LOWEST_DOUBLE_PROB*0.5), int(HIGHEST_DOUBLE_PROB*0.5))
        double_prob = random.randint(LOWEST_DOUBLE_PROB + int(double_luck), HIGHEST_DOUBLE_PROB)
        delta, won = _resolve_double_outcome(double_prob, amount)
        if delta is None:
            return DoubleResult(outcome=DoubleOutcome.DRAW)

        jackpot_cut = int(amount * 0.05)

        await db_logs.log_try_event(session=uow.session, user_id=user_id, event_type="double", amount=amount, profit=delta,
                                    server_id=interaction_guild_id)
        await db_user.add_user_balance(session=uow.session, user_id=user_id, amount=delta)
        await db_user.update_winstreak(session=uow.session, user_id=user_id, win=int(won))
        if won:
            await db_economy.add_to_jackpot(session=uow.session, amount=jackpot_cut)

    if won:
        return DoubleResult(outcome=DoubleOutcome.WON, amount=amount, delta=delta, jackpot_cut=jackpot_cut)
    return DoubleResult(outcome=DoubleOutcome.LOST, amount=amount, delta=delta)


async def handle(interaction, amount):
    await interaction.response.defer(thinking=True)
    logger.debug("Handler started work")
    await check_new_user.ensure_user_registered(interaction)
    try:
        result = await logic(interaction_user_id=interaction.user.id, interaction_guild_id=interaction.guild_id, amount=amount)
        if not result:
            return await interaction.followup.send("Error occurred")
        message = _format_double_message(result, interaction.user.mention)
        await interaction.followup.send(message)
    except Exception as e:
        await interaction.followup.send("Error occurred")
        logger.warning(f"Error occurred for {interaction.user}: {e}")