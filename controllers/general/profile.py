from database.db_functions import db_user
from helpers.logger_config import internal_logger as logger
import time
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import io
import discord
from discord import ui
from helpers.time_handler import get_timestamp
import datetime as dt

banned_balance = "```ansi\n[31mĐ ░▒▓[0m\n```"
statuses = {0:"```ansi\n[31m🔒 Banned[0m\n```", 1: "User", 2: "Gentlemen", 3: "addictive"}


async def handle(interaction):
    await interaction.response.defer(thinking=True)
    try:
        user_info_data = await db_user.get_overall_user_info(interaction.user.id)
        if user_info_data is None or not user_info_data[0]:
            return await interaction.followup.send("Nothing to show yet")

        lst = []
        first_embed = await first_page(interaction, user_info_data)

        balance_history_data, balance_before = await db_user.get_week_balance_history(interaction.user.id)
        second_embed, second_file = await second_page(interaction, balance_history_data, balance_before)

        lst.append((first_embed, None))
        if second_embed is not None:
            lst.append((second_embed, second_file))
        view = EmbedNavigator(pages=lst)
        return await interaction.followup.send(
            embed=first_embed,
            view=view
    )

    except Exception as e:
        logger.error(e)
        return await interaction.followup.send("Error occurred")





def rgb_color(balance):
    xp = [0, 5000, 10000, 15000]
    fp_r = [130, 255, 255, 0]
    fp_g = [0, 130, 255, 255]

    r = int(np.interp(balance, xp, fp_r))
    g = int(np.interp(balance, xp, fp_g))

    return r, g, 0

async def first_page(interaction, data):


    min_timestamp, balance, status, luck_factor = data
    balance_for_user = 'Đ' + f'**{str(balance)}**'

    time = str(dt.timedelta(seconds=(get_timestamp() - min_timestamp)))

    if status == 0:
        balance_for_user = banned_balance

    embedVar = discord.Embed(color=0xFFD700)
    embedVar.set_author(name=f'{interaction.user.display_name} profile')
    embedVar.set_thumbnail(url=interaction.user.display_avatar.url)
    embedVar.description = "Kaiji found some information about you"
    embedVar.add_field(name="Status", value=statuses[status], inline=True) # change pfp
    embedVar.add_field(name="Balance", value=f'{balance_for_user}', inline=True) # change color
    embedVar.add_field(name='‎ ', value=f"Addicted to gambling: **{time}**", inline=False)
    colors = rgb_color(balance)
    r, g, b = colors
    embedVar.colour = discord.Color.from_rgb(r,g,b)
    return embedVar

