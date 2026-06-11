import enum
import dataclasses
import random

from database.db_functions import db_economy, db_logs
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from helpers.time_handler import get_timestamp
from helpers.user_functions.check_new_user import ensure_user_registered
from helpers.user_functions.check_ban import is_banned
from helpers import timed_tasks
import constants


class LotteryOutcome(enum.Enum):
    """A types of lottery outcome"""
    ERROR = "error"
    BANNED = "banned"
    TOO_POOR = "too_poor"
    COOLDOWN = "cooldown"
    LOST = "lost"
    WON = "won"


@dataclasses.dataclass(frozen=True)
class LotteryResult:
    """Logic function returning"""
    outcome: LotteryOutcome
    place: int = 0
    profit: int = 0
    jackpot_amount: int = 0
    cooldown_left: int = 0


def _check_lottery_place(lottery_place):
    """Function for checking, if user got some place or lost"""
    if not 985 <= lottery_place <= 1015:
        return 0
    if lottery_place in [*[i for i in range(985, 993)]] + [*[i for i in range(1008, 1016)]]:
        return 5
    if lottery_place in [993, 994, 995, 996, 1004, 1005, 1006, 1007]:
        return 4
    if lottery_place in [997, 998, 1002, 1003]:
        return 3
    if lottery_place in [999, 1001]:
        return 2
    if lottery_place in [1000]:
        return 1
    return None


def _calculate_lottery(luck_factor, jackpot_amount):
    """Translating nubmers from _check_lottery_place to profit, jackpot_change and timer"""
    lottery_luck = min(int(luck_factor * 900), 900)
    lottery_prob = random.randint(0 + lottery_luck, 2000 - lottery_luck)

    lottery_place = _check_lottery_place(lottery_prob)

    LOTTERY_PRIZES = {
        0: {"profit": -constants.LOTTERY_TICKET_PRICE, "jackpot_change": constants.LOTTERY_TICKET_PRICE, "timer": 0},
        1: {"profit": constants.LOTTERY_FIRST_PLACE + jackpot_amount, "jackpot_change": -jackpot_amount, "timer": 200},
        2: {"profit": constants.LOTTERY_SECOND_PLACE, "jackpot_change": constants.LOTTERY_TICKET_PRICE, "timer": 0},
        3: {"profit": constants.LOTTERY_THIRD_PLACE, "jackpot_change": constants.LOTTERY_TICKET_PRICE, "timer": 0},
        4: {"profit": constants.LOTTERY_FOURTH_PLACE, "jackpot_change": constants.LOTTERY_TICKET_PRICE, "timer": 0},
        5: {"profit": constants.LOTTERY_FIFTH_PLACE, "jackpot_change": constants.LOTTERY_TICKET_PRICE, "timer": 0},
    }

    prize = LOTTERY_PRIZES[lottery_place]
    return lottery_place, prize["profit"], prize["jackpot_change"], prize["timer"]


