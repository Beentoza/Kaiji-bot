import enum
import discord
from discord import ui

from database.db_functions import db_admin, db_items
from database.uow import UnitOfWork
from helpers.logger_config import internal_logger as logger


class ChangeEffectOutcome(enum.Enum):
    """A types of change-effect outcome"""
    NOT_ADMIN = "not_admin"
    ITEM_NOT_FOUND = "item_not_found"
    ROLE_NOT_FOUND = "role_not_found"
    SUCCESS = "success"
    ERROR = "error"


def _format_change_effect_message(outcome, mention, item_name):
    """From outcome making a message"""
    match outcome:
        case ChangeEffectOutcome.NOT_ADMIN:
            return f"{mention} you don't have permission to do this."
        case ChangeEffectOutcome.ITEM_NOT_FOUND:
            return f"{mention} that item wasn't found."
        case ChangeEffectOutcome.ROLE_NOT_FOUND:
            return f"{mention} that role wasn't found."
        case ChangeEffectOutcome.SUCCESS:
            return f"{mention} item '{item_name}' has been changed."
    return f"Error occurred"


def _build_embed(pending):
    """Preview of what the item will look like after the changes"""
    embed = discord.Embed(title=f"Editing item: {pending['item_name']}", color=0x3498db)
    embed.add_field(name="Name (locked)", value=pending['item_name'], inline=False)
    embed.add_field(name="Role", value=f"<@&{pending['role']}>" if pending['role'] else "—", inline=True)
    embed.add_field(name="Emoji", value=pending['emoji'] or "—", inline=True)
    embed.add_field(name="Duration", value=str(pending['duration']) if pending['duration'] is not None else "—", inline=True)
    embed.add_field(name="In casino", value=str(pending['in_casino']), inline=True)
    embed.add_field(name="On author", value=str(pending['on_author']), inline=True)
    return embed


async def _is_admin(user_id):
    async with UnitOfWork() as uow:
        return await db_admin.is_admin(uow.session, user_id)


async def _save(user_id, pending, get_role):
    """Persist the pending settings. Returns a ChangeEffectOutcome."""
    async with UnitOfWork() as uow:
        if not await db_admin.is_admin(uow.session, user_id):
            return ChangeEffectOutcome.NOT_ADMIN

        # resolve the role only if the item has one set
        role_id_to_store = None
        if pending['role'] is not None:
            # if role doesn't exist
            role = get_role(pending['role'])
            if not role:
                return ChangeEffectOutcome.ROLE_NOT_FOUND
            role_id_to_store = role.id

        # updating item in DB
        changed = await db_items.change_item(
            session=uow.session,
            item_name=pending['item_name'],
            in_casino=pending['in_casino'],
            role=role_id_to_store,
            emoji=pending['emoji'],
            on_author=pending['on_author'],
            duration=pending['duration'],
        )
        if not changed:
            return ChangeEffectOutcome.ITEM_NOT_FOUND

    return ChangeEffectOutcome.SUCCESS


class EditFieldsModal(ui.Modal):
    """Text fields the admin can retype: emoji and duration"""
    def __init__(self, view):
        super().__init__(title="Edit item fields")
        self.view_ref = view
        self.emoji_input = ui.TextInput(
            label="Emoji (wrapped in colons, e.g. :smile:)",
            default=view.pending['emoji'] or "",
            required=False,
        )
        self.duration_input = ui.TextInput(
            label="Duration (whole number)",
            default=str(view.pending['duration']) if view.pending['duration'] is not None else "",
            required=False,
        )
        self.add_item(self.emoji_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        emoji = self.emoji_input.value.strip()
        if emoji and (not emoji.startswith(':') or not emoji.endswith(':')):
            return await interaction.response.send_message(
                "Emoji must be wrapped in colons, like :smile:.", ephemeral=True
            )

        duration_raw = self.duration_input.value.strip()
        if duration_raw and not duration_raw.isdigit():
            return await interaction.response.send_message(
                "Duration must be a whole number.", ephemeral=True
            )

        self.view_ref.pending['emoji'] = emoji or None
        self.view_ref.pending['duration'] = int(duration_raw) if duration_raw else None
        await interaction.response.edit_message(embed=_build_embed(self.view_ref.pending), view=self.view_ref)


class ChangeEffectView(ui.View):
    """Ephemeral window where the admin tweaks settings before confirming"""
    def __init__(self, author_id, pending, get_role):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.pending = pending
        self.get_role = get_role

    async def interaction_check(self, interaction: discord.Interaction):
        # only the admin who opened the menu may touch it
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your menu.", ephemeral=True)
            return False
        return True

    @ui.button(label="Edit fields", style=discord.ButtonStyle.primary, row=0)
    async def edit_fields(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(EditFieldsModal(self))

    @ui.button(label="Toggle in_casino", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_casino(self, interaction: discord.Interaction, button: ui.Button):
        self.pending['in_casino'] = not self.pending['in_casino']
        await interaction.response.edit_message(embed=_build_embed(self.pending), view=self)

    @ui.button(label="Toggle on_author", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_on_author(self, interaction: discord.Interaction, button: ui.Button):
        self.pending['on_author'] = not self.pending['on_author']
        await interaction.response.edit_message(embed=_build_embed(self.pending), view=self)

    @ui.select(cls=ui.RoleSelect, placeholder="Pick a new role (optional)", min_values=0, max_values=1, row=1)
    async def select_role(self, interaction: discord.Interaction, select: ui.RoleSelect):
        if select.values:
            self.pending['role'] = select.values[0].id
        await interaction.response.edit_message(embed=_build_embed(self.pending), view=self)

    @ui.button(label="Confirm", style=discord.ButtonStyle.green, row=2)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        outcome = await _save(self.author_id, self.pending, self.get_role)
        for child in self.children:
            child.disabled = True
        message = _format_change_effect_message(outcome, interaction.user.mention, self.pending['item_name'])
        await interaction.response.edit_message(content=message, embed=None, view=self)
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Change cancelled.", embed=None, view=self)
        self.stop()


async def handle(
        interaction,
        item_name: str # which item to change (picked from autocomplete, stays the key)
):
    await interaction.response.defer(thinking=True, ephemeral=True)
    logger.debug("Handler started work")
    try:
        if not await _is_admin(interaction.user.id):
            return await interaction.followup.send("You don't have permission to do this.", ephemeral=True)

        settings = await db_items.get_item_settings(item_name)
        if settings is None:
            return await interaction.followup.send("That item wasn't found.", ephemeral=True)

        # current settings the admin will tweak; item_name is the locked key
        pending = {
            'item_name': settings.item_name,
            'in_casino': bool(settings.in_casino),
            'role': settings.role,
            'emoji': settings.emoji,
            'on_author': bool(settings.on_author),
            'duration': settings.duration,
        }
        view = ChangeEffectView(interaction.user.id, pending, interaction.guild.get_role)
        await interaction.followup.send(embed=_build_embed(pending), view=view, ephemeral=True)
    except Exception as e:
        await interaction.followup.send("Error occurred", ephemeral=True)
        logger.warning(f"Error occurred for {interaction.user}: {e}")
