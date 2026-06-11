import random
import asyncio
import discord
from database.db_functions import db_items


async def spin_function(discord_message, content_message, list_of_emojies, time: float):
    await asyncio.sleep(time)

    content_message = content_message.split('\n', 1)[-1] + f"{random.choice(list_of_emojies)} {random.choice(list_of_emojies)} {random.choice(list_of_emojies)}\n"
    await discord_message.edit(content=content_message)
    content_message = content_message.split('\n', 1)[-1] + f"-------------\n"
    await discord_message.edit(content=content_message)
    return content_message

async def handle(interaction):
    await interaction.response.defer(thinking=True)

    sep = '---'
    symbols = await db_items.get_symbols()
    symbols.append(":skull:")

    # from DB instead of a hardcoded list

    ticks_left   = random.randint(5, 8)
    ticks_middle = random.randint(7, 10)
    ticks_right  = random.randint(10, 11)
    another_row = random.sample(symbols, 3)
    if random.random() < 0.1:
        # 10% win: three identical symbols
        winning_symbol = random.choice(symbols)
        final_row = [winning_symbol, winning_symbol, winning_symbol]
    else:
        # 90% loss: three different symbols
        final_row = random.sample(symbols, 3)


    tape = (
            [another_row]
            + [[sep, sep, sep]]
            + [final_row]
            + [[sep, sep, sep]]
            + [['', '', ''] for _ in range(40)]
    )

    for i in range(35):
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

    def build_embed(left, middle, right):
        if len(embed.fields) >= 3:
            for i in range(3):
                embed.remove_field(0)
        embed.add_field(name='\u200b', value=col_to_str(left),   inline=True)
        embed.add_field(name='\u200b', value=col_to_str(middle), inline=True)
        embed.add_field(name='\u200b', value=col_to_str(right),  inline=True)
        return embed

    message = await interaction.followup.send("Activating")

    max_ticks = max(ticks_left, ticks_middle, ticks_right) * 2
    embed = discord.Embed(color=discord.Color.orange())
    for i in range(max_ticks + 1):
        left   = get_col(0, ticks_left   * 2 - i)
        middle = get_col(1, ticks_middle * 2 - i)
        right  = get_col(2, ticks_right  * 2 - i)
        embed  = build_embed(left, middle, right)

        await message.edit(content='', embed=embed)
        await asyncio.sleep(0.3)

    winning_emojies = await db_items.get_winning_items()  # {emoji: ItemType}

    win_flag = left[2] == middle[2] == right[2] and right[2] in winning_emojies

    if win_flag:
        item_type = winning_emojies[left[2]]

        embed.color = discord.Color.green()
        embed.description = 'Yippee'
        await message.edit(embed=embed)
        await db_items.add_item_to_user(interaction.user.id, item_type)
        await interaction.followup.send(f"{interaction.user.mention} You've got {item_type.value}!")
    else:
        embed.color = discord.Color.red()
        embed.description = 'noop noop'
        await message.edit(embed=embed)
