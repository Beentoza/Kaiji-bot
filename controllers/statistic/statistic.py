from __future__ import annotations

from database.db_functions import db
from discord import ui, Interaction, SelectOption
from helpers.logger_config import internal_logger as logger


def regroup_market_info(res):
    """Getting info about market"""
    if res['len'] != 0:
        msg = (f"Commands used: **{res['len']}** times\n"
               f"Average multiplier: **{res['avg_multiplier']:.3f}**\n")

        msg += f"Biggest throw: **{res['lose']}**\n" if res["lose"] < 0 else "Didn't lose yet (pro)\n"

        msg += f"Biggest W: **{res['win']}**\n" if res["win"] > 0 else "Didn't win yet (not pro)\n"

        msg += f"Total got from market: **{res['total_profit']}**"

        return 'Market', msg
    else:
        return 'Market', "There's nothing to see"

def regroup_double_info(res):
    """Getting info about double"""
    if res['len'] != 0:
        msg = f"Commands used: **{res['len']}** times\n"

        msg += f"Biggest throw: **{res['lose']}**\n" if res["lose"] < 0 else "Didn't lose yet (pro)\n"

        msg += f"Biggest W: **{res['win']}**\n" if res["win"] > 0 else "Didn't win yet (not pro)\n"

        msg += f"Total got from market: **{res['total_profit']}**"

        return 'Double or nothing', msg
    else:
        return 'Double or nothing', "There's nothing to see"

def regroup_lottery_info(res):
    """Getting info about lottery places"""
    if res['len'] != 0:
        msg = f"Commands used: **{res['len']}** times\n"

        msg += f"Got fifth place **{res['win_20']}** times\n" if res['win_20'] > 0 else ''
        msg += f"Got fourth place **{res['win_50']}** times\n" if res['win_50'] > 0 else ''
        msg += f"Got third place **{res['win_125']}** times\n" if res['win_125'] > 0 else ''
        msg += f"Got second place **{res['win_250']}** times\n" if res['win_250'] > 0 else ''
        msg += f"Got jackpot **{res['win_20']}** times\n" if res['win_jackpot'] > 0 else "Didn't got jackpot\n"

        msg += f"Biggest win from lottery **{res['win']}**\n" if res['win'] > 0 else ''
        msg += f"Profit from lottery **{res['total_profit']}**" if res['total_profit'] > 0 else ''


        return 'Lottery', msg


    else:
        return 'Lottery', "There's nothing to see"



SLASH = "/"




def _create_content_items(user_info):
    """
    Making UI display for group commands
    """
    items = [
        ui.TextDisplay(f"### Statistic about try commands"),
        ui.Separator()]


    for name, description in user_info:

        items.append(ui.TextDisplay(f'### {name}'))
        items.append(ui.TextDisplay(f'{description}'))
        items.append(ui.Separator())

    return items

class HelpGroupSelect(ui.Select):
    """Looking which group chosen and shows it to user"""

    def __init__(self, groups: list[str], selected_group: str):
        self.selected_group = selected_group
        options = []
        for group in groups:
            is_default = group == selected_group
            options.append(SelectOption(
                label=group.capitalize(),
                value=group,
                default=is_default
            ))

        super().__init__(
            placeholder=f"Selected: {selected_group.capitalize()}",
            options=options if options else [SelectOption(label="No groups available", value="none", default=True)]
        ) # making a text button (so player can see which option he chose)

    async def callback(self, interaction: Interaction):
        """If user choose new group"""
        selected_group = self.values[0]
        if selected_group == "none":
            return await interaction.response.defer()

        logger.debug(f"User {interaction.user} selected group: {selected_group}")

        self.view.update_content(selected_group) # updating view and sending it
        await interaction.response.edit_message(content="", view=self.view)


class HelpLayoutView(ui.LayoutView):
    """Main class, making help GUI when user writing /help without choosing any group"""

    def __init__(self, groups: list[str], initial_group: str):
        super().__init__(timeout=180)
        self.groups = groups
        self.current_group = initial_group

        self.main_container = ui.Container()

        self.select_row = ui.ActionRow()
        self.select = HelpGroupSelect(groups, initial_group)
        self.select_row.add_item(self.select)

        self.content_items: list[ui.Item] = []

        self._rebuild_container(initial_group)
        self.add_item(self.main_container)


    def _clear_all_items(self):
        """Clearing all content from container to rebuild"""
        for item in list(self.main_container.children):
            self.main_container.remove_item(item)
        self.content_items = []

    def _rebuild_container(self, group_name: str):
        """Building container"""
        self.content_items = _create_content_items(group_name)
        self.main_container.add_item(self.select_row)

        for item in self.content_items:
            self.main_container.add_item(item)


    def update_content(self, new_group: str):
        """Updating UI for user when he's changing group"""

        self.current_group = new_group
        self.select_row.remove_item(self.select)
        self.select = HelpGroupSelect(self.groups, new_group) # deleting previous choose from HelpGroupSelect and changing it
        self.select_row.add_item(self.select)

        self._clear_all_items()
        self._rebuild_container(new_group)

async def handle(interaction: Interaction, show: int = 0):
    logger.debug("Help handler started")
    await interaction.response.defer(thinking=True, ephemeral=show)

    try:
        lst = []
        res = await db.log_get_event(interaction.user.id)
        lst.append(regroup_market_info(res[0]))
        lst.append(regroup_double_info(res[1]))
        lst.append(regroup_lottery_info(res[2]))
        content_items = _create_content_items(lst)

        temp_view = ui.LayoutView()
        temp_container = ui.Container()
        for item in content_items:
            temp_container.add_item(item)
        temp_view.add_item(temp_container)

        await interaction.followup.send(content="", view=temp_view)
        logger.info(f"Finished successfully for {interaction.user.id}")

    except Exception as exc:
        await interaction.followup.send("Error occurred", ephemeral=True)
        logger.warning(f"Error while showing help: {exc}")
        logger.debug("Finished with error")