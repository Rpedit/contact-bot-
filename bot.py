import os
import re
import html
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
from pyrogram.errors import (
    UserIsBlocked,
    InputUserDeactivated,
    UserDeactivated,
    UserDeactivatedBan,
)

try:
    from pyrogram.enums import ParseMode
except ImportError:
    class ParseMode:
        HTML = "html"
        MARKDOWN = "markdown"

from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID, START_VIDEO, BUTTON_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

OWNER_ID = int(ADMIN_ID)
DB_FILE = "bot.db"
msg_map = {}

# ================= 1. Local Database (SQLite) ================= #
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


# ================= 2. Bot Instance & Filters ================= #
app = Client("support_contact_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

PRIVACY_TEXT = (
    "🔒 **Privacy & Data Policy**\n\n"
    "• **Data Collected:** User ID, Name, aur Username safe message relay provide karne ke liye store hota hai.\n"
    "• **Relay Function:** User ka message directly support admin tak deliver hota hai.\n"
    "• **Security:** Data kisi third-party ke sath share ya sell nahi kiya jata."
)

# Adult & 18+ Keywords / Domains Filter
ADULT_REGEX = re.compile(
    r"(?i)\b(porn|xxx|sex|sexy|adult|nude|nudes|nsfw|boobs|dick|pussy|hentai|erotic|"
    r"xvideos|pornhub|xhamster|xnxx|brazzers|stripchat|onlyfans|chaturbate|redtube|"
    r"spankbang|chut|gand|lund|chudai|bhosda|mms)\b|"
    r"(https?:\/\/[^\s]*(xxx|porn|sex|xnxx|xvideos|adult)[^\s]*)"
)

def is_adult_content(text: str) -> bool:
    if not text:
        return False
    return bool(ADULT_REGEX.search(text))

async def auto_delete(msg: Message, delay: int = 3):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

def extract_target_user(message: Message) -> int | None:
    """Command argument, reply, forward ya card text se target user ID nikalta hai"""
    if len(message.command) > 1 and message.command[1].isdigit():
        return int(message.command[1])

    if message.reply_to_message:
        rep = message.reply_to_message
        if rep.id in msg_map:
            return msg_map[rep.id]
        if rep.forward_from:
            return rep.forward_from.id
        raw_text = rep.text or rep.caption or ""
        match = re.search(r"#id(\d+)", raw_text)
        if match:
            return int(match.group(1))

    return None


# ================= 3. Message Handlers ================= #
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user = message.from_user
    save_user(user.id, user.first_name, user.username or "")

    caption_text = (
        f"HEY 👤 [{user.first_name}](tg://user?id={user.id}),\n\n"
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


# ================= 4. Admin Commands ================= #
@app.on_message(filters.command("stats") & filters.private & filters.user(OWNER_ID))
async def stats_handler(client: Client, message: Message):
    users = get_all_users()
    await message.reply_text(
        f"📊 **Bot Analytics**\n\n"
        f"👑 **Admin:** `{OWNER_ID}`\n"
        f"👥 **Total Registered Users:** `{len(users)}`"
    )


# --- Broadcast with Interactive PIN Option ---
@app.on_message(filters.command("broadcast") & filters.private & filters.user(OWNER_ID))
async def broadcast_prompt(client: Client, message: Message):
    if not message.reply_to_message:
        return await message.reply_text(
            "⚠️ **Format:** Jis message ko broadcast karna hai uspar reply karke `/broadcast` likhein."
        )

    target_msg_id = message.reply_to_message.id
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 Normal Broadcast", callback_data=f"bcast_norm_{target_msg_id}"),
            InlineKeyboardButton("📌 Broadcast & PIN", callback_data=f"bcast_pin_{target_msg_id}")
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="bcast_cancel")]
    ])

    await message.reply_text(
        "📢 **Broadcast Confirmation:**\n\n"
        "Aap is message ko normal bhejna chahte hain ya sabhi users ke chat me **PIN** bhi karna chahte hain?",
        reply_markup=buttons
    )


# --- Reply to Ban / Unban ---
@app.on_message(filters.command("ban") & filters.private & filters.user(OWNER_ID))
async def ban_handler(client: Client, message: Message):
    target = extract_target_user(message)
    if target:
        ban_user(target)
        await message.reply_text(f"🚫 User `[{target}]` ko **Ban** kar diya gaya.")
    else:
        await message.reply_text("⚠️ User ke message ya card par reply karke `/ban` likhein ya ID dein.")


@app.on_message(filters.command("unban") & filters.private & filters.user(OWNER_ID))
async def unban_handler(client: Client, message: Message):
    target = extract_target_user(message)
    if target:
        unban_user(target)
        await message.reply_text(f"✅ User `[{target}]` ko **Unban** kar diya gaya.")
    else:
        await message.reply_text("⚠️ User ke message ya card par reply karke `/unban` likhein ya ID dein.")


