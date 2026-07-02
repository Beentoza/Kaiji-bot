import enum
import discord
from discord import ui

from database.db_functions import db_admin, db_items
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger


class AddEffectOutcome(enum.Enum):
    """A types of add-effect outcome"""
    NOT_ADMIN = "not_admin"
    NO_NAME = "no_name"
    NAME_EXISTS = "name_exists"
    NO_EMOJI = "no_emoji"
    EMOJI_NOT_FOUND = "emoji_not_found"
    SUCCESS = "success"
    ERROR = "error"


def _format_add_effect_message(outcome, mention, item_name):
    """From outcome making a message"""
    match outcome:
        case AddEffectOutcome.NOT_ADMIN:
            return f"{mention} you don't have permission to do this."
        case AddEffectOutcome.NO_NAME:
            return f"{mention} the item needs a name."
        case AddEffectOutcome.NAME_EXISTS:
            return f"{mention} an item with name '{item_name}' already exists."
        case AddEffectOutcome.NO_EMOJI:
            return f"{mention} casino items require an emoji."
        case AddEffectOutcome.EMOJI_NOT_FOUND:
            return f"{mention} the emoji must be wrapped in colons, like :smile:."
        case AddEffectOutcome.SUCCESS:
            return f"{mention} item '{item_name}' has been added."
    return f"Error occurred"


async def _is_admin(user_id):
    async with UnitOfWork() as uow:
        return await db_admin.is_admin(uow.session, user_id)


async def _save(user_id, item_name, in_casino, role_id, emoji, on_author, duration):
    """Create the item. Returns an AddEffectOutcome."""
    async with UnitOfWork() as uow:
        if not await db_admin.is_admin(uow.session, user_id):
            return AddEffectOutcome.NOT_ADMIN

        if await db_items.item_name_exists(uow.session, item_name):
            return AddEffectOutcome.NAME_EXISTS

        # adding item into DB
        await db_items.add_item(
            session=uow.session,
            item_name=item_name,
            in_casino=in_casino,
            role=role_id,
            emoji=emoji,
            on_author=on_author,
            duration=duration,
        )

    logger.info(f"Admin {user_id} added item {item_name}")
    return AddEffectOutcome.SUCCESS


class EditFieldsModal(ui.Modal):
    """Everything the admin types/picks: name, emoji, role and duration.
    view=None means this is the first modal (it spawns the layout message);
    a passed view means the admin re-opened it to fix the fields."""
    def __init__(self, author_id, emoji_choices, view=None):
        super().__init__(title="Item fields")
        self.author_id = author_id
        self.emoji_choices = emoji_choices
        self.view_ref = view

        self.name_input = ui.TextInput(
            label="Item name",
            default=(view.item_name if view else ""),
            required=True,
            max_length=100,
        )
        self.add_item(self.name_input)

        # emoji: dropdown of the server's custom emojis, or a text field if it have none
        if emoji_choices:
            options = [
                discord.SelectOption(
                    label=e.name, value=str(e), emoji=e,
                    default=bool(view and view.emoji == str(e)),
                )
                for e in emoji_choices[:25]
            ]
            self.emoji_select = ui.Select(placeholder="Pick an emoji (optional)", min_values=0, max_values=1, options=options)
            self.emoji_input = None
            self.add_item(ui.Label(text="Emoji", component=self.emoji_select))
        else:
            self.emoji_select = None
            self.emoji_input = ui.TextInput(
                label="Emoji (wrapped in colons, e.g. :smile:)",
                default=(view.emoji if (view and view.emoji) else ""),
                required=False,
            )
            self.add_item(self.emoji_input)

        # keep the current role preselected
        default_roles = [discord.Object(id=view.role_id, type=discord.Role)] if (view and view.role_id) else []
        self.role_select = ui.RoleSelect(placeholder="Pick a role (optional)", min_values=0, max_values=1, default_values=default_roles)
        self.add_item(ui.Label(text="Role", component=self.role_select))

        self.duration_input = ui.TextInput(
            label="Duration in hours (whole number)",
            default=(str(view.duration) if (view and view.duration is not None) else ""),
            required=False,
            placeholder="e.g. 24 (hours)",
            max_length=6,
        )
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.emoji_select is not None:
            emoji = self.emoji_select.values[0] if self.emoji_select.values else None
        else:
            emoji = self.emoji_input.value.strip() or None
            if emoji and (not emoji.startswith(':') or not emoji.endswith(':')):
                return await interaction.response.send_message(
                    "Emoji must be wrapped in colons, like :smile:.", ephemeral=True
                )

        duration_raw = self.duration_input.value.strip()
        if duration_raw and not duration_raw.isdigit():
            return await interaction.response.send_message(
                "Duration must be a whole number.", ephemeral=True
            )
        duration = int(duration_raw) if duration_raw else None
        name = self.name_input.value.strip()
        role_id = self.role_select.values[0].id if self.role_select.values else None

        if self.view_ref is None:
            # first modal -> spawn the layout as a second message
            view = AddEffectView(self.author_id, self.emoji_choices, name, emoji, duration, False, False, role_id)
            return await interaction.response.send_message(view=view, ephemeral=True)
        else:
            # re-edit -> update the existing layout in place
            v = self.view_ref
            v.item_name, v.emoji, v.duration, v.role_id = name, emoji, duration, role_id
            return await interaction.response.edit_message(view=v.rebuilt())


