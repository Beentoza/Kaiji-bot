import discord
from discord import ui, ButtonStyle, Interaction
from helpers.logger_config import internal_logger as logger
from discord import AllowedMentions
import time
from database.uow import UnitOfWork

class BetsLayoutView(ui.LayoutView):
    def __init__(self, bets_mapping: dict, initial_index: int = 0, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.bets = bets_mapping
        self.ids = list(bets_mapping.keys())
        self.index = initial_index
        self.main_container = ui.Container()


        self.action_row = ui.ActionRow()


        self.btn_back = ui.Button(label="◀", style=ButtonStyle.secondary)
        self.btn_page = ui.Button(label=f"{self.index+1}/{len(self.ids)}", style=ButtonStyle.gray, disabled=True)
        self.btn_forward = ui.Button(label="▶", style=ButtonStyle.secondary)


        async def back_cb(interaction: Interaction):
            if self.index > 0:
                self.index -= 1
                self._rebuild_container()

            await interaction.response.edit_message(view=self)

        async def forward_cb(interaction: Interaction):
            if self.index < len(self.ids) - 1:
                self.index += 1
                self._rebuild_container()
            await interaction.response.edit_message(view=self)


        self.btn_back.callback = back_cb
        self.btn_forward.callback = forward_cb


        self.action_row.add_item(self.btn_back)
        self.action_row.add_item(self.btn_page)
        self.action_row.add_item(self.btn_forward)

        self._rebuild_container()
        self.add_item(self.main_container)

    def _rebuild_container(self):
        for child in list(self.main_container.children):
            self.main_container.remove_item(child)
        bet = self.bets[self.ids[self.index]]

        self.main_container.add_item(ui.TextDisplay(f"# {bet['title']}"))
        self.main_container.add_item(ui.TextDisplay(f"Closing <t:{bet['open_before']}:R>"))
        self.main_container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))

        # outcomes + users
        for outcome, data in bet["outcomes"].items():
            coeff = data.get("total_option_amount", 0)

            self.main_container.add_item(ui.TextDisplay(f"## {outcome}"))
            self.main_container.add_item(ui.TextDisplay(f"### {coeff}%"))
            users = data.get("users", {})
            if not users:
                pass
            else:
                for uid, amount in users.items():
                    self.main_container.add_item(ui.TextDisplay(f"<@{uid}> : {amount}"))
            self.main_container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))


        self.btn_page.label = f"{self.index + 1}/{len(self.ids)}"
        self.btn_back.disabled = self.index <= 0
        self.btn_forward.disabled = self.index >= len(self.ids) - 1


        self.main_container.add_item(self.action_row)



def build_bets_mapping(active_bets, row_coeff, viewer_id) -> dict:
    """Turn bets and per-option sums into the dict BetsLayoutView shows. No DB here."""
    rows_by_bet = {}
    for r in row_coeff:
        rows_by_bet.setdefault(r.bet_id, []).append(r)

    bets_mapping = {}
    for bet in active_bets:
        bet_rows = rows_by_bet.get(bet.id, [])
        total_bet_pool = sum((r.sum_amount or 0) for r in bet_rows)
        opts = bet.options if isinstance(bet.options, list) else []

        bets_mapping[bet.id] = {
            "author": 635433154471002112,
            "title": bet.theme,
            "open_before": bet.end_timestamp,
            "total_amount": total_bet_pool,
            "outcomes": {name: {"users": {}} for name in opts}
        }

        for r in bet_rows:
            if 0 <= r.option < len(opts):
                target_name = opts[r.option]
                bets_mapping[bet.id]["outcomes"][target_name]["total_option_amount"] = r.sum_amount / total_bet_pool * 100

        for p in bet.participations:
            if 0 <= p.option < len(opts):
                outcome_name = opts[p.option]
                current_user_id = p.user.discord_id

                if current_user_id == viewer_id:
                    display_value = f"{p.money} 👈"
                else:
                    display_value = p.money

                bets_mapping[bet.id]["outcomes"][outcome_name]["users"][current_user_id] = display_value

    return bets_mapping


async def logic(user_id, guild_id, open: int, participation: int, unit_of_work) -> dict:
    async with unit_of_work as uow:
        active_bets, row_coeff = await uow.outcomes.get_outcomes(
            current_time=time.time(), user_id=user_id, open=open, participation=participation, server_id=guild_id
        )
    return build_bets_mapping(active_bets, row_coeff, user_id)


async def handle(interaction: Interaction, open: int, participation: int, show: int):
    """Command to see existent outcomes
    open: user can choose open&closed&all
    participation: user can choose participated, not participated, all"""
    await interaction.response.defer(thinking=True, ephemeral=show)
    logger.debug("Handler started working")

    try:
        res = await logic(user_id=interaction.user.id, guild_id=interaction.guild_id, open=open,
                          participation=participation, unit_of_work=UnitOfWork())
        if not res:
            return await interaction.followup.send("There's no open outcomes")
        view = BetsLayoutView(res, initial_index=0, timeout=None)


        await interaction.followup.send(content="", view=view, allowed_mentions=AllowedMentions.none())

        logger.debug("Handler finished successfully")
    except Exception as err:
        logger.warning(f"Error while showing bets for user {interaction.user.id}: {err}")
        try:
            await interaction.followup.send("Error occurred")
        except Exception:
            logger.exception("Failed to send followup error message")