async def second_page(interaction, balance_history_data, balance_before):
    try:




        user_data = balance_history_data
        arr = np.array(user_data)
        balances = arr[:, 0]
        timestamps = arr[:, 1]

        start_time = time.time() - 604800
        end_time = time.time()

        bins = np.linspace(start_time, end_time, num=8)
        day_indices = np.digitize(timestamps, bins)



        chart_y = np.full((7,2), np.nan)

        for day in range(1, 8):
            indices = np.where(day_indices == day)[0]
            if indices.size > 0:

                last_game = int(balances[indices[-1]])
                if indices.size == 1:
                    middle_game = last_game
                else:

                    mid_idx = indices[len(indices) // 2]
                    middle_game = int(balances[mid_idx])

                chart_y[day - 1, 0] = float(middle_game)
                chart_y[day - 1, 1] = float(last_game)

        if np.isnan(chart_y[0, 0]) and balance_before is None: #
            return None, None

        for i in range(len(chart_y)):
            if np.isnan(chart_y[i, 0]): # checking if there's something or notr
                if i == 0: # if it's first day, getting data before
                    chart_y[i, 0], chart_y[i, 1] = balance_before, balance_before
                else:
                    chart_y[i, 0], chart_y[i, 1] = chart_y[i-1, 1], chart_y[i-1, 1] # else getting from previous day


        lst_x = []
        lst_y = []
        for i in range(len(chart_y)):
            val1_raw = chart_y[i, 0] if not np.isnan(chart_y[i, 0]) else 0
            val2_raw = chart_y[i, 1] if not np.isnan(chart_y[i, 1]) else 0

            val1, val2 = int(val1_raw), int(val2_raw)

            lst_x.append(i)
            lst_x.append(i + 0.5)
            lst_y.append(val1)
            lst_y.append(val2)



        fig, ax = plt.subplots(figsize=(10, 6))

        # making background clear
        fig.patch.set_alpha(0.0)
        ax.patch.set_alpha(0.0)

        # writing tittle
        blue_color = '#3b82f6'
        ax.set_xlabel('Date (Last 7 Days)', color=blue_color, labelpad=10)
        ax.set_ylabel('Balance Amount', color=blue_color, labelpad=10)

        # making green lines with points
        ax.plot(lst_x, lst_y, color='#00ff99', marker='o', linewidth=2, markersize=4)

        # Making blue axises
        for spine in ax.spines.values():
            spine.set_color(blue_color)

        # Color of numbers
        ax.tick_params(axis='both', colors=blue_color)

        # Making blue net
        ax.grid(True, linestyle='--', alpha=0.3, color=blue_color)


        # making date for every day
        ax.set_xticks(range(len(chart_y)))
        ax.set_xticklabels([datetime.fromtimestamp(b).strftime('%d.%m') for b in bins[1:]])

        # highlight the smallest and biggest value
        # find these points
        y_array = np.array(lst_y)
        max_val = np.max(y_array)
        min_val = np.min(y_array)

        # get indexes (if there's more than one)
        max_idx = np.where(y_array == max_val)[0][0]
        min_idx = np.where(y_array == min_val)[0][0]

        # max point
        ax.scatter(lst_x[max_idx], max_val, color='#ffd700', s=80, zorder=5, edgecolors='white', label='Max')

        # min point
        ax.scatter(lst_x[min_idx], min_val, color='#ff4500', s=80, zorder=5, edgecolors='white', label='Min')



        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', transparent=True, bbox_inches='tight', dpi=100)
        buffer.seek(0)

        plt.close(fig)
        file = discord.File(buffer, filename="chart.png")
        graphic_embed = discord.Embed(
            title="Balance history",
            color=0x3b82f6  # blue
        )
        graphic_embed.set_image(url="attachment://chart.png")
        return graphic_embed, file


    except Exception as e:
        logger.error(e)
        return None, None


class EmbedNavigator(ui.View):
    def __init__(self, pages: list, timeout: float = 180):
        """pages: list of tuples [(embed1, file1), (embed2, file2), ...]"""
        super().__init__(timeout=timeout)
        self.pages = pages
        self.index = 0
        self.update_buttons()

    def update_buttons(self):
        # central counter label
        self.btn_count.label = f"{self.index + 1} / {len(self.pages)}"
        # disable buttons at the edges
        self.btn_back.disabled = (self.index == 0)
        self.btn_forward.disabled = (self.index == len(self.pages) - 1)

    async def refresh_msg(self, interaction: discord.Interaction):
        # current page data; tuple may be (embed, file) or (embed,)
        page_data = self.pages[self.index]
        embed = page_data[0]
        file = page_data[1] if len(page_data) > 1 else None

        # rewind the file if it's a BytesIO
        if file and hasattr(file.fp, 'seek'):
            file.fp.seek(0)

        self.update_buttons()

        # build the attachments list; empty -> Discord just updates text/embed
        current_attachments = [file] if file else []

        await interaction.response.edit_message(
            embed=embed,
            attachments=current_attachments,
            view=self
        )

    @ui.button(label="◀", style=discord.ButtonStyle.primary)
    async def btn_back(self, interaction: discord.Interaction, button: ui.Button):
        if self.index > 0:
            self.index -= 1
            await self.refresh_msg(interaction)

    @ui.button(label="...", style=discord.ButtonStyle.gray, disabled=True)
    async def btn_count(self, interaction: discord.Interaction, button: ui.Button):
        pass

    @ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def btn_forward(self, interaction: discord.Interaction, button: ui.Button):
        if self.index < len(self.pages) - 1:
            self.index += 1
            await self.refresh_msg(interaction)