class _EditButton(ui.Button):
    def __init__(self, view):
        super().__init__(label="Edit fields", style=discord.ButtonStyle.primary)
        self.state = view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EditFieldsModal(self.state.author_id, self.state.emoji_choices, view=self.state))


class _ToggleButton(ui.Button):
    """Boolean toggle sitting inside its section: green = yes, red = no"""
    def __init__(self, view, field):
        current = getattr(view, field)
        super().__init__(
            label="Yes" if current else "No",
            style=discord.ButtonStyle.success if current else discord.ButtonStyle.danger,
        )
        self.state = view
        self.field = field

    async def callback(self, interaction: discord.Interaction):
        setattr(self.state, self.field, not getattr(self.state, self.field))
        await interaction.response.edit_message(view=self.state.rebuilt())


class _FinishButton(ui.Button):
    def __init__(self, view):
        super().__init__(label="Finish", style=discord.ButtonStyle.green)
        self.state = view

    async def callback(self, interaction: discord.Interaction):
        view = self.state
        # validate what the admin filled in; keep the menu open on error
        if not view.item_name:
            return await interaction.response.send_message(
                _format_add_effect_message(AddEffectOutcome.NO_NAME, interaction.user.mention, view.item_name), ephemeral=True
            )
        if view.in_casino and not view.emoji:
            return await interaction.response.send_message(
                _format_add_effect_message(AddEffectOutcome.NO_EMOJI, interaction.user.mention, view.item_name), ephemeral=True
            )

        outcome = await _save(
            view.author_id, view.item_name, view.in_casino,
            view.role_id, view.emoji, view.on_author, view.duration,
        )
        message = _format_add_effect_message(outcome, interaction.user.mention, view.item_name)
        if outcome is not AddEffectOutcome.SUCCESS:
            # something went wrong (e.g. duplicate name) — keep the menu open
            return await interaction.response.send_message(message, ephemeral=True)

        await interaction.response.edit_message(view=view)
        await interaction.delete_original_response()
        await interaction.followup.send(message, ephemeral=True)
        view.stop()


class _CancelButton(ui.Button):
    def __init__(self, view):
        super().__init__(label="Cancel", style=discord.ButtonStyle.danger)
        self.state = view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=self.state)
        await interaction.delete_original_response()
        await interaction.followup.send("Adding cancelled.", ephemeral=True)
        self.state.stop()


class AddEffectView(ui.LayoutView):
    """Second message: preview card + boolean toggles + confirm"""
    def __init__(self, author_id, emoji_choices, item_name="", emoji=None, duration=None, in_casino=False, on_author=False, role_id=None):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.emoji_choices = emoji_choices
        self.item_name = item_name
        self.emoji = emoji
        self.duration = duration
        self.in_casino = in_casino
        self.on_author = on_author
        self.role_id = role_id

        container = ui.Container()
        container.add_item(ui.TextDisplay(f"# {item_name or 'New item'}"))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))
        container.add_item(ui.TextDisplay(f"### Role: {f'<@&{role_id}>' if role_id else '—'}"))
        container.add_item(ui.TextDisplay(f"### Emoji: {emoji or '—'}"))
        container.add_item(ui.TextDisplay(f"### Duration: {f'{duration} hours' if duration is not None else '—'}"))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))
        # booleans as sections — the toggle button lives inside the section (green = yes, red = no)
        container.add_item(ui.Section(ui.TextDisplay("### Exist in casino as item"), accessory=_ToggleButton(self, "in_casino")))
        container.add_item(ui.Section(ui.TextDisplay("### Author using item on himself"), accessory=_ToggleButton(self, "on_author")))
        self.add_item(container)

        action_row = ui.ActionRow()
        action_row.add_item(_EditButton(self))
        action_row.add_item(_FinishButton(self))
        action_row.add_item(_CancelButton(self))
        self.add_item(action_row)

    def rebuilt(self):
        """A fresh view carrying the current state (used after any edit)"""
        return AddEffectView(
            self.author_id, self.emoji_choices, self.item_name, self.emoji,
            self.duration, self.in_casino, self.on_author, self.role_id,
        )

    async def interaction_check(self, interaction: discord.Interaction):
        # only the admin who opened the menu may touch it
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your menu.", ephemeral=True)
            return False
        return True


async def handle(interaction):
    logger.debug("Handler started work")
    # admin check must run before send_modal (a modal has to be the first response)
    if not await _is_admin(interaction.user.id):
        return await interaction.response.send_message("You don't have permission to do this.", ephemeral=True)

    emoji_choices = list(interaction.guild.emojis) if interaction.guild else []
    return await interaction.response.send_modal(EditFieldsModal(interaction.user.id, emoji_choices))
