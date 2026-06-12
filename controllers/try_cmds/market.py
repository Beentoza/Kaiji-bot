import enum
import dataclasses
import math
import random

from database.db_functions import db_user, db_economy, db_logs, db_time
from database.uow import UnitOfWork
from helpers.time_handler import get_timestamp, MARKET_TIMER
from helpers.logger_config import internal_logger as logger
from helpers import timed_tasks
from helpers.user_functions.check_new_user import ensure_user_registered
from helpers.user_functions.check_ban import is_banned
import constants

MARKET_MULTIPLIERS = {
    constants.MARKET_ALL_IN_NUMBER: 1.0,
    constants.MARKET_75_PERCENTS_NUMBER: 0.75,
    constants.MARKET_50_PERCENTS_NUMBER: 0.50,
    constants.MARKET_25_PERCENTS_NUMBER: 0.25,
}

class MarketOutcome(enum.Enum):
    """A types of market outcome"""
    ERROR = "error"
    BANNED = "banned"
    NEGATIVE_AMOUNT = "negative_amount"
    TOO_LOW = "too_low"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    COOLDOWN = "cooldown"
    SAME_BALANCE = "same_balance"
    WON = "won"
    LOST = "lost"


@dataclasses.dataclass(frozen=True)
class MarketResult:
    """Logic function returning"""
    outcome: MarketOutcome
    amount: int = 0
    delta: int = 0
    end_value_dif: int = 0
    jackpot_cut: int = 0
    multiplier: float = 0.0
    cooldown_left: int = 0


def checking_for_prepared_options(amount, balance):
    """Checking if user chose on of the predicted answers"""
    if amount in MARKET_MULTIPLIERS.keys():
        amount = MARKET_MULTIPLIERS[amount]*balance
    return amount

