from discord.ext import commands
from discord.ext.commands import Context
import discord
import asyncio
import time
from datetime import datetime, timedelta

from cashutils import (
    l_JsonStock, s_JsonStock, l_qInfo, s_qInfo, genQcode,
    get_next_queue_number, register_queue, remove_queue_by_code,
    update_queue_status, update_queue_last_confirm, get_queue_number_by_code,
    get_queue_status_by_code, get_queue_last_confirm_by_code, get_timestamp,
    archive_expired_tickets
)

STOCK_FILE = "stock.json" # Path to your itemlist
GCASH_NUMBER = "09335075624" # Gcash number for payments
GCASH_OWNER_ID = 762976863689113600 #[DEPRACATED] dati kasi magddm lang yung bot sa owner 
TICKET_TIMEOUT = 60*60*60*2 # secs
TICKET_CATEGORY_NAME = "Active Tickets"
ARCHIVE_CATEGORY_NAME = "Archive"
STAFF_CHANNEL_ID = 1398173714733862942
PERSISTENT_MESSAGE_CHANNEL_ID = 1398181590902767626
PERSISTENT_MESSAGE_ID_FILE = "ticket_button_message_id.txt" 
NOTIFY_CHANNEL_ID = 1398979639870881912
HANDLER_ROLE = 1398978392744792084

ORDER_QUEUE_FILE = "order_queue.txt" # Add a global queue counter
LOG_CHANNEL_ID = 1399302081155698750 
# Store queue info as a list of dicts: [{code, number, user_id, status}]
QUEUE_INFO_FILE = "queue_info.json"



