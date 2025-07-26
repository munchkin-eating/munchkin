from discord.ext import commands
from discord.ext.commands import Context
import discord
import asyncio
import json
import os

STOCK_FILE = "stock.json"
GCASH_NUMBER = "09610617355"
GCASH_OWNER_ID = 762976863689113600  # Replace with your Discord ID
TICKET_TIMEOUT = 3600
TICKET_CATEGORY_NAME = "Tickets"
ARCHIVE_CATEGORY_NAME = "Archive"

def load_stock():
    with open(STOCK_FILE, "r") as f:
        return json.load(f)

def save_stock(stock):
    with open(STOCK_FILE, "w") as f:
        json.dump(stock, f, indent=4)

class ConfirmPaymentView(discord.ui.View):
    def __init__(self, user: discord.User, ticket_channel: discord.TextChannel, image_url=None):
        super().__init__(timeout=300)
        self.user = user
        self.ticket_channel = ticket_channel
        self.image_url = image_url

    @discord.ui.button(label="Confirm Payment", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != GCASH_OWNER_ID:
            await interaction.response.send_message("You're not authorized to confirm this.", ephemeral=True)
            return
        await interaction.response.send_message("Payment confirmed. <3", ephemeral=False)
        await self.ticket_channel.send(f"{self.user.mention} your payment has been confirmed! God bless you!!")

        archive_category = discord.utils.get(self.ticket_channel.guild.categories, name=ARCHIVE_CATEGORY_NAME)
        if not archive_category:
            archive_category = await self.ticket_channel.guild.create_category(ARCHIVE_CATEGORY_NAME)

        await self.ticket_channel.edit(category=archive_category)
        await self.ticket_channel.set_permissions(self.user, overwrite=None)
        await self.ticket_channel.send("This ticket has been archived.")
        self.stop()

class ItemSelectView(discord.ui.View):
    def __init__(self, requester: discord.User, bot: commands.Bot):
        super().__init__(timeout=None)
        self.requester = requester
        self.bot = bot
        self.stock = load_stock()

        for name, data in self.stock.items():
            label = f"{name} - ₱{data['price']}"
            disabled = data["stock"] <= 0
            if disabled:
                label += " (Out of stock)"
            self.add_item(ItemButton(label, name, disabled, requester, bot))

class ItemButton(discord.ui.Button):
    def __init__(self, label, item_name, disabled, requester, bot):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=item_name, disabled=disabled)
        self.item_name = item_name
        self.requester = requester
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message("Only use these buttons", ephemeral=True)
            return

        stock = load_stock()
        item = stock[self.item_name]

        if item["stock"] <= 0:
            await interaction.response.send_message("WAAAAAAAA THIS ITEM IS OUT OF STOCK", ephemeral=True)
            return

        item["stock"] -= 1
        save_stock(stock)

        await interaction.response.send_message(
            f"You selected **{self.item_name}**\n"
            f"Description: *{item.get('description', 'No description')}*\n"
            f"Please send **₱{item['price']}** to `{GCASH_NUMBER}` via GCash and upload the screenshot using `/confirm`.",
            ephemeral=False
        )

class Cashmoney(commands.Cog, name="cashmoney"):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="ticket", description="Creates a ticket for your transactions.")
    async def ticket(self, context: Context) -> None:
        guild = context.guild
        requester = context.author
        category_name = TICKET_CATEGORY_NAME
        channel_name = requester.name.lower().replace(" ", "-") + "-ticket"

        category = discord.utils.get(guild.categories, name=category_name)
        if category is None:
            category = await guild.create_category(name=category_name)

        existing_channel = discord.utils.get(category.text_channels, name=channel_name)
        if existing_channel:
            await context.send(f"{requester.mention} {existing_channel.mention} you already got a ticket channel bruzz", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            requester: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        new_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Ticket channel for {requester}"
        )

        await context.send(f"{requester.mention}, you have created your ticket channel at {new_channel.mention}", ephemeral=False)

        stock = load_stock()
        formatted_items = "\n".join(
            "\n"
            f"**{name}** - ₱{data['price']}\n> {data.get('description', 'No description')}"
            for name, data in stock.items()
        )
        await new_channel.send(
            f"**Available Items:**\n{formatted_items}\n\n"
            f"{requester.mention} Send payment to `{GCASH_NUMBER}` after choosing below. This ticket will self-destruct in 1 hour.",
            view=ItemSelectView(requester, self.bot)
        )

        await new_channel.send(file=discord.File("assets/QR.jpg"))

        await asyncio.sleep(TICKET_TIMEOUT)
        await new_channel.delete(reason="Ticket expired")

    @commands.hybrid_command(name="confirm", description="Confirm your payment by uploading your screenshot")
    @discord.app_commands.describe(screenshot="Upload your GCash screenshot")
    async def confirm(self, ctx: Context, screenshot: discord.Attachment = None):
        await ctx.defer(ephemeral=False)

        if ctx.channel.category and ctx.channel.category.name != TICKET_CATEGORY_NAME:
            await ctx.reply("This command can only be used inside ticket channels.")
            return

        if not screenshot:
            await ctx.reply("Please upload your GCash screenshot using the `screenshot` option.")
            return

        image_url = screenshot.url
        requester = ctx.author

        gcash_owner = await self.bot.fetch_user(GCASH_OWNER_ID)
        if gcash_owner:
            try:
                embed = discord.Embed(
                    title="GCash Payment Confirmation",
                    description=f"{requester.mention} submitted a payment in {ctx.channel.mention}",
                    color=discord.Color.green()
                )
                embed.set_image(url=image_url)
                await gcash_owner.send(embed=embed, view=ConfirmPaymentView(requester, ctx.channel, image_url))
                await ctx.reply("Screenshot sent to the owner for confirmation.")
            except discord.Forbidden:
                await ctx.reply("Couldn't DM the owner. Please mention them manually in ts channel.")

async def setup(bot) -> None:
    await bot.add_cog(Cashmoney(bot))
