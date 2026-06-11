import enum
import dataclasses

from database.db_functions import db_other
from helpers.logger_config import internal_logger as logger


LEADERBOARD_EMBED_COLOR = 0x00ff00
CROWNS = [":crown:", ":first_place:", ":second_place:", ":third_place:", ":reminder_ribbon:"]


class LeaderboardOutcome(enum.Enum):
    SUCCESS = "success"


@dataclasses.dataclass(frozen=True)
class LeaderboardResult:
    outcome: LeaderboardOutcome
    players: tuple = ()


async def logic():
    data = await db_other.get_leaderboard()
    return LeaderboardResult(outcome=LeaderboardOutcome.SUCCESS, players=data)


def _format_leaderboard_message(result, embed):
    embed_var = embed(title='Richest players', color=LEADERBOARD_EMBED_COLOR)
    for i, (user_id, balance) in enumerate(result.players):
        crown = CROWNS[i] if i < len(CROWNS) else ""
        embed_var.add_field(name=f'{crown} ** {i + 1}**', value=f'<@{user_id}> - Đ{balance}', inline=False)
    return embed_var


async def handle(interaction, embed):
    """Giving top 5 richest players"""
    await interaction.response.defer(thinking=True)
    logger.debug("Handle started work")
    try:
        result = await logic()
        embed_var = _format_leaderboard_message(result, embed)
        await interaction.followup.send(embed=embed_var)
        logger.info(f"Handler worked for {interaction.user.id}")
    except Exception as e:
        logger.warning(f"Error happened for {interaction.user.id}: {e}")
