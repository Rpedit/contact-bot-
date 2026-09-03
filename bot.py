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
    BotCommandScopeChat,
    BotCommandScopeAllPrivateChats,
)
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID, START_VIDEO, BUTTON_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MASTER_ADMIN = int(ADMIN_ID)
active_clients = []
DB_FILE = "clones.db"

# ================= 1. SQLite Storage ================= #
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS clones (
            token TEXT PRIMARY KEY,
            owner_id INTEGER,
            start_text TEXT,
            support_group_id INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_users (
            token TEXT,
            user_id INTEGER,
            first_name TEXT,
            username TEXT,
            joined_at TEXT,
            PRIMARY KEY (token, user_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            token TEXT,
            keyword TEXT,
            content TEXT,
            PRIMARY KEY (token, keyword)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            token TEXT,
            user_id INTEGER,
            PRIMARY KEY (token, user_id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

def db_save_user(token: str, user_id: int, name: str, username: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO bot_users VALUES (?, ?, ?, ?, ?)",
        (token, user_id, name, username, datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    conn.close()

def db_get_users(token: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM bot_users WHERE token = ?", (token,))
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def db_set_start(token: str, text: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE clones SET start_text = ? WHERE token = ?", (text, token))
    conn.commit()
    conn.close()

def db_get_start(token: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT start_text FROM clones WHERE token = ?", (token,))
    res = c.fetchone()
    conn.close()
    return res[0] if res and res[0] else None

def db_set_group(token: str, chat_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE clones SET support_group_id = ? WHERE token = ?", (chat_id, token))
    conn.commit()
    conn.close()

def db_get_group(token: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT support_group_id FROM clones WHERE token = ?", (token,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else 0

def db_add_template(token: str, keyword: str, content: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO templates VALUES (?, ?, ?)", (token, keyword.lower(), content))
    conn.commit()
    conn.close()

def db_get_template(token: str, keyword: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT content FROM templates WHERE token = ? AND keyword = ?", (token, keyword.lower()))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

def db_ban_user(token: str, user_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO bans VALUES (?, ?)", (token, user_id))
    conn.commit()
    conn.close()

def db_unban_user(token: str, user_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM bans WHERE token = ? AND user_id = ?", (token, user_id))
    conn.commit()
    conn.close()

def db_is_banned(token: str, user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM bans WHERE token = ? AND user_id = ?", (token, user_id))
    banned = c.fetchone() is not None
    conn.close()
    return banned


# ================= 2. Helpers & Scoped Commands ================= #
async def auto_delete(msg: Message, delay: int = 3):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

async def set_modular_commands(client: Client, owner_id: int):
    try:
        # Users menu: Only Start & Privacy policy
        await client.set_bot_commands(
            [
                BotCommand("start", "🤖 Start Bot"),
                BotCommand("privacy", "🔒 Privacy & Policy"),
            ],
            scope=BotCommandScopeAllPrivateChats(),
        )
        # Admin menu: Full control commands
        await client.set_bot_commands(
            [
                BotCommand("admin", "👑 Control Center"),
                BotCommand("stats", "📊 Live Stats"),
                BotCommand("setstart", "✏️ Edit Welcome Text"),
                BotCommand("setgroup", "👥 Link Support Group"),
                BotCommand("template", "⚡ Add Quick Template"),
                BotCommand("broadcast", "📢 Send Message to All"),
                BotCommand("ban", "🚫 Ban User"),
                BotCommand("unban", "✅ Unban User"),
                BotCommand("start", "🤖 Restart Bot"),
            ],
            scope=BotCommandScopeChat(chat_id=owner_id),
        )
    except Exception as e:
        logger.warning(f"Scoped commands warning: {e}")

PRIVACY_TEXT = (
    "🔒 **ModularBot Privacy & Data Policy**\n\n"
    "• **Data Collected:** User ID, Name, aur Username sirf service operate karne ke liye save hota hai.\n"
    "• **Relay Function:** User ke messages directly bot owner ya unke support group tak deliver hote hain.\n"
    "• **GDPR Rights:** Aap apna account data delete karwane ke liye kisi bhi waqt owner se request kar sakte hain.\n"
    "• **Third-Party Sharing:** Aapka personal data kisi company ya advertiser ke sath share nahi kiya jata."
)


# ================= 3. Core Handler Engine ================= #
def setup_modular_handlers(bot: Client, owner_id: int, bot_token: str):
    msg_map = {}

    @bot.on_message(filters.command("privacy") & filters.private)
    async def privacy_cmd(client: Client, message: Message):
        await message.reply_text(PRIVACY_TEXT)

    @bot.on_message(filters.command("start") & filters.private)
    async def start_cmd(client: Client, message: Message):
        user = message.from_user
        db_save_user(bot_token, user.id, user.first_name, user.username or "")
        custom_text = db_get_start(bot_token)

        if not custom_text:
            custom_text = (
                f"HEY 👤 [**{user.first_name}**](tg://user?id={user.id}),\n\n"
                f"Welcome to our Support & Contact Bot!\n"
                f"Aap apna koi bhi message yahan bhej sakte hain."
            )

        user_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ Channel / Updates ↗", url=BUTTON_URL)],
            [InlineKeyboardButton("🔒 Privacy Policy", callback_data="show_privacy")],
        ])

        try:
            await message.reply_video(video=START_VIDEO, caption=custom_text, reply_markup=user_buttons)
        except Exception:
            await message.reply_text(text=custom_text, reply_markup=user_buttons)

        if user.id == owner_id:
            admin_panel = (
                "👑 **ModularBot Administrator Setup**\n\n"
                "• `/setstart <text>` - Naya start message set karein\n"
                "• `/setgroup` - Messages group me mangwane ke liye support group me type karein\n"
                "• `/template <word> <reply>` - Quick template banayein\n"
                "• `/broadcast` - Sabhi users ko ek message forward karein\n"
                "• `/admin` - Current statistics check karein"
            )
            await message.reply_text(admin_panel)

    @bot.on_message(filters.command("setstart") & filters.private & filters.user(owner_id))
    async def set_start_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            return await message.reply_text("⚠️ **Format:** `/setstart Welcome to my bot! Type your message.`")
        new_text = message.text.split(None, 1)[1]
        db_set_start(bot_token, new_text)
        await message.reply_text("✅ **Custom Start Message update ho gaya!**")

    @bot.on_message(filters.command("setgroup") & filters.group)
    async def link_group_cmd(client: Client, message: Message):
        if message.from_user.id != owner_id:
            return await message.reply_text("⛔ Sirf bot owner ye command use kar sakta hai.")
        db_set_group(bot_token, message.chat.id)
        await message.reply_text(f"✅ **Linked!** Ab users ke saare messages is group me aayenge.")

    @bot.on_message(filters.command("template") & filters.private & filters.user(owner_id))
    async def template_cmd(client: Client, message: Message):
        if len(message.command) < 3:
            return await message.reply_text("⚠️ **Format:** `/template hi Hello! Main aapki kya madad kar sakta hoon?`")
        keyword = message.command[1]
        content = message.text.split(None, 2)[2]
        db_add_template(bot_token, keyword, content)
        await message.reply_text(f"✅ Template `# {keyword}` save ho gaya! Reply me `#{keyword}` likhne par ye send hoga.")

    @bot.on_message(filters.command(["admin", "stats"]) & filters.private & filters.user(owner_id))
    async def stats_cmd(client: Client, message: Message):
        users = db_get_users(bot_token)
        group_id = db_get_group(bot_token)
        panel = (
            "📊 **Modular Clone Analytics**\n\n"
            f"👤 **Owner ID:** `{owner_id}`\n"
            f"👥 **Total Users:** `{len(users)}`\n"
            f"🏢 **Support Route:** `{group_id if group_id != 0 else 'Direct Private DM'}`\n\n"
            "💬 User ko jawab dene ke liye uske message ya card par **Reply** karein."
        )
        await message.reply_text(panel)

    @bot.on_message(filters.command("broadcast") & filters.private & filters.user(owner_id))
    async def broadcast_cmd(client: Client, message: Message):
        if not message.reply_to_message and len(message.command) < 2:
            return await message.reply_text("⚠️ Message par reply karke `/broadcast` likhein.")

        users = db_get_users(bot_token)
        status = await message.reply_text(f"🚀 Broadcasting message to `{len(users)}` users...")
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

        await status.edit_text(f"✅ **Broadcast Done!** `{success}/{len(users)}` users tak pahunch gaya.")

    @bot.on_message(filters.command("ban") & (filters.private | filters.group))
    async def ban_cmd(client: Client, message: Message):
        if message.from_user.id != owner_id:
            return
        target_id = None
        if len(message.command) > 1 and message.command[1].isdigit():
            target_id = int(message.command[1])
        elif message.reply_to_message and message.reply_to_message.id in msg_map:
            target_id = msg_map[message.reply_to_message.id]

        if target_id:
            db_ban_user(bot_token, target_id)
            await message.reply_text(f"🚫 User `[{target_id}]` ban ho gaya.")
        else:
            await message.reply_text("⚠️ User ID enter karein ya card par reply karein.")

    @bot.on_message(filters.command("unban") & (filters.private | filters.group))
    async def unban_cmd(client: Client, message: Message):
        if message.from_user.id != owner_id:
            return
        target_id = int(message.command[1]) if len(message.command) > 1 and message.command[1].isdigit() else None
        if target_id:
            db_unban_user(bot_token, target_id)
            await message.reply_text(f"✅ User `[{target_id}]` unban ho gaya.")
        else:
            await message.reply_text("⚠️ Valid user ID enter karein.")

    @bot.on_callback_query()
    async def callback_query(client: Client, query: CallbackQuery):
        if query.data == "show_privacy":
            await query.message.reply_text(PRIVACY_TEXT)
            await query.answer()
        else:
            await query.answer()

    # --- User Messages (Relay to Owner or Linked Group) ---
    @bot.on_message(filters.private & ~filters.user(owner_id) & ~filters.command(["start", "privacy"]))
    async def forward_relay(client: Client, message: Message):
        user = message.from_user
        if db_is_banned(bot_token, user.id):
            notice = await message.reply_text("🚫 **Aapko is bot par block kiya gaya hai.**")
            return asyncio.create_task(auto_delete(notice, 4))

        destination_chat = db_get_group(bot_token)
        if destination_chat == 0:
            destination_chat = owner_id

        try:
            fwd = await message.forward(destination_chat)
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
            chat_id=destination_chat,
            text=info_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 User Profile", url=profile_url)]]),
            disable_web_page_preview=True,
        )
        msg_map[card.id] = user.id

        confirm = await message.reply_text("Message sent! ⏱️")
        asyncio.create_task(auto_delete(confirm, 3))

    # --- Admin Reply & Quick Template Expansion ---
    @bot.on_message((filters.private | filters.group) & filters.reply)
    async def reply_relay(client: Client, message: Message):
        if message.chat.type == "private" and message.from_user.id != owner_id:
            return

        target_id = msg_map.get(message.reply_to_message.id)
        if not target_id and message.reply_to_message.text:
            match = re.search(r"#id(\d+)", message.reply_to_message.text)
            if match:
                target_id = int(match.group(1))

        if not target_id:
            return

        # Template quick answer check (#keyword)
        msg_text = message.text or message.caption or ""
        if msg_text.startswith("#"):
            keyword = msg_text[1:].strip().split()[0]
            template_content = db_get_template(bot_token, keyword)
            if template_content:
                await client.send_message(chat_id=target_id, text=template_content)
                await message.reply_text(f"⚡ Template `#{keyword}` sent to user!")
                return

        try:
            await message.copy(chat_id=target_id)
            try:
                await client.send_reaction(chat_id=message.chat.id, message_id=message.id, emoji="👍")
            except Exception:
                pass
        except Exception as e:
            await message.reply_text(f"❌ Send fail: `{e}`")

    # --- Non-Reply Warning ---
    @bot.on_message(
        filters.private
        & filters.user(owner_id)
        & ~filters.reply
        & ~filters.command(["start", "admin", "privacy", "help", "setstart", "setgroup", "template", "broadcast", "ban", "unban", "stats"])
    )
    async def no_reply_alert(client: Client, message: Message):
        alert = await message.reply_text("⚠️ _Reply to a forwarded message to send a message to that user._")
        asyncio.create_task(auto_delete(alert, delay=4))


# ================= 4. Master Bot System ================= #
master_bot = Client("modular_master", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
setup_modular_handlers(master_bot, MASTER_ADMIN, BOT_TOKEN)

@master_bot.on_message(filters.command("clone") & filters.private)
async def master_clone_command(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("⚠️ **Format:** `/clone <BOT_TOKEN>`")

    token = message.command[1].strip()
    wait_msg = await message.reply_text("🔄 Token verify karke instance create kiya ja raha hai...")

    new_clone = Client(f"clone_{token[:10]}", api_id=API_ID, api_hash=API_HASH, bot_token=token)
    setup_modular_handlers(new_clone, message.from_user.id, token)

    try:
        await new_clone.start()
        await set_modular_commands(new_clone, message.from_user.id)
        bot_me = await new_clone.get_me()

        conn = sqlite3.connect(DB_FILE)
        conn.cursor().execute("INSERT OR REPLACE INTO clones (token, owner_id) VALUES (?, ?)", (token, message.from_user.id))
        conn.commit()
        conn.close()

        active_clients.append(new_clone)
        await wait_msg.edit_text(
            f"✅ **Modular Bot Deployed!**\n\n"
            f"🤖 **Bot:** @{bot_me.username}\n"
            f"👑 **Owner:** `{message.from_user.id}`\n\n"
            f"Apne bot par jayein aur `/start` karein!"
        )
    except Exception as e:
        await wait_msg.edit_text(f"❌ Failed to launch clone: `{e}`")


# ================= 5. Server Lifecycle & Runner ================= #
async def web_handler(request):
    return web.Response(text="Modular Engine is running 24/7!")

async def start_services():
    server = web.Application()
    server.router.add_get("/", web_handler)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()

    await master_bot.start()
    await set_modular_commands(master_bot, MASTER_ADMIN)
    active_clients.append(master_bot)
    logger.info("Modular Master live!")

    conn = sqlite3.connect(DB_FILE)
    clones = conn.cursor().execute("SELECT token, owner_id FROM clones").fetchall()
    conn.close()

    for token, owner_id in clones:
        if token == BOT_TOKEN:
            continue
        try:
            c = Client(f"clone_{token[:10]}", api_id=API_ID, api_hash=API_HASH, bot_token=token)
            setup_modular_handlers(c, owner_id, token)
            await c.start()
            await set_modular_commands(c, owner_id)
            active_clients.append(c)
            logger.info(f"Loaded clone for owner {owner_id}")
        except Exception as e:
            logger.error(f"Clone recovery error: {e}")

    await idle()
    for c in active_clients:
        await c.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
