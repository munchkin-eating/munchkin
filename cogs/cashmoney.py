from discord.ext import commands
from discord.ext.commands import Context
import discord
import asyncio
import json
import os
import time
import random
import string

STOCK_FILE = "stock.json" # Path to your itemlist
GCASH_NUMBER = "09610617355" # Gcash number for payments
GCASH_OWNER_ID = 762976863689113600 #[DEPRACATED] dati kasi magddm lang yung bot sa owner 
TICKET_TIMEOUT = 900 # 15 minutes
TICKET_CATEGORY_NAME = "Tickets"
ARCHIVE_CATEGORY_NAME = "Archive"
STAFF_CHANNEL_ID = 1398173714733862942
PERSISTENT_MESSAGE_CHANNEL_ID = 1398181590902767626
PERSISTENT_MESSAGE_ID_FILE = "ticket_button_message_id.txt" 
NOTIFY_CHANNEL_ID = 1398979639870881912

ORDER_QUEUE_FILE = "order_queue.txt" # Add a global queue counter

# Store queue info as a list of dicts: [{code, number, user_id, status}]
QUEUE_INFO_FILE = "queue_info.json"

def load_stock():
    with open(STOCK_FILE, "r") as f:
        return json.load(f)

def save_stock(stock):
    with open(STOCK_FILE, "w") as f:
        json.dump(stock, f, indent=4)

def load_queue_info():
    if not os.path.exists(QUEUE_INFO_FILE):
        return []
    with open(QUEUE_INFO_FILE, "r") as f:
        return json.load(f)

def save_queue_info(queue_info):
    with open(QUEUE_INFO_FILE, "w") as f:
        json.dump(queue_info, f, indent=4)

def generate_dynamic_queue():
    # Generates a queue string like "A1B2C3" using random letters and digits
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=6))

def get_next_queue_number():
    queue_info = load_queue_info()
    return len(queue_info) + 1

def register_queue(user_id, code, status="pending"):
    queue_info = load_queue_info()
    # Ensure queue code is unique
    if any(q["code"] == code for q in queue_info):
        # If code exists, generate a new one recursively
        return register_queue(user_id, generate_dynamic_queue(), status)
    # Find the lowest available number (fill gaps if any)
    used_numbers = {q["number"] for q in queue_info}
    number = 1
    while number in used_numbers:
        number += 1
    queue_info.append({
        "code": code,
        "number": number,
        "user_id": user_id,
        "status": status
    })
    save_queue_info(queue_info)
    return number

def get_queue_number_by_code(code):
    queue_info = load_queue_info()
    for q in queue_info:
        if q["code"] == code:
            return q["number"]
    return None

def get_queue_status_by_code(code):
    queue_info = load_queue_info()
    for q in queue_info:
        if q["code"] == code:
            return q["status"]
    return "pending"

def update_queue_status(code, status):
    queue_info = load_queue_info()
    for q in queue_info:
        if q["code"] == code:
            q["status"] = status
            break
    save_queue_info(queue_info)

def remove_queue_by_code(code):
    queue_info = load_queue_info()
    queue_info = [q for q in queue_info if q["code"] != code]
    save_queue_info(queue_info)