# ================= 5. Callback Queries (Broadcast & Privacy) ================= #
@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    data = query.data

    if data == "show_privacy":
        await query.message.reply_text(PRIVACY_TEXT)
        return await query.answer()

    if data == "bcast_cancel":
        await query.message.delete()
        return await query.answer("Broadcast cancel kar diya gaya.", show_alert=True)

    if data.startswith("bcast_norm_") or data.startswith("bcast_pin_"):
        should_pin = data.startswith("bcast_pin_")
        target_msg_id = int(data.split("_")[-1])

        await query.message.delete()
        users = get_all_users()
        status = await client.send_message(
            chat_id=OWNER_ID,
            text=f"🚀 Broadcasting message to `{len(users)}` users... (Pin: **{should_pin}**)"
        )

        success, pinned, failed = 0, 0, 0
        for uid in users:
            try:
                sent = await client.copy_message(chat_id=uid, from_chat_id=OWNER_ID, message_id=target_msg_id)
                success += 1
                if should_pin:
                    try:
                        await client.pin_chat_message(chat_id=uid, message_id=sent.id, both_sides=True)
                        pinned += 1
                    except Exception:
                        pass
                await asyncio.sleep(0.05)
            except Exception:
                failed += 1

        result_text = (
            f"✅ **Broadcast Completed!**\n\n"
            f"👥 **Total Users:** `{len(users)}`\n"
            f"🟢 **Delivered:** `{success}`\n"
            f"📌 **Pinned:** `{pinned}`\n"
            f"🔴 **Failed:** `{failed}`"
        )
        await status.edit_text(result_text)
        return await query.answer()

    await query.answer()


# ================= 6. Relay System ================= #
@app.on_message(filters.private & ~filters.user(OWNER_ID) & ~filters.command(["start", "privacy"]))
async def user_to_admin(client: Client, message: Message):
    user = message.from_user

    # Ban check
    if is_banned(user.id):
        notice = await message.reply_text("🚫 **Aapko is bot par block kiya gaya hai.**")
        return asyncio.create_task(auto_delete(notice, 4))

    # Adult content / link filter
    content_text = message.text or message.caption or ""
    if is_adult_content(content_text):
        try:
            await message.delete()
        except Exception:
            pass

        warning_alert = await client.send_message(
            chat_id=user.id,
            text=(
                "⚠️ **WARNING / चेतावनी!**\n\n"
                "Adult / 18+ links ya gandi content bhejna strictly **BANNED** hai.\n"
                "Aapka message delete kar diya gaya hai. Dobara karne par block kar diya jayega!"
            )
        )
        return asyncio.create_task(auto_delete(warning_alert, delay=6))

    try:
        fwd = await message.forward(OWNER_ID)
        msg_map[fwd.id] = user.id
    except Exception as e:
        return logger.error(f"Forward error: {e}")

    # Sirf forward-hidden / private users par card aur button aayega
    if not fwd.forward_from:
        profile_url = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user.id}"
        profile_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 User profile", url=profile_url)]
        ])

        # Screenshot jaisa exact formatting: Name plain aur ID bracket ke andar GREEN link
        safe_name = html.escape(user.first_name or "User")
        info_text = (
            f"👆 Message sent by {safe_name}\n"
            f"<a href=\"tg://user?id={user.id}\">[{user.id}]</a> #id{user.id}\n"
            f"👉 To answer, reply to this message."
        )

        try:
            card = await client.send_message(
                chat_id=OWNER_ID,
                text=info_text,
                reply_to_message_id=fwd.id,
                disable_web_page_preview=True,
                reply_markup=profile_button,
                parse_mode=ParseMode.HTML,
            )
            msg_map[card.id] = user.id
        except Exception as e:
            logger.error(f"Card error: {e}")

    confirm = await message.reply_text("Message sent! ⏱️")
    asyncio.create_task(auto_delete(confirm, 3))


# --- Admin Reply to User ---
@app.on_message(filters.private & filters.user(OWNER_ID) & filters.reply)
async def admin_reply(client: Client, message: Message):
    if message.text and message.text.startswith(("/ban", "/unban", "/broadcast", "/stats")):
        return

    target = msg_map.get(message.reply_to_message.id)
    if not target and message.reply_to_message.forward_from:
        target = message.reply_to_message.forward_from.id
    if not target:
        raw_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        match = re.search(r"#id(\d+)", raw_text)
        if match:
            target = int(match.group(1))

    if target:
        try:
            await message.copy(chat_id=target)
            try:
                await client.send_reaction(chat_id=OWNER_ID, message_id=message.id, emoji="👍")
            except Exception:
                pass

            confirm = await message.reply_text("Message sent! ⏱️")
            asyncio.create_task(auto_delete(confirm, 3))

        except (UserIsBlocked, InputUserDeactivated, UserDeactivated, UserDeactivatedBan):
            await message.reply_text(
                "❌ Message not sent!\n"
                "The user blocked the bot or deleted the account."
            )
        except Exception as e:
            await message.reply_text(f"❌ Send fail: `{e}`")
    else:
        await message.reply_text("⚠️ User ID nahi mili. User card ya message par reply karein.")


# --- Non-Reply Alert ---
@app.on_message(
    filters.private
    & filters.user(OWNER_ID)
    & ~filters.reply
    & ~filters.command(["start", "privacy", "stats", "broadcast", "ban", "unban"])
)
async def no_reply_warning(client: Client, message: Message):
    alert = await message.reply_text("⚠️ Reply to a forwarded message to send a message to that user.")
    asyncio.create_task(auto_delete(alert, delay=4))


# ================= 7. Web Server & Lifecycle ================= #
async def web_handler(request):
    return web.Response(text="Support Relay Bot is Active 24/7!")

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

    # Admin commands list
    await app.set_bot_commands(
        [
            BotCommand("start", "🤖 Restart Bot"),
            BotCommand("stats", "📊 Live Stats"),
            BotCommand("broadcast", "📢 Broadcast with PIN"),
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
