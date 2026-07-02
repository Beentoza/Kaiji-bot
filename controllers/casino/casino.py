import enum
import dataclasses
import random
import asyncio
import discord

from database.db_functions import db_items
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger
from helpers.user_functions import check_new_user
import constants


class CasinoOutcome(enum.Enum):
    """Possible results of a single casino spin."""
    WON = "won"
    LOST = "lost"
    ERROR = "error"


@dataclasses.dataclass(frozen=True)
class CasinoResult:
    """What logic() hands back to the handler to drive the animation and message."""
    outcome: CasinoOutcome
    symbols: list = dataclasses.field(default_factory=list)
    final_row: list = dataclasses.field(default_factory=list)
    item_name: str | None = None


def _decide_row(win_emojis: dict, symbols: list) -> tuple[list, str | None]:
    """Pick the row the reels land on and the item won (None on a loss).

    Win: three identical emojis, returns the item name.
    Loss: the reels spin independently, so the first two may or may not match on
        their own (a natural near miss). Only a full triple is disallowed, since
        the win/loss is already decided here — the symbols are just the reveal."""
    if random.random() < constants.CASINO_WIN_CHANCE:
        emoji = random.choice(symbols)
        return [emoji, emoji, emoji], win_emojis[emoji]

    while True:
        row = [random.choice(symbols) for _ in range(3)]
        if not row[0] == row[1] == row[2]:
            return row, None


async def logic(user_id: int) -> CasinoResult:
    """Decide the spin outcome and, on a win, grant the item — all in one UoW.

    The outcome is fully determined here; the handler's animation only reveals it."""
    async with UnitOfWork() as uow:
        win_emojis = await db_items.get_winning_items(uow.session)  # {emoji: item_name}
        symbols = list(win_emojis)

        # the reels need at least three distinct symbols to spin
        if len(symbols) < 3:
            logger.warning("Casino has fewer than 3 symbols configured")
            return CasinoResult(outcome=CasinoOutcome.ERROR)

        final_row, item_name = _decide_row(win_emojis, symbols)

        if item_name is not None:
            await db_items.add_item_to_user(uow.session, user_id, item_name)
            logger.info(f"User {user_id} won casino item {item_name}")
            outcome = CasinoOutcome.WON
        else:
            outcome = CasinoOutcome.LOST

    return CasinoResult(
        outcome=outcome,
        symbols=symbols,
        final_row=final_row,
        item_name=item_name,
    )


async def _play_slot_machine(message, symbols: list, final_row: list) -> discord.Embed:
    """Scroll the three reels and land the bolded middle line on final_row.
    Returns the final embed so the handler can recolor it for the result."""
    sep = '---'
    ticks_left   = random.randint(5, 8)
    ticks_middle = random.randint(7, 10)
    # if the first two reels land the same, drag the third out to build suspense;
    # otherwise there's nothing to win, so let it snap in right after the second
    if final_row[0] == final_row[1]:
        ticks_right = ticks_middle + random.randint(5, 8)
    else:
        ticks_right = ticks_middle + random.randint(1, 2)
    another_row  = random.sample(symbols, 3)

    tape = (
        [list(another_row)]
        + [[sep, sep, sep]]
        + [list(final_row)]
        + [[sep, sep, sep]]
        + [['', '', ''] for _ in range(40)]
    )

    for i in range(40):
        if i % 2 == 0:
            tape[i + 4][0] = random.choice(symbols) if ticks_left   * 2 > i else sep
            tape[i + 4][1] = random.choice(symbols) if ticks_middle * 2 > i else sep
            tape[i + 4][2] = random.choice(symbols) if ticks_right  * 2 > i else sep
        else:
            tape[i + 4] = [sep, sep, sep]

    def get_col(col_idx, ticks):
        idx = max(ticks, 0)
        return [tape[idx + offset][col_idx] for offset in range(4, -1, -1)]

    def col_to_str(col):
        return f"{col[0]}\n{col[1]}\n**{col[2]}**\n{col[3]}\n{col[4]}"

    embed = discord.Embed(color=discord.Color.orange())

    def build_embed(left, middle, right):
        if len(embed.fields) >= 3:
            for _ in range(3):
                embed.remove_field(0)
        embed.add_field(name='\u200b', value=col_to_str(left),   inline=True)
        embed.add_field(name='\u200b', value=col_to_str(middle), inline=True)
        embed.add_field(name='\u200b', value=col_to_str(right),  inline=True)

    max_ticks = max(ticks_left, ticks_middle, ticks_right) * 2
    for i in range(max_ticks + 1):
        build_embed(
            get_col(0, ticks_left   * 2 - i),
            get_col(1, ticks_middle * 2 - i),
            get_col(2, ticks_right  * 2 - i),
        )
        await message.edit(content='', embed=embed)
        await asyncio.sleep(0.3)

    return embed


async def handle(interaction):
    await interaction.response.defer(thinking=True)
    logger.debug("Casino handler started work")
    await check_new_user.ensure_user_registered(interaction)

    try:
        result = await logic(interaction.user.id)
    except Exception as e:
        logger.warning(f"Casino error for {interaction.user}: {e}")
        return await interaction.followup.send("Error occurred")

    if result.outcome is CasinoOutcome.ERROR:
        return await interaction.followup.send("Error occurred")

    message = await interaction.followup.send("Activating")
    embed = await _play_slot_machine(message, result.symbols, result.final_row)

    if result.outcome is CasinoOutcome.WON:
        embed.color = discord.Color.green()
        embed.description = 'Yippee'
        await message.edit(embed=embed)
        await interaction.followup.send(
            f"{interaction.user.mention} You've got {result.item_name}!"
        )
    else:
        embed.color = discord.Color.red()
        embed.description = 'noop noop'
        await message.edit(embed=embed)
