import discord

class Buttons(discord.ui.View):
    def __init__(self, items: list, timeout: float = 60.0):
        """
        Class to make buttons under message
        Usually should be used when message to big and make a couple of message is ugly
        you should have a list [1,2,3 f.e]
        make object view = Buttons(list)
        and send (list[0], view=view)
        """

        super().__init__(timeout=timeout)

        self.items = items  # can be strings, embeds or dicts
        self.index = 0
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()


        back_button = discord.ui.Button(
            label="◀",
            style=discord.ButtonStyle.gray,
            disabled=self.index <= 0,
            custom_id="back"
        )
        back_button.callback = self.back_callback
        self.add_item(back_button)


        total_pages = len(self.items)
        page_button = discord.ui.Button(
            label=f"Page {self.index + 1}/{total_pages}",
            style=discord.ButtonStyle.gray,
            disabled=True,
            custom_id="page"
        )
        self.add_item(page_button)


        forward_button = discord.ui.Button(
            label="▶",
            style=discord.ButtonStyle.gray,
            disabled=self.index >= total_pages - 1,
            custom_id="forward"
        )
        forward_button.callback = self.forward_callback
        self.add_item(forward_button)

    def get_message_kwargs(self):
        item = self.items[self.index]

        if isinstance(item, discord.Embed):
            return {"embed": item}
        elif isinstance(item, str):
            return {"content": item}
        elif isinstance(item, dict):
            return item
        else:
            return {"content": str(item)}

    async def back_callback(self, interaction: discord.Interaction):
        if self.index > 0:
            self.index -= 1
            self.update_buttons()
            kwargs = self.get_message_kwargs()
            await interaction.response.edit_message(**kwargs, view=self)

    async def forward_callback(self, interaction: discord.Interaction):
        if self.index < len(self.items) - 1:
            self.index += 1
            self.update_buttons()
            kwargs = self.get_message_kwargs()
            await interaction.response.edit_message(**kwargs, view=self)