def _format_lottery_message(result, mention):
    """From result making a message"""
    match result.outcome:
        case LotteryOutcome.BANNED:
            return f"{mention} You're banned duude"
        case LotteryOutcome.TOO_POOR:
            return f'{mention}, you\'re so poor. For the sake of your wallet, you need more than Đ10 in your bank to play the lottery.'
        case LotteryOutcome.COOLDOWN:
            return f"{mention}, you have {result.cooldown_left} seconds until your next lottery ticket purchase"
        case LotteryOutcome.LOST:
            loss_messages = [
                f'{mention}, you\'re a loser. Đ{int(constants.LOTTERY_TICKET_PRICE)} has been added to the jackpot.',
                f'{mention}, you stupid idiot. Đ{int(constants.LOTTERY_TICKET_PRICE)} has been added to the jackpot.',
                f'{mention}, your pp too smol. Đ{int(constants.LOTTERY_TICKET_PRICE)} has been added to the jackpot.',
                f'{mention}, stop throwing your money away. Đ{int(constants.LOTTERY_TICKET_PRICE)} has been added to the jackpot.',
                f'{mention}, you never learn. Đ{int(constants.LOTTERY_TICKET_PRICE)} has been added to the jackpot.',
                f'{mention}, you bakayarou UwU. Đ{int(constants.LOTTERY_TICKET_PRICE)} has been added to the jackpot.',
            ]
            return random.choice(loss_messages)
        case LotteryOutcome.WON:
            author_line = f"\n<@{constants.KAIJI_OWNER_ID}> look at this pro gambler!" if constants.KAIJI_OWNER_ID else ""
            win_messages = {
                1: f'{mention}, congratulations! You\'ve won the grand prize of Đ{int(constants.LOTTERY_FIRST_PLACE + constants.LOTTERY_TICKET_PRICE)} and the jackpot of Đ{int(result.jackpot_amount)}. The jackpot has been reset to Đ0.{author_line}',
                2: f'{mention}, congratulations! You\'ve won the second place prize of Đ{int(constants.LOTTERY_SECOND_PLACE + constants.LOTTERY_TICKET_PRICE)}. Đ{int(constants.LOTTERY_TICKET_PRICE)} has been added to the jackpot.',
                3: f'{mention}, congratulations! You\'ve won the third place prize of Đ{int(constants.LOTTERY_THIRD_PLACE + constants.LOTTERY_TICKET_PRICE)}. Đ{int(constants.LOTTERY_TICKET_PRICE)} has been added to the jackpot.',
                4: f'{mention}, congratulations! You\'ve won the fourth place prize of Đ{int(constants.LOTTERY_FOURTH_PLACE + constants.LOTTERY_TICKET_PRICE)}. Đ{int(constants.LOTTERY_TICKET_PRICE)} has been added to the jackpot.',
                5: f'{mention}, congratulations! You\'ve won the fifth place prize of Đ{int(constants.LOTTERY_FIFTH_PLACE + constants.LOTTERY_TICKET_PRICE)}. Đ{int(constants.LOTTERY_TICKET_PRICE)} has been added to the jackpot.',
            }
            return win_messages[result.place]
    return f"{mention} Error"


async def logic(interaction_user_id, interaction_guild_id):
    user_id = interaction_user_id

    async with UnitOfWork() as uow:
        data = await db_economy.get_lottery_info(session=uow.session, user_id=user_id)

        lottery_timestamp, balance, status, jackpot_amount, luck_factor = data
        time_since_last = get_timestamp() - lottery_timestamp

        if is_banned(status):
            return LotteryResult(outcome=LotteryOutcome.BANNED)
        if balance < 10 * constants.LOTTERY_TICKET_PRICE:
            return LotteryResult(outcome=LotteryOutcome.TOO_POOR)
        if time_since_last < constants.COOLDOWN_BETWEEN_TICKETS:
            return LotteryResult(outcome=LotteryOutcome.COOLDOWN, cooldown_left=constants.COOLDOWN_BETWEEN_TICKETS - time_since_last)

        lottery_place, profit, jackpot_change, timer = _calculate_lottery(luck_factor, jackpot_amount)

        await db_logs.log_try_event(
            session=uow.session,
            user_id=user_id, event_type='lottery',
            amount=constants.LOTTERY_TICKET_PRICE, profit=profit,
            server_id=interaction_guild_id
        )
        await db_economy.update_lottery_and_user(
            session=uow.session, user_id=user_id,
            user_money_change=profit, jackpot_change=jackpot_change, timer=timer
        )

    await timed_tasks.add_balance_history(
        interaction_user_id, interaction_guild_id,
        'try_group', 'lottery', profit, balance + profit
    )

    logger.info(f"User {user_id} got place {lottery_place}, profit {profit}")

    if lottery_place == 0:
        return LotteryResult(outcome=LotteryOutcome.LOST, profit=profit)
    return LotteryResult(outcome=LotteryOutcome.WON, place=lottery_place, profit=profit, jackpot_amount=jackpot_amount)


async def handle(interaction):
    """User paying 1 D every time to buy ticket and has changed to win jackpot or place of prizes"""
    await interaction.response.defer(thinking=True)
    logger.debug("Handler started work")
    await ensure_user_registered(interaction)
    try:
        result = await logic(
            interaction_user_id=interaction.user.id,
            interaction_guild_id=interaction.guild_id,
        )
        message = _format_lottery_message(result, interaction.user.mention)
        await interaction.followup.send(message)
    except Exception as e:
        await interaction.followup.send("Error occurred")
        logger.warning(f"Error occurred when tried to process Lottery for {interaction.user} {e}")