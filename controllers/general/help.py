from __future__ import annotations
from discord import ui, Interaction, SelectOption, Embed
from helpers.logger_config import internal_logger as logger
from helpers import work_with_parameters as work
from helpers.roles_and_rights import \
    roles_for_certain_roles

SLASH = "/"



def _create_content_items(group_name: str) -> list[ui.Item]:
    """
    Making UI display for group commands
    """
    items = [
        ui.TextDisplay(f"# Help for {group_name.capitalize()} Commands"),
        ui.Separator()] # making a label
    group_commands = work.get_commands_by_group(group_name, True, True)

    for cmd_name in group_commands:
        metadata = work.get_command_metadata(group_name, cmd_name)
        description = metadata.get('description', 'No description.')
        items.append(ui.TextDisplay(f"### {cmd_name}"))

        params = work.get_command_description(group_name, cmd_name)
        full_description = f"{description}\n"
        if params:
            full_description += "\n**Options:**"
            for opt, desc in params.items():
                full_description += f"\n`{opt}`: {desc}"

        items.append(ui.TextDisplay(full_description))
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

async def handle(interaction: Interaction, group: str | None = None, user_cmd: str | None = None, show: int = 0):
    logger.debug("Help handler started")
    await interaction.response.defer(thinking=True, ephemeral=show)

    try:



        if user_cmd is not None:
            if user_cmd == 'At first you have to choose group':
                logger.info(f"{interaction.user.id} choose {user_cmd} and {group}")
                return await interaction.followup.send("Choose group and command correctly")

            command_info = work.get_command_info(group, user_cmd)
            description = (command_info.get('metadata', {}).get('description') or
                           f"No detailed description available for {SLASH}{group} {user_cmd}.")

            params = command_info.get('description', {})
            param_text = ""

            if params:
                param_text = "\n\n**Options:**\n" + "\n".join(
                    f"`{opt}`: {desc}" for opt, desc in params.items()
                )

            embed = Embed(
                title=f"Help for: {SLASH}{group} {user_cmd}",
                description=description + param_text,
                color=0x00FF00
            )

            logger.info(f"Help handler finished successfully for {interaction.user.id}")
            return await interaction.followup.send(embed=embed)



        if group is None:
            roles = interaction.user.roles
            all_groups = work.get_list_of_groups()
            available_groups = roles_for_certain_roles(all_groups, roles, interaction.user.id)

            if not available_groups:
                return await interaction.followup.send("You have no access to any command groups.", ephemeral=True)

            initial_group = available_groups[0]

            view = HelpLayoutView(available_groups, initial_group)

            logger.info(f"Help handler finished successfully for {interaction.user.id}")
            return await interaction.followup.send(content="", view=view)




        if group is not None:
            content_items = _create_content_items(group)

            temp_view = ui.LayoutView()
            temp_container = ui.Container()
            for item in content_items:
                temp_container.add_item(item)
            temp_view.add_item(temp_container)

            await interaction.followup.send(content="", view=temp_view)
            logger.info(f"Help handler finished successfully for {interaction.user.id}")

    except Exception as exc:
        await interaction.followup.send("Error occurred", ephemeral=True)
        logger.warning(f"Error while showing help: {exc}")
        logger.debug("Help handler finished with error")