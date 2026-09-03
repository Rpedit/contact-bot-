import os
import re
import sqlite3
import asyncio
import logging
from datetime import datetime
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID, START_VIDEO, BUTTON_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

OWNER_ID = int(ADMIN_ID)
DB_FILE = "bot.db"
msg_map = {}

# ================= 1. Local Database ================= #
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            joined_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_user(user_id: int, name: str, username: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)",
        (user_id, name, username, datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def is_banned(user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM bans WHERE user_id = ?", (user_id,))
    res = c.fetchone() is not None
    conn.close()
    return res

def ban_user(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO bans VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ================= 2. Bot Instance ================= #
app = Client("support_contact_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

PRIVACY_TEXT = (
    "🔒 **Privacy & Data Policy**\n\n"
    "• **Data Collected:** User ID, Name, aur Username sirf message relay service ke liye save kiya jata hai.\n"
    "• **Relay Function:** User ka message directly support admin tak deliver hota hai.\n"
    "• **Security:** Aapka personal data kisi third-party ko share ya sell nahi kiya jata."
)

async def auto_delete(msg: Message, delay: int = 3):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


# ================= 3. Message Handlers ================= #
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user = message.from_user
    save_user(user.id, user.first_name, user.username or "")

    caption_text = (
        f"HEY 👤 [**{user.first_name}**](tg://user?id={user.id}),\n\n"
        f"Welcome to our **Support & Contact Bot**!\n\n"
        f"💬 Aap apna koi bhi message, sawaal ya suggestion yahan type karke bhej sakte hain."
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Channel / Updates ↗", url=BUTTON_URL)],
        [InlineKeyboardButton("🔒 Privacy Policy", callback_data="show_privacy")],
    ])

    try:
        await message.reply_video(video=START_VIDEO, caption=caption_text, reply_markup=buttons)
    except Exception:
        try:
            await message.reply_animation(animation=START_VIDEO, caption=caption_text, reply_markup=buttons)
        except Exception:
            await message.reply_text(text=caption_text, reply_markup=buttons)


@app.on_message(filters.command("privacy") & filters.private)
async def privacy_handler(client: Client, message: Message):
    await message.reply_text(PRIVACY_TEXT)


@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    if query.data == "show_privacy":
        await query.message.reply_text(PRIVACY_TEXT)
        await query.answer()
    else:
        await query.answer()


# ================= 4. Admin Management Commands ================= #
@app.on_message(filters.command("stats") & filters.private & filters.user(OWNER_ID))
async def stats_handler(client: Client, message: Message):
    users = get_all_users()
    await message.reply_text(
        f"📊 **Bot Analytics**\n\n"
        f"👑 **Admin:** `{OWNER_ID}`\n"
        f"👥 **Total Users:** `{len(users)}`"
    )


@app.on_message(filters.command("broadcast") & filters.private & filters.user(OWNER_ID))
async def broadcast_handler(client: Client, message: Message):
    if not message.reply_to_message and len(message.command) < 2:
        return await message.reply_text("⚠️ Message par reply karke `/broadcast` likhein ya text type karein.")

    users = get_all_users()
    status = await message.reply_text(f"🚀 Broadcasting to `{len(users)}` users...")
    success = 0

    for uid in users:
        try:
            if message.reply_to_message:
                await message.reply_to_message.copy(chat_id=uid)
            else:
                await client.send_message(chat_id=uid, text=message.text.split(None, 1)[1])
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await status.edit_text(f"✅ **Broadcast Finished!** Delivered: `{success}/{len(users)}`")


@app.on_message(filters.command("ban") & filters.private & filters.user(OWNER_ID))
async def ban_handler(client: Client, message: Message):
    target = None
    if len(message.command) > 1 and message.command[1].isdigit():
        target = int(message.command[1])
    elif message.reply_to_message and message.reply_to_message.id in msg_map:
        target = msg_map[message.reply_to_message.id]

    if target:
        ban_user(target)
        await message.reply_text(f"🚫 User `[{target}]` ko block/ban kar diya gaya.")
    else:
        await message.reply_text("⚠️ User ID dein ya forwarded card par reply karein.")


@app.on_message(filters.command("unban") & filters.private & filters.user(OWNER_ID))
async def unban_handler(client: Client, message: Message):
    target = int(message.command[1]) if len(message.command) > 1 and message.command[1].isdigit() else None
    if target:
        unban_user(target)
        await message.reply_text(f"✅ User `[{target}]` unban ho gaya.")
    else:
        await message.reply_text("⚠️ Valid user ID enter karein: `/unban 123456789`")


# ================= 5. Relay System (User <-> Admin) ================= #
@app.on_message(filters.private & ~filters.user(OWNER_ID) & ~filters.command(["start", "privacy"]))
async def user_to_admin(client: Client, message: Message):
    user = message.from_user
    if is_banned(user.id):
        notice = await message.reply_text("🚫 **Aapko is bot par block kiya gaya hai.**")
        return asyncio.create_task(auto_delete(notice, 4))

    try:
        fwd = await message.forward(OWNER_ID)
        msg_map[fwd.id] = user.id
    except Exception as e:
        return logger.error(f"Forward error: {e}")

    info_text = (
        f"📢 **Message from {user.first_name}!!**\n"
        f"[{user.id}](tg://user?id={user.id}) #id{user.id}\n\n"
        f"👉 Reply to this message to answer."
    )
    profile_url = f"https://t.me/{user.username}" if user.username else f"tg://openmessage?user_id={user.id}"
    card = await client.send_message(
        chat_id=OWNER_ID,
        text=info_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 User Profile", url=profile_url)]]),
        disable_web_page_preview=True,
    )
    msg_map[card.id] = user.id

    confirm = await message.reply_text("Message sent! ⏱️")
    asyncio.create_task(auto_delete(confirm, 3))


@app.on_message(filters.private & filters.user(OWNER_ID) & filters.reply)
async def admin_reply(client: Client, message: Message):
    target = msg_map.get(message.reply_to_message.id)
    if not target and message.reply_to_message.text:
        match = re.search(r"#id(\d+)", message.reply_to_message.text)
        if match:
            target = int(match.group(1))

    if target:
        try:
            await message.copy(chat_id=target)
            try:
                await client.send_reaction(chat_id=OWNER_ID, message_id=message.id, emoji="👍")
            except Exception:
                pass
        except Exception as e:
            await message.reply_text(f"❌ Send fail: `{e}`")
    else:
        await message.reply_text("⚠️ User ID nahi mili. User card ya forwarded message par reply karein.")


@app.on_message(
    filters.private
    & filters.user(OWNER_ID)
    & ~filters.reply
    & ~filters.command(["start", "privacy", "stats", "broadcast", "ban", "unban"])
)
async def no_reply_warning(client: Client, message: Message):
    alert = await message.reply_text("⚠️ _Reply to a forwarded message to send a message to that user._")
    asyncio.create_task(auto_delete(alert, delay=4))


# ================= 6. Web Server & Lifecycle ================= #
async def web_handler(request):
    return web.Response(text="Support Relay Bot is Running 24/7!")

async def main():
    server = web.Application()
    server.router.add_get("/", web_handler)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()

    await app.start()

    # Normal users: Only /start in menu
    await app.set_bot_commands(
        [BotCommand("start", "🤖 Start Bot")],
        scope=BotCommandScopeAllPrivateChats()
    )

    # Admin: Private admin commands
    await app.set_bot_commands(
        [
            BotCommand("start", "🤖 Restart Bot"),
            BotCommand("stats", "📊 Live Stats"),
            BotCommand("broadcast", "📢 Broadcast"),
            BotCommand("ban", "🚫 Ban User"),
            BotCommand("unban", "✅ Unban User"),
            BotCommand("privacy", "🔒 Privacy Policy"),
        ],
        scope=BotCommandScopeChat(chat_id=OWNER_ID)
    )

    logger.info("Bot is active and running!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