def _user_checks(amount, balance, status, time_since_last):
    if is_banned(status):
        return MarketResult(outcome=MarketOutcome.BANNED)
    if amount < 0:
        return MarketResult(outcome=MarketOutcome.NEGATIVE_AMOUNT)
    if amount < 50:
        return MarketResult(outcome=MarketOutcome.TOO_LOW)
    if amount > balance:
        return MarketResult(outcome=MarketOutcome.INSUFFICIENT_FUNDS)

    if time_since_last < MARKET_TIMER:
        remaining_time = int((MARKET_TIMER - time_since_last) // 60)
        return MarketResult(outcome=MarketOutcome.COOLDOWN, cooldown_left=remaining_time)
    return None


def _random_multiplier(luck_factor):
    """Making multiplier"""
    max_market_luck = constants.MARKET_MULT1_MAX-constants.MARKET_MULT1_MIN
    market_luck = min(luck_factor * max_market_luck/2, max_market_luck)
    multiplier1 = random.uniform(constants.MARKET_MULT1_MIN + market_luck, constants.MARKET_MULT1_MAX)
    multiplier2 = random.uniform(constants.MARKET_MULT2_MIN + market_luck, constants.MARKET_MULT2_MAX)
    multiplier3 = random.uniform(constants.MARKET_MULT3_MIN + market_luck, constants.MARKET_MULT3_MAX)
    multiplier4 = random.uniform(constants.MARKET_MULT4_MIN + market_luck, constants.MARKET_MULT4_MAX)

    multiplier = multiplier1 * multiplier2 * multiplier3 * multiplier4
    return multiplier


def _calculate_market_payouts(amount, balance, multip):
    """Getting variables"""
    end_value = math.ceil(amount * multip)
    end_value_dif = int(end_value - amount)
    jackpot_cut = max(0, math.ceil(end_value_dif * 0.1))
    delta = end_value_dif - jackpot_cut
    new_balance = balance + delta

    return delta, end_value_dif, new_balance, jackpot_cut


def _format_market_message(result, mention):
    """From result making a message"""
    match result.outcome:
        case MarketOutcome.ERROR:
            return f"{mention} Error"
        case MarketOutcome.BANNED:
            return f"{mention} You're banned, duude"
        case MarketOutcome.NEGATIVE_AMOUNT:
            return f"{mention}, please deposit with a valid amount."
        case MarketOutcome.TOO_LOW:
            return f"{mention}, the minimum deposit for a market run is Đ50."
        case MarketOutcome.INSUFFICIENT_FUNDS:
            return f"{mention}, you don't have enough funds to deposit this amount"
        case MarketOutcome.COOLDOWN:
            return f"{mention}, the markets have not re-opened yet. The markets will open in {result.cooldown_left} minutes"
        case MarketOutcome.SAME_BALANCE:
            return "You got same amount, luck next time"
        case MarketOutcome.WON:
            jackpot_msg = ""
            if result.jackpot_cut >= 1:
                jackpot_msg = f' {mention} 10% of your winnings, valued at Đ{result.jackpot_cut}, has been added to the jackpot.'
            return f"{mention}, you've received Đ{result.end_value_dif + result.amount} (+{result.end_value_dif}) from your latest market run. {jackpot_msg}"
        case MarketOutcome.LOST:
            return f"{mention}, you've received Đ{int(result.amount + result.delta)} from your latest market run with an initial deposit of Đ{result.amount}. Better luck next time!"
    return None


async def logic(interaction_user_id, interaction_guild_id, amount: int = None):
    user_id = interaction_user_id

    async with UnitOfWork() as uow:

        data = await db_economy.get_timestamp_balance_status(session=uow.session, user_id=user_id, timestamp_column_name="market")
        if data is None:
            return MarketResult(outcome=MarketOutcome.ERROR)
        else:
            market_timestamp, balance, status, luck_factor = data
            time_since_last = get_timestamp() - market_timestamp


        amount = checking_for_prepared_options(amount, balance) # if player chose 75%, 50%, all-in and e.t.c
        check = _user_checks(amount, balance, status, time_since_last)
        if check:
            return check

        multip = _random_multiplier(luck_factor)
        delta, end_value_dif, new_balance, jackpot_cut = _calculate_market_payouts(amount, balance, multip)

        await db_time.set_market_time(session=uow.session, user_id=user_id, time=get_timestamp())
        await db_logs.log_try_event(
            session=uow.session,
            user_id=user_id, event_type="market", amount=amount, profit=delta,
            server_id=interaction_guild_id, multiplier=multip
        )

        if not delta:
            logger.info(f"User {user_id} got same balance")
            return MarketResult(outcome=MarketOutcome.SAME_BALANCE)


        await db_user.add_user_balance(session=uow.session,user_id=user_id, amount=delta)
        if end_value_dif * 0.1 >= 1:
            await db_economy.add_to_jackpot(session=uow.session, amount=jackpot_cut)

    await timed_tasks.add_balance_history(
        interaction_user_id, interaction_guild_id,
        'try_group', 'market', delta, new_balance
    ) # not in uow.session, because not sending information to database instantly

    if multip >= 1:
        logger.info(f"User {user_id} won {delta}")
        return MarketResult(outcome=MarketOutcome.WON, amount=amount, delta=delta, end_value_dif=end_value_dif, jackpot_cut=jackpot_cut, multiplier=multip)
    else:
        logger.info(f"User {user_id} lost {abs(delta)}")
        return MarketResult(outcome=MarketOutcome.LOST, amount=amount, delta=delta, multiplier=multip)


async def handle(interaction, amount, test_mode=False, test_data=None):
    """User getting multiplier from amount and some of the winnings going to jackpot or if user lost money disappearing"""
    await interaction.response.defer(thinking=True)
    logger.debug("Handler started work")
    await ensure_user_registered(interaction)
    try:
        result = await logic(
            interaction_user_id=interaction.user.id,
            interaction_guild_id=interaction.guild_id,
            amount=amount,
        )
        message = _format_market_message(result, interaction.user.mention)
        await interaction.followup.send(message)
    except Exception as e:
        await interaction.followup.send("Error occurred")
        logger.warning(f"Error occurred when tried to process market for {interaction.user} {e}")