class ConfirmPaymentView(discord.ui.View):
    def __init__(self, user: discord.User, ticket_channel: discord.TextChannel, image_url=None, item_name=None, queue_code=None, staff_message=None):
        super().__init__(timeout=None)
        self.user = user
        self.ticket_channel = ticket_channel
        self.image_url = image_url
        self.item_name = item_name
        self.queue_code = queue_code
        self.ticket_timeout_task = None
        self.staff_message = staff_message  # message object for editing embed

    async def update_staff_embed(self, status, staff_name):
        if self.staff_message:
            embed = self.staff_message.embeds[0]
            color_map = {
                "Pending": discord.Color.light_grey(),
                "Confirmed": discord.Color.green(),
                "Rejected": discord.Color.orange(),
                "Processing": discord.Color.yellow(),
                "Terminated": discord.Color.red()
            }
            embed.color = color_map.get(status, discord.Color.light_grey())
            embed.set_field_at(
                0,
                name="Status",
                value=f"{status} by {staff_name} {get_timestamp()}",
                inline=False
            )
            await self.staff_message.edit(embed=embed)

    async def log_Stat(self, status, staff_name):
        log_channel = self.ticket_channel.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(
                f"Order `{self.queue_code}` (Order #{get_queue_number_by_code(self.queue_code)}) status updated to **{status}** by {staff_name} {get_timestamp()}\n"
                f"{self.ticket_channel.mention}"
            )

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff = f"{interaction.user.display_name} ({interaction.user.id})"
        update_queue_status(self.queue_code, "confirmed")
        update_queue_last_confirm(self.queue_code)
        queue_number = get_queue_number_by_code(self.queue_code)
        await self.ticket_channel.send(
            f"{self.user.mention} your payment has been confirmed by {staff}! God bless you!!\n"
            f"> `{self.queue_code}` (Order #{queue_number})."
        )
        try:
            await self.user.send(
                f"Your payment for **{self.item_name or 'your item'}** has been confirmed by {staff}!\n"
                f"Thank you for your purchase. God bless you!\n"
                f"> `{self.queue_code}` (Order #{queue_number})."
            )
        except discord.Forbidden:
            await self.ticket_channel.send(f"Couldn't DM {self.user.mention}")

        await self.update_staff_embed("Confirmed", staff)
        await self.log_Stat("Confirmed", staff)
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
    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff = interaction.user.display_name
        update_queue_status(self.queue_code, "rejected")
        queue_number = get_queue_number_by_code(self.queue_code)
        await self.ticket_channel.send(
            f"{self.user.mention} your payment for {self.item_name} was **rejected** by {staff}.\n"
            f"Please try `/confirm` again with a valid screenshot, or you shall be warned and your ticket terminated.\n"
            f"> `{self.queue_code}` (Order #{queue_number})."
        )
        try:
            await self.user.send(
                f"Your payment for **{self.item_name or 'your item'}** was rejected by {staff}.\n"
                f"Please try `/confirm` again with a valid screenshot, or you shall be warned and your ticket terminated.\n"
                f"> `{self.queue_code}` (Order #{queue_number})."
            )
        except discord.Forbidden:
            await self.ticket_channel.send(f"Couldn't DM {self.user.mention}")

        await self.update_staff_embed("Rejected", staff)
        await self.log_Stat("Rejected", staff)

    @discord.ui.button(label="Processing", style=discord.ButtonStyle.primary)
    async def processing(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff = interaction.user.display_name
        update_queue_status(self.queue_code, "processing")
        queue_number = get_queue_number_by_code(self.queue_code)
        await self.ticket_channel.send(
            f"{self.user.mention} your payment for {self.item_name} is now **being processed** by {staff}.\n"
            f"Please wait while your order is handled.\n"
            f"> `{self.queue_code}` (Order #{queue_number})."
        )
        try:
            await self.user.send(
                f"Your payment for **{self.item_name or 'your item'}** is now being processed by {staff}.\n"
                f"Please wait while your order is handled.\n"
                f"> `{self.queue_code}` (Order #{queue_number})."
            )
        except discord.Forbidden:
            await self.ticket_channel.send("Couldn't DM the user — they may have DMs disabled.")
        await self.update_staff_embed("Processing", staff)
        await self.log_Stat("Processing", staff)
        bot = interaction.client
        if hasattr(bot, "ticket_timeout_tasks"):
            task = bot.ticket_timeout_tasks.get(self.ticket_channel.id)
            if task:
                task.cancel()
                await self.ticket_channel.send("Ticket timeout has been removed. This ticket will remain open until manually archived.")

    @discord.ui.button(label="Terminate", style=discord.ButtonStyle.danger)
    async def Terminate(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff = interaction.user.display_name
        remove_queue_by_code(self.queue_code)
        await self.ticket_channel.send(
            f"{self.user.mention} your order has been **terminated** by {staff}. This ticket will now be archived."
        )
        await self.user.send(
            f"{self.user.mention} your order has been **terminated** by {staff}. This ticket will now be archived."
        )
        await self.update_staff_embed("Terminated", staff)
        await self.log_Stat("Terminated", staff)
        archive_category = discord.utils.get(self.ticket_channel.guild.categories, name=ARCHIVE_CATEGORY_NAME)
        if not archive_category:
            archive_category = await self.ticket_channel.guild.create_category(ARCHIVE_CATEGORY_NAME)
        await asyncio.sleep(5)
        await self.ticket_channel.edit(category=archive_category)
        await self.ticket_channel.set_permissions(self.user, overwrite=None)
        await self.ticket_channel.send("This ticket has been archived.")
        self.stop()

    @discord.ui.button(label="Jump to Ticket Channel", style=discord.ButtonStyle.blurple)
    async def jump_to_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"Jump to ticket channel: {self.ticket_channel.mention}", ephemeral=True
        )

class ItemButton(discord.ui.Button):

    def __init__(self, label, item_name, disabled, requester, bot):
        super().__init__(label=label, style=discord.ButtonStyle.primary, disabled=disabled)
        self.item_name = item_name
        self.requester = requester
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester.id:
            await interaction.response.send_message("Only use these buttons", ephemeral=True)
            return

        stock = l_JsonStock()
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
                await interaction.channel.send("Please choose an item again to restart your order.")
                return
            if item["stock"] < quantity:
                await interaction.channel.send(f"Not enough stock! Only {item['stock']} left.")
                await interaction.channel.send("Please choose an item again to restart your order.")
                return

            item["stock"] -= quantity
            s_JsonStock(stock)

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
            await interaction.channel.send("Timed out waiting for quantity. Please choose an item again to restart your order.")

class ItemSelectView(discord.ui.View):
    def __init__(self, requester: discord.User, bot: commands.Bot):
        super().__init__(timeout=None)
        self.requester = requester
        self.bot = bot
        self.stock = l_JsonStock()
        for name, data in self.stock.items():
            label = f"{name} - ₱{data['price']}"
            disabled = data["stock"] <= 0
            if disabled:
                label += " (Out of stock)"
            self.add_item(ItemButton(label, name, disabled, requester, bot))
        # Add staff-only terminate button
        self.add_item(TerminateChannelButton())

class TerminateChannelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Terminate", style=discord.ButtonStyle.danger, row=4)

    async def callback(self, interaction: discord.Interaction):
        # Only allow staff (with manage_channels or a specific role) to use this
        if not (interaction.user.guild_permissions.manage_channels or any(r.id == HANDLER_ROLE for r in getattr(interaction.user, "roles", []))):
            await interaction.response.send_message("You do not have permission to terminate this channel.", ephemeral=True)
            return
        channel = interaction.channel
        # Try to find the queue code from the channel name
        queue_code = None
        for q in l_qInfo():
            if q["user_id"] in [m.id for m in channel.members if not m.bot] and q["status"] in ("pending", "processing"):
                if q["code"] in channel.name:
                    queue_code = q["code"]
                    break
            elif q["code"] in channel.name:
                queue_code = q["code"]
                break
        # Remove from queue and reorder
        if queue_code:
            remove_queue_by_code(queue_code)
            # Log to staff log channel
            if channel.guild.get_channel(LOG_CHANNEL_ID):
                await channel.guild.get_channel(LOG_CHANNEL_ID).send(
                    f"Order `{queue_code}` was terminated by {interaction.user.mention} ({interaction.user.id}) in {channel.mention} at {get_timestamp()}"
                )
        archive_category = discord.utils.get(channel.guild.categories, name=ARCHIVE_CATEGORY_NAME)
        if not archive_category:
            archive_category = await channel.guild.create_category(ARCHIVE_CATEGORY_NAME)
        await channel.edit(category=archive_category)
        await channel.set_permissions(channel.guild.default_role, overwrite=None)
        await channel.send("This ticket has been terminated and archived by staff.")
        await interaction.response.send_message("Channel has been terminated and archived.", ephemeral=True)
        
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

        # Check if user already has an active ticket channel
        base_channel_name = requester.name.lower().replace(" ", "-") + "s-ticket"
        for ch in category.text_channels:
            # Only consider channels where the user is the only non-bot member with send permissions
            perms = ch.overwrites_for(requester)
            if ch.name.startswith(base_channel_name) and perms.view_channel and perms.send_messages:
                return

        # Use dynamic queue string instead of numeric
        queue_code = genQcode()
        queue_number = register_queue(context.author.id, queue_code)

        channel_name = base_channel_name + "-" + queue_code
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            requester: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        newTicketChan = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Ticket channel for {requester}"
        )

        # Remove notify_channel logic, just send ephemeral message in persistent message channel
        persistent_channel = guild.get_channel(PERSISTENT_MESSAGE_CHANNEL_ID)
        if persistent_channel:
            try:
                await context.send(
                    f"{requester.mention}, your ticket channel is {newTicketChan.mention} (Queue `{queue_code}` / Order #{queue_number})",
                    delete_after=2
                )
            except Exception:
                pass

        stock = l_JsonStock()
        embed = discord.Embed(
            title=f"{requester.display_name}, your order ticket has been created! Please select an item below to start your order.",
            color=0xEAEBD0
        )
        for name, data in stock.items():
            embed.add_field(
                name=f"{name} - ₱{data['price']}",
                value=data.get('description', 'No description'),
                inline=True
            )
        embed.add_field(
            name="Order Instructions",
            value=f"{requester.name}, send payment to `{GCASH_NUMBER}` after choosing below.\nThis ticket will explode in 15 minutes.\n`{queue_code}` (Order #{queue_number})",
            inline=False
        )
        await newTicketChan.send(
            embed=embed,
            view=ItemSelectView(requester, self.bot)
        )

        await newTicketChan.send(file=discord.File("assets/QR.jpg"))
        # Store queue code for later use in confirm
        if not hasattr(self.bot, "queue_numbers"):
            self.bot.queue_numbers = {}
        self.bot.queue_numbers[requester.id] = queue_code

        # Store the asyncio task for timeout so it can be cancelled
        async def ticket_timeout():
            await asyncio.sleep(TICKET_TIMEOUT)
            # await newTicketChan.delete(reason="Ticket expired")
            # ito ang problema 

        if not hasattr(self.bot, "ticket_timeout_tasks"):
            self.bot.ticket_timeout_tasks = {}
        self.bot.ticket_timeout_tasks[newTicketChan.id] = asyncio.create_task(ticket_timeout())

    #/confirm
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
        log_channel = ctx.guild.get_channel(LOG_CHANNEL_ID)
        if staff_channel:
            role_mention = f"<@&{HANDLER_ROLE}>" # ORDER HANDLER ROLE ID
            embed = discord.Embed(
                title=f"(#{queue_number}) [{queue_code}] {requester.display_name}'s {quantity}x {item_name}",
                description=
                (
                    f"`{queue_code}` (Order #{queue_number})\n"
                    "\n"
                    f"Client: {requester.mention}\n"
                    f"Channel: {ctx.channel.mention}\n"
                    "\n"
                    f"Item: **{item_name}**\n"
                    f"Quantity: **x{quantity}**\n"
                    f"Total: **₱{total_price}**\n"
                ),
                color=discord.Color.light_grey()
            )
            embed.set_thumbnail(url=requester.display_avatar.url)
            embed.set_footer(text=f"Requested by {requester.display_name} ({requester.id})")
            embed.add_field(
                name="Status",
                value=f"Pending {get_timestamp()}",
                inline=False
            )
            embed.set_image(url=image_url)
            staff_msg = await staff_channel.send(
                embed=embed,
                view=ConfirmPaymentView(requester, ctx.channel, image_url, item_name, queue_code, staff_message=None),
                content=role_mention
            )
            # Pass staff_msg to ConfirmPaymentView for editing
            view = ConfirmPaymentView(requester, ctx.channel, image_url, item_name, queue_code, staff_message=staff_msg)
            await staff_msg.edit(view=view)
            await ctx.reply("Screenshot sent to the staff for confirmation.")
            if log_channel:
                await log_channel.send(
                    f"Order `{queue_code}` (Order #{queue_number}) created by {requester.display_name} {get_timestamp()}"
                )
        else:
            await ctx.reply("Couldn't find the staff channel.")

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketButtonView(self.bot))
        # Start the archive expired tickets task only once
        if not hasattr(self.bot, "_archive_expired_tickets_started"):
            self.bot.loop.create_task(archive_expired_tickets(self.bot))
            self.bot._archive_expired_tickets_started = True
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
                    "• **Do not ping staff** repeatedly"
                ),
                color=0xFDAEAE
            )
            embed.set_footer(text=f"Created by **永恆的王**")
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

async def setup(bot) -> None:
    await bot.add_cog(Cashmoney(bot))