class ConfirmPaymentView(discord.ui.View):
    def __init__(self, user: discord.User, ticket_channel: discord.TextChannel, image_url=None, item_name=None, queue_code=None):
        super().__init__(timeout=300)
        self.user = user
        self.ticket_channel = ticket_channel
        self.image_url = image_url
        self.item_name = item_name
        self.queue_code = queue_code
        self.ticket_timeout_task = None

    @discord.ui.button(label="Confirm Payment", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff = interaction.user.display_name
        update_queue_status(self.queue_code, "confirmed")
        queue_number = get_queue_number_by_code(self.queue_code)
        await interaction.response.send_message(
            f"Payment confirmed by {staff}. <3", ephemeral=False
        )
        await self.ticket_channel.send(
            f"{self.user.mention} your payment has been confirmed by {staff}! God bless you!!\n"
            f"> Your queue/order code is `{self.queue_code}` (Order #{queue_number})."
        )
        try:
            await self.user.send(
                f"Your payment for **{self.item_name or 'your item'}** has been confirmed by {staff}!\n"
                f"Thank you for your purchase. God bless you!\n"
                f"> Your queue/order code is `{self.queue_code}` (Order #{queue_number})."
            )
        except discord.Forbidden:
            await self.ticket_channel.send("Couldn't DM the user — they may have DMs disabled.")

        # Remove from queue when completed
        remove_queue_by_code(self.queue_code)

        archive_category = discord.utils.get(self.ticket_channel.guild.categories, name=ARCHIVE_CATEGORY_NAME)
        if not archive_category:
            archive_category = await self.ticket_channel.guild.create_category(ARCHIVE_CATEGORY_NAME)
        await asyncio.sleep(20)
        await self.ticket_channel.edit(category=archive_category)
        await self.ticket_channel.set_permissions(self.user, overwrite=None)
        await self.ticket_channel.send("This ticket has been archived.")
        self.stop()

    ################# REJECTION SYSTEM #################################
    @discord.ui.button(label="Reject Payment", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff = interaction.user.display_name
        update_queue_status(self.queue_code, "rejected")
        queue_number = get_queue_number_by_code(self.queue_code)
        await interaction.response.send_message(
            f"Order at {self.ticket_channel.mention} was rejected by {staff}.", ephemeral=False
        )
        await self.ticket_channel.send(
            f"{self.user.mention} your payment for {self.item_name} was **rejected** by {staff}.\n"
            f"Please try `/confirm` again with a valid screenshot, or your ticket will expire and be archived within 15 minutes.\n"
            f"> Your queue/order code is `{self.queue_code}` (Order #{queue_number})."
        )
        try:
            await self.user.send(
                f"Your payment for **{self.item_name or 'your item'}** was rejected by {staff}.\n"
                f"Please try `/confirm` again with a valid screenshot, or your ticket will expire and be archived within 15 minutes.\n"
                f"> Your queue/order code is `{self.queue_code}` (Order #{queue_number})."
            )
        except discord.Forbidden:
            await self.ticket_channel.send("Couldn't DM the user — they may have DMs disabled.")

    @discord.ui.button(label="Processing", style=discord.ButtonStyle.primary)
    async def processing(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff = interaction.user.display_name
        update_queue_status(self.queue_code, "processing")
        queue_number = get_queue_number_by_code(self.queue_code)
        await interaction.response.send_message(
            f"Order at {self.ticket_channel.mention} is now being processed by {staff}.", ephemeral=False
        )
        await self.ticket_channel.send(
            f"{self.user.mention} your payment for {self.item_name} is now **being processed** by {staff}.\n"
            f"Please wait while your order is handled.\n"
            f"> Your queue/order code is `{self.queue_code}` (Order #{queue_number})."
        )
        try:
            await self.user.send(
                f"Your payment for **{self.item_name or 'your item'}** is now being processed by {staff}.\n"
                f"Please wait while your order is handled.\n"
                f"> Your queue/order code is `{self.queue_code}` (Order #{queue_number})."
            )
        except discord.Forbidden:
            await self.ticket_channel.send("Couldn't DM the user — they may have DMs disabled.")
        # Remove ticket timeout by cancelling the delete task if possible
        bot = interaction.client
        if hasattr(bot, "ticket_timeout_tasks"):
            task = bot.ticket_timeout_tasks.get(self.ticket_channel.id)
            if task:
                task.cancel()
                await self.ticket_channel.send("Ticket timeout has been removed. This ticket will remain open until manually archived.")

    @discord.ui.button(label="Eliminate Order", style=discord.ButtonStyle.danger)
    async def eliminate(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff = interaction.user.display_name
        remove_queue_by_code(self.queue_code)
        await interaction.response.send_message(
            f"Order eliminated by {staff}. Ticket will be archived.", ephemeral=False
        )
        await self.ticket_channel.send(
            f"{self.user.mention} your order has been **eliminated** by {staff}. This ticket will now be archived."
        )
        await self.user.send(
            f"{self.user.mention} your order has been **eliminated** by {staff}. This ticket will now be archived."
        )
        archive_category = discord.utils.get(self.ticket_channel.guild.categories, name=ARCHIVE_CATEGORY_NAME)
        if not archive_category:
            archive_category = await self.ticket_channel.guild.create_category(ARCHIVE_CATEGORY_NAME)
        await asyncio.sleep(5)
        await self.ticket_channel.edit(category=archive_category)
        await self.ticket_channel.set_permissions(self.user, overwrite=None)
        await self.ticket_channel.send("This ticket has been archived.")
        self.stop()

class ItemButton(discord.ui.Button):
    # List of pastel hex color codes for buttons
    PASTEL_HEX_COLORS = [
        0xFFD1DC, # pastel pink
        0xB5EAD7, # pastel green
        0xC7CEEA, # pastel blue
        0xFFDAC1, # pastel peach
        0xE2F0CB, # pastel mint
        0xFFFACD, # pastel lemon
        0xD5CFE1, # pastel lavender
        0xF3FFE3, # pastel white-green
        0xE0BBE4, # pastel purple
        0xFFB7B2, # pastel coral
    ]

    def __init__(self, label, item_name, disabled, requester, bot):
        hex_color = random.choice(ItemButton.PASTEL_HEX_COLORS)
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"{item_name}:{hex_color}", disabled=disabled)
        self.item_name = item_name
        self.requester = requester
        self.bot = bot
        self.hex_color = hex_color

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
            f"How many do you want to order? Please **reply to this message** with a number.",
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
                await interaction.channel.send("Please press the button again to restart your order.")
                return
            if item["stock"] < quantity:
                await interaction.channel.send(f"Not enough stock! Only {item['stock']} left.")
                await interaction.channel.send("Please press the button again to restart your order.")
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

class Cashmoney(commands.Cog, name="cashmoney"):
    def __init__(self, bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="ticket", description="Creates a ticket for your transactions.")
    async def ticket(self, context: Context) -> None:
        guild = context.guild
        requester = context.author
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(name=TICKET_CATEGORY_NAME)

        # Use dynamic queue string instead of numeric
        queue_code = generate_dynamic_queue()
        queue_number = register_queue(context.author.id, queue_code)

        # Change channel name to use queue_code instead of timecode
        channel_name = requester.name.lower().replace(" ", "-") + "-ticket-" + queue_code
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

        # ...existing code...

        notify_channel = guild.get_channel(NOTIFY_CHANNEL_ID)
        if notify_channel:
            await notify_channel.send(f"{requester.mention}, you have created your ticket channel at {new_channel.mention} (Queue `{queue_code}` / Order #{queue_number})")

        stock = load_stock()
        embed = discord.Embed(
            title="Available Items",
            color=0xEAEBD0
        )
        for name, data in stock.items():
            embed.add_field(
                name=f"{name} - ₱{data['price']}",
                value=data.get('description', 'No description'),
                inline=False
            )
        embed.add_field(
            name="Order Instructions",
            value=f"{requester.name}, send payment to `{GCASH_NUMBER}` after choosing below.\nThis ticket will explode in 15 minutes.\nQueue/Order Code: `{queue_code}` (Order #{queue_number})",
            inline=False
        )
        await new_channel.send(
            embed=embed,
            view=ItemSelectView(requester, self.bot)
        )

        await new_channel.send(
            f"{requester.mention}, your order ticket has been created! Please select an item above to start your order."
        )
        await new_channel.send(file=discord.File("assets/QR.jpg"))
        # Store queue code for later use in confirm
        if not hasattr(self.bot, "queue_numbers"):
            self.bot.queue_numbers = {}
        self.bot.queue_numbers[requester.id] = queue_code
        # Store the asyncio task for timeout so it can be cancelled
        async def ticket_timeout():
            await asyncio.sleep(TICKET_TIMEOUT)
            await new_channel.delete(reason="Ticket expired")
        # Instead of attaching to the channel, store in a dict on the cog/bot
        if not hasattr(self.bot, "ticket_timeout_tasks"):
            self.bot.ticket_timeout_tasks = {}
        self.bot.ticket_timeout_tasks[new_channel.id] = asyncio.create_task(ticket_timeout())

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
        queue_code = getattr(self.bot, "queue_numbers", {}).get(requester.id, "N/A")
        queue_number = get_queue_number_by_code(queue_code)

        staff_channel = ctx.guild.get_channel(STAFF_CHANNEL_ID)
        if staff_channel:
            role_mention = f"<@&1398978392744792084>" # ORDER HANDLER ROLE ID
            embed = discord.Embed(
                title=f"(#{queue_number})[{queue_code}] {requester.display_name}'s Payment Confirmation for {ctx.channel.mention}",
                description=(
                    f"{requester.mention} submitted a payment in {ctx.channel.mention}\n"
                    f"Item: **{item_name}**\n"
                    f"Quantity: **{quantity}**\n"
                    f"Total: **₱{total_price}**\n"
                    f"Queue/Order Code: `{queue_code}` (Order #{queue_number})"
                ),
                color=discord.Color.green()
            )
            embed.set_image(url=image_url)
            embed.set_thumbnail(url=requester.display_avatar.url)
            await staff_channel.send(
                embed=embed,
                view=ConfirmPaymentView(requester, ctx.channel, image_url, item_name, queue_code),
                content=role_mention
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