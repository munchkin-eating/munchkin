from discord.ext import commands
from discord.ext.commands import Context
import discord
import asyncio
import json
import os
import time

STOCK_FILE = "stock.json" # Path to your itemlist
GCASH_NUMBER = "09610617355" # Gcash number for payments
GCASH_OWNER_ID = 762976863689113600 #[DEPRACATED] dati kasi magddm lang yung bot sa owner 
TICKET_TIMEOUT = 900 # 15 minutes
TICKET_CATEGORY_NAME = "Tickets"
ARCHIVE_CATEGORY_NAME = "Archive"
STAFF_CHANNEL_ID = 1398173714733862942
PERSISTENT_MESSAGE_CHANNEL_ID = 1398181590902767626
PERSISTENT_MESSAGE_ID_FILE = "ticket_button_message_id.txt" 
NOTIFY_CHANNEL_ID = 1398698611935809626  

def load_stock():
    with open(STOCK_FILE, "r") as f:
        return json.load(f)

def save_stock(stock):
    with open(STOCK_FILE, "w") as f:
        json.dump(stock, f, indent=4)

class ConfirmPaymentView(discord.ui.View):
    def __init__(self, user: discord.User, ticket_channel: discord.TextChannel, image_url=None, item_name=None):
        super().__init__(timeout=300)
        self.user = user
        self.ticket_channel = ticket_channel
        self.image_url = image_url
        self.item_name = item_name

    @discord.ui.button(label="Confirm Payment", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != GCASH_OWNER_ID:
            await interaction.response.send_message("You're not authorized to confirm this.", ephemeral=True)
            return

        await interaction.response.send_message("Payment confirmed. <3", ephemeral=False)
        await self.ticket_channel.send(f"{self.user.mention} your payment has been confirmed! God bless you!!")

        try:
            await self.user.send(
                f"Your payment for **{self.item_name or 'your item'}** has been confirmed!\n"
                f"Thank you for your purchase. God bless you!"
            )
        except discord.Forbidden:
            await self.ticket_channel.send("Couldn't DM the user — they may have DMs disabled.")

        archive_category = discord.utils.get(self.ticket_channel.guild.categories, name=ARCHIVE_CATEGORY_NAME)
        if not archive_category:
            archive_category = await self.ticket_channel.guild.create_category(ARCHIVE_CATEGORY_NAME)
        await asyncio.sleep(20)
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

        # Prompt for quantity
        await interaction.response.send_message(
            f"You selected **{self.item_name}**.\n"
            f"Description: *{item.get('description', 'No description')}*\n"
            f"How many do you want to order? Please reply with a number.",
            ephemeral=False
        )

        def check(m):
            return (
                m.author.id == self.requester.id and
                m.channel.id == interaction.channel.id and
                m.content.isdigit()
            )

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=60)
            quantity = int(msg.content)
            if quantity <= 0:
                await interaction.channel.send("Quantity must be at least 1.")
                return
            if item["stock"] < quantity:
                await interaction.channel.send(f"Not enough stock! Only {item['stock']} left.")
                return

            item["stock"] -= quantity
            save_stock(stock)

            # Store selection for later confirmation
            interaction.client.selected_items = getattr(interaction.client, "selected_items", {})
            interaction.client.selected_items[self.requester.id] = {
                "item_name": self.item_name,
                "quantity": quantity,
                "total_price": item["price"] * quantity
            }

            await interaction.channel.send(
                f"You ordered **{quantity}x {self.item_name}**\n"
                f"Total: **₱{item['price']} x {quantity} = ₱{item['price'] * quantity}**\n"
                f"Please send **₱{item['price'] * quantity}** to `{GCASH_NUMBER}` via GCash and upload the screenshot using `/confirm`."
            )
        except asyncio.TimeoutError:
            await interaction.channel.send("Timed out waiting for quantity. Please press the button again to restart your order.")

class Cashmoney(commands.Cog, name="cashmoney"):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="ticket", description="Creates a ticket for your transactions.")
    async def ticket(self, context: Context) -> None:
        guild = context.guild
        requester = context.author
        ref_ID = time.time()  # Use current time as reference ID
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(name=TICKET_CATEGORY_NAME)

        channel_name = requester.name.lower().replace(" ", "-") + "s-ticket-" + str(int(ref_ID))
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

        notify_channel = guild.get_channel(NOTIFY_CHANNEL_ID)
        if notify_channel:
            await notify_channel.send(f"{requester.mention}, you have created your ticket channel at {new_channel.mention}")

        stock = load_stock()
        formatted_items = "\n".join(
            f"**{name}** - ₱{data['price']}\n> {data.get('description', 'No description')}"
            for name, data in stock.items()
        )
        await new_channel.send(
            f"**Available Items:**\n{formatted_items}\n\n"
            f"{requester.mention} Send payment to `{GCASH_NUMBER}` after choosing below. This ticket will explode in 15 minutes.",
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
        selected = getattr(self.bot, "selected_items", {}).get(requester.id)
        if not selected:
            await ctx.reply("No item and quantity registered for your order. Please select an item first.")
            return

        item_name = selected["item_name"]
        quantity = selected["quantity"]
        total_price = selected["total_price"]

        staff_channel = ctx.guild.get_channel(STAFF_CHANNEL_ID)
        if staff_channel:
            embed = discord.Embed(
                title="GCash Payment Confirmation",
                description=(
                    f"{requester.mention} submitted a payment in {ctx.channel.mention}\n"
                    f"Item: **{item_name}**\n"
                    f"Quantity: **{quantity}**\n"
                    f"Total: **₱{total_price}**"
                ),
                color=discord.Color.green()
            )
            embed.set_image(url=image_url)
            await staff_channel.send(
                embed=embed,
                view=ConfirmPaymentView(requester, ctx.channel, image_url, item_name)
            )
            await ctx.reply("Screenshot sent to the staff for confirmation.")
        else:
            await ctx.reply("Couldn't find the staff channel.")

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketButtonView(self.bot))
        try:
            with open(PERSISTENT_MESSAGE_ID_FILE, "r") as f:
                message_id = int(f.read().strip())
                channel = self.bot.get_channel(PERSISTENT_MESSAGE_CHANNEL_ID)
                if channel:
                    try:
                        await channel.fetch_message(message_id)
                        return
                    except discord.NotFound:
                        pass
        except (FileNotFoundError, ValueError):
            pass

        channel = self.bot.get_channel(PERSISTENT_MESSAGE_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title="Open an Order",
                description=(
                    "• Open a ticket if you're a **sure buyer**\n"
                    "• Ghosted or inactive ticket shall be **closed**\n"
                    "• Strictly **no rushing** of orders\n"
                    "• **Different orders = different tickets**\n"
                    "• **Ask** if the item is available first\n"
                    "• Do **not ping staff** repeatedly"
                ),
                color=0xFDAEAE
            )
            embed.set_footer(text=f"Created by 永恆的王")
            msg = await channel.send(embed=embed, view=TicketButtonView(self.bot))
            with open(PERSISTENT_MESSAGE_ID_FILE, "w") as f:
                f.write(str(msg.id))


class TicketButtonView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Create Order", style=discord.ButtonStyle.primary, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx = await self.bot.get_context(interaction.message)
        ctx.author = interaction.user
        await self.bot.get_cog("cashmoney").ticket(ctx)
        await interaction.response.defer()

async def setup(bot) -> None:
    await bot.add_cog(Cashmoney(bot))
