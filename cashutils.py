import json
import os
import random
import string
import time
import asyncio

STOCK_FILE = "stock.json"
QUEUE_INFO_FILE = "queue_info.json"
TICKET_CATEGORY_NAME = "Active Tickets"
ARCHIVE_CATEGORY_NAME = "Archive"
LOG_CHANNEL_ID = 1399302081155698750

def l_JsonStock():
    print("Loading stock from", STOCK_FILE)
    if not os.path.exists(STOCK_FILE):
        return {}
    with open(STOCK_FILE, "r") as f:
        return json.load(f)

def s_JsonStock(stock):
    print("Savinf stock from", STOCK_FILE)
    if not os.path.exists(STOCK_FILE):
        return {}
    with open(STOCK_FILE, "w") as f:
        json.dump(stock, f, indent=4)

def l_qInfo():
    if not os.path.exists(QUEUE_INFO_FILE):
        return []
    with open(QUEUE_INFO_FILE, "r") as f:
        return json.load(f)

def s_qInfo(queue_info):
    with open(QUEUE_INFO_FILE, "w") as f:
        json.dump(queue_info, f, indent=4)

def genQcode():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=6))

def get_next_queue_number():
    queue_info = l_qInfo()
    return len(queue_info) + 1

def register_queue(user_id, code, status="pending"):
    queue_info = l_qInfo()
    if any(q["code"] == code for q in queue_info):
        return register_queue(user_id, genQcode(), status)
    used_numbers = {q["number"] for q in queue_info}
    number = 1
    while number in used_numbers:
        number += 1
    queue_info.append({
        "code": code,
        "number": number,
        "user_id": user_id,
        "status": status,
        "created_at": int(time.time()),
        "last_confirm": None
    })
    s_qInfo(queue_info)
    return number

def remove_queue_by_code(code):
    queue_info = l_qInfo()
    removed_number = None
    for q in queue_info:
        if q["code"] == code:
            removed_number = q["number"]
            break
    if removed_number is None:
        return
    queue_info = [q for q in queue_info if q["code"] != code]
    for q in queue_info:
        if q["number"] > removed_number:
            q["number"] -= 1
    s_qInfo(queue_info)

def update_queue_status(code, status):
    queue_info = l_qInfo()
    for q in queue_info:
        if q["code"] == code:
            q["status"] = status
            break
    s_qInfo(queue_info)

def update_queue_last_confirm(code):
    queue_info = l_qInfo()
    for q in queue_info:
        if q["code"] == code:
            q["last_confirm"] = int(time.time())
            break
    s_qInfo(queue_info)

def get_queue_number_by_code(code):
    queue_info = l_qInfo()
    for q in queue_info:
        if q["code"] == code:
            return q["number"]
    return None

def get_queue_status_by_code(code):
    queue_info = l_qInfo()
    for q in queue_info:
        if q["code"] == code:
            return q["status"]
    return "pending"

def get_queue_last_confirm_by_code(code):
    queue_info = l_qInfo()
    for q in queue_info:
        if q["code"] == code:
            return q.get("last_confirm")
    return None

def get_timestamp():
    return f"<t:{int(time.time())}:R>"

async def archive_expired_tickets(bot):
    await bot.wait_until_ready()
    while True:
        now = int(time.time())
        queue_info = l_qInfo()
        expired_codes = []
        for q in queue_info:
            if q.get("status") not in ("pending", "processing"):
                continue
            last_confirm = q.get("last_confirm")
            created_at = q.get("created_at", now)
            last_activity = last_confirm if last_confirm else created_at
            if now - last_activity > 3 * 24 * 60 * 60:
                expired_codes.append(q["code"])
        for code in expired_codes:
            for guild in bot.guilds:
                category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
                if not category:
                    continue
                for channel in category.text_channels:
                    if code in channel.name:
                        archive_category = discord.utils.get(guild.categories, name=ARCHIVE_CATEGORY_NAME)
                        if not archive_category:
                            archive_category = await guild.create_category(ARCHIVE_CATEGORY_NAME)
                        try:
                            await channel.edit(category=archive_category)
                            await channel.set_permissions(guild.default_role, overwrite=None)
                            await channel.send("This ticket has been archived due to inactivity (no /confirm for 3 days).")
                        except Exception as e:
                            # Log or print error if needed
                            pass
                        break
            remove_queue_by_code(code)
        await asyncio.sleep(3600)
