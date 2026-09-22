import enum
import dataclasses

from database.db_functions import db_other
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger


LEADERBOARD_EMBED_COLOR = 0x00ff00
CROWNS = [":crown:", ":first_place:", ":second_place:", ":third_place:", ":reminder_ribbon:"]


class LeaderboardOutcome(enum.Enum):
    SUCCESS = "success"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class LeaderboardResult:
    outcome: LeaderboardOutcome
    players: tuple = ()


async def logic():
    try:
        async with UnitOfWork() as uow:
            data = await db_other.get_leaderboard(uow.session)
        return LeaderboardResult(outcome=LeaderboardOutcome.SUCCESS, players=data)
    except Exception as e:
        logger.exception(f"Failed to get leaderboard: {e}")
        return LeaderboardResult(outcome=LeaderboardOutcome.ERROR)


def _format_leaderboard_message(result, embed):
    match result.outcome:
        case LeaderboardOutcome.SUCCESS:
            embed_var = embed(title='Richest players', color=LEADERBOARD_EMBED_COLOR)
            for i, (user_id, balance) in enumerate(result.players):
                crown = CROWNS[i] if i < len(CROWNS) else ""
                embed_var.add_field(name=f'{crown} ** {i + 1}**', value=f'<@{user_id}> - Đ{balance}', inline=False)
            return {"embed": embed_var}
        case LeaderboardOutcome.ERROR:
            return {"content": "Error occurred"}
    return {"content": "Error occurred"}


async def handle(interaction, embed):
    """Giving top 5 richest players"""
    await interaction.response.defer(thinking=True)
    logger.debug("Handle started work")
    result = await logic()
    payload = _format_leaderboard_message(result, embed)
    await interaction.followup.send(**payload)
    logger.info(f"Handler worked for {interaction.user.id}")
