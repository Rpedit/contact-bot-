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
    ChatPermissions,
)
from config import API_ID, API_HASH, BOT_TOKEN, ADMINS, START_VIDEO, BUTTON_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

MASTER_ADMINS = [int(x) for x in ADMINS]
active_clients = []
user_languages = {}

# ================= 1. Advanced SQLite Database Setup ================= #
DB_FILE = "clones.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Clones Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS clones (
            token TEXT PRIMARY KEY,
            admin_id INTEGER
        )
    """)
    # Registered Users Table (For Broadcast & Stats)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            date_joined TEXT
        )
    """)
    # Connected Groups Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            date_added TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_user(user_id: int, name: str, username: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, name, username, date_joined) VALUES (?, ?, ?, ?)",
        (user_id, name, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()

def save_group(chat_id: int, title: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO groups (chat_id, title, date_added) VALUES (?, ?, ?)",
        (chat_id, title, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
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

def get_db_stats():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM groups")
    total_groups = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM clones")
    total_clones = c.fetchone()[0]
    conn.close()
    return total_users, total_groups, total_clones

def save_clone(token: str, admin_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO clones (token, admin_id) VALUES (?, ?)", (token, admin_id))
    conn.commit()
    conn.close()

def get_clones():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT token, admin_id FROM clones")
    data = c.fetchall()
    conn.close()
    return data

init_db()


# ================= 2. Helper Functions ================= #
async def auto_delete(msg: Message, delay: int = 3):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

async def register_bot_commands(client: Client):
    try:
        await client.set_bot_commands([
            BotCommand("start", "🤖 Restart / Check status"),
            BotCommand("admin", "👑 Admin control panel"),
            BotCommand("broadcast", "📢 Send message to all users"),
            BotCommand("stats", "📊 Bot analytics & stats"),
            BotCommand("help", "❓ How to use / Commands"),
            BotCommand("lang", "🌍 Change language"),
            BotCommand("id", "🆔 Get Chat / User ID"),
            BotCommand("ban", "🚫 Ban user (Group/PM)"),
            BotCommand("unban", "✅ Unban user"),
            BotCommand("mute", "🔇 Mute user (Group)"),
            BotCommand("unmute", "🔊 Unmute user (Group)"),
            BotCommand("kick", "👢 Kick user from group"),
            BotCommand("pin", "📌 Pin message in group"),
        ])
    except Exception as e:
        logger.warning(f"Commands setup issue: {e}")

def extract_target_user(message: Message, msg_map: dict) -> int | None:
    """Extracts target user ID from command arg, reply, forward, or message card."""
    if len(message.command) > 1 and message.command[1].lstrip("-").isdigit():
        return int(message.command[1])

    if message.reply_to_message:
        replied = message.reply_to_message
        if replied.from_user:
            return replied.from_user.id
        if replied.id in msg_map:
            return msg_map[replied.id]
        if replied.forward_from:
            return replied.forward_from.id
        text_content = replied.text or replied.caption or ""
        match = re.search(r"#id(\d+)", text_content)
        if match:
            return int(match.group(1))

    return None


# ================= 3. Core Handlers Generator ================= #
def setup_handlers(bot: Client, admin_id: int):
    msg_map = {}
    banned_users = set()
    user_warns = {}

    # --- Group Auto-Join Tracker & Welcome Card ---
    @bot.on_message(filters.new_chat_members)
    async def group_welcome(client: Client, message: Message):
        chat = message.chat
        save_group(chat.id, chat.title)

        for member in message.new_chat_members:
            if member.is_self:
                await message.reply_text(
                    f"🎉 **Thanks for adding me to {chat.title}!**\n\n"
                    "Mujhe group me **Admin** banayein taaki main group management aur user support automate kar sakoon.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚡ Support Group", url=BUTTON_URL)]])
                )
            else:
                welcome_card = (
                    f"👋 Welcome [{member.first_name}](tg://user?id={member.id}) to **{chat.title}**!\n\n"
                    "• Spaming na karein.\n"
                    "• Rules follow karein."
                )
                del_msg = await message.reply_text(welcome_card)
                asyncio.create_task(auto_delete(del_msg, delay=10))

    # --- /start Handler (Private) ---
    @bot.on_message(filters.command("start") & filters.private)
    async def start_handler(client: Client, message: Message):
        user = message.from_user
        save_user(user.id, user.first_name, user.username or "")
        me = await client.get_me()

        caption_text = (
            f"HEY 👤 [**{user.first_name}**](tg://user?id={user.id}),\n\n"
            f"I'M THE OWNER OF 🔍 **HD PRO SEARCH BOT**\n\n"
            f"🎬 **NEW MOVIES / SERIES BOTS DEKHNA HO TO NICHE DIYE GAYE BUTTON PE CLICK KARE** 👇\n\n"
            f"⚠️ **AEK SE BHI ZYADA FAST & ADVANCED MOVIE SEARCH BOTS AVAILABLE!**"
        )

        user_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ Fast Movie Bots List ↗", url=BUTTON_URL)],
            [
                InlineKeyboardButton("➕ Add Me to Your Group", url=f"https://t.me/{me.username}?startgroup=true"),
                InlineKeyboardButton("🌍 Language", callback_data="open_lang")
            ],
            [InlineKeyboardButton("❓ How to Use", callback_data="open_help")]
        ])

        try:
            await message.reply_video(video=START_VIDEO, caption=caption_text, reply_markup=user_buttons)
        except Exception:
            try:
                await message.reply_animation(animation=START_VIDEO, caption=caption_text, reply_markup=user_buttons)
            except Exception:
                await message.reply_text(text=caption_text, reply_markup=user_buttons)

        if user.id == admin_id:
            admin_panel_text = (
                "👆 This is the message your users will see.\n\n"
                "👇 This is the message you see as an administrator.\n\n"
                "👑 **You are the administrator of this bot!**"
            )
            admin_buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_home"),
                    InlineKeyboardButton("📊 Stats", callback_data="live_stats")
                ],
                [InlineKeyboardButton("🎧 Support ↗", url=BUTTON_URL)]
            ])
            await message.reply_text(admin_panel_text, reply_markup=admin_buttons)

    # --- /admin & /stats Interactive Dashboard ---
    @bot.on_message(filters.command(["admin", "stats"]) & filters.private & filters.user(admin_id))
    async def admin_panel_handler(client: Client, message: Message):
        tot_u, tot_g, tot_c = get_db_stats()
        panel_text = (
            "👑 **Advanced Admin Dashboard**\n\n"
            f"👤 **Admin ID:** `{admin_id}`\n"
            f"👥 **Total Registered Users:** `{tot_u}`\n"
            f"🏢 **Total Active Groups:** `{tot_g}`\n"
            f"🤖 **Total Active Clones:** `{tot_c}`\n"
            f"🚫 **Total Banned Users:** `{len(banned_users)}`\n"
            f"⚠️ **Active Warnings:** `{len(user_warns)}`"
        )
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 Live Stats", callback_data="live_stats"),
                InlineKeyboardButton("📢 Broadcast", callback_data="start_bcast")
            ],
            [
                InlineKeyboardButton("📋 Banned Users", callback_data="show_banned"),
                InlineKeyboardButton("⚙️ System Info", callback_data="system_info")
            ],
            [InlineKeyboardButton("❌ Close Panel", callback_data="close_panel")]
        ])
        await message.reply_text(panel_text, reply_markup=buttons)

    # --- /broadcast Command ---
    @bot.on_message(filters.command("broadcast") & filters.private & filters.user(admin_id))
    async def broadcast_message(client: Client, message: Message):
        if not message.reply_to_message and len(message.command) < 2:
            await message.reply_text("⚠️ **Format:** Reply to a message with `/broadcast` ya `/broadcast <text>` likhein.")
            return

        users = get_all_users()
        total = len(users)
        success, failed = 0, 0

        status = await message.reply_text(f"🚀 **Broadcasting started...** (Total: `{total}` users)")

        for uid in users:
            try:
                if message.reply_to_message:
                    await message.reply_to_message.copy(chat_id=uid)
                else:
                    broadcast_text = message.text.split(None, 1)[1]
                    await client.send_message(chat_id=uid, text=broadcast_text)
                success += 1
                await asyncio.sleep(0.05)
            except Exception:
                failed += 1

        await status.edit_text(
            f"✅ **Broadcast Completed!**\n\n"
            f"👥 **Total Users:** `{total}`\n"
            f"🟢 **Delivered:** `{success}`\n"
            f"🔴 **Failed:** `{failed}`"
        )

    # --- /id & /info Command (Works in Groups & PM) ---
    @bot.on_message(filters.command("id"))
    async def get_id_details(client: Client, message: Message):
        reply = message.reply_to_message
        target = reply.from_user if reply else message.from_user
        
        info = (
            f"💬 **Chat ID:** `{message.chat.id}`\n"
            f"👤 **User:** [{target.first_name}](tg://user?id={target.id})\n"
            f"🆔 **User ID:** `{target.id}`\n"
            f"🏷️ **Username:** @{target.username if target.username else 'None'}"
        )
        if reply:
            info += f"\n📩 **Replied Msg ID:** `{reply.id}`"

        await message.reply_text(info, disable_web_page_preview=True)

    # --- Group Moderation Commands (/ban, /unban, /mute, /unmute, /kick, /pin) ---
    @bot.on_message(filters.command("ban") & (filters.user(admin_id) | filters.group))
    async def handle_ban(client: Client, message: Message):
        if message.chat.type in ["group", "supergroup"]:
            member = await message.chat.get_member(message.from_user.id)
            if not member.privileges and message.from_user.id != admin_id:
                return await message.reply_text("⛔ Sirf group admins ye command chala sakte hain!")

        target_id = extract_target_user(message, msg_map)
        if not target_id:
            return await message.reply_text("⚠️ User ID do ya kisi user ke message par reply karke `/ban` likho.")

        if message.chat.type in ["group", "supergroup"]:
            try:
                await message.chat.ban_member(target_id)
                await message.reply_text(f"🚫 User `[{target_id}]` ko group se **Ban** kar diya gaya.")
            except Exception as e:
                await message.reply_text(f"❌ Ban fail: `{e}`")
        else:
            banned_users.add(target_id)
            await message.reply_text(f"🚫 User `[{target_id}]` ko bot se **Ban** kar diya gaya.")

    @bot.on_message(filters.command("unban") & (filters.user(admin_id) | filters.group))
    async def handle_unban(client: Client, message: Message):
        target_id = extract_target_user(message, msg_map)
        if not target_id:
            return await message.reply_text("⚠️ User ID specify karein.")

        if message.chat.type in ["group", "supergroup"]:
            try:
                await message.chat.unban_member(target_id)
                await message.reply_text(f"✅ User `[{target_id}]` ko group me **Unban** kar diya gaya.")
            except Exception as e:
                await message.reply_text(f"❌ Unban fail: `{e}`")
        else:
            if target_id in banned_users:
                banned_users.remove(target_id)
            await message.reply_text(f"✅ User `[{target_id}]` ko bot par **Unban** kar diya gaya.")

    @bot.on_message(filters.command("mute") & filters.group)
    async def handle_mute(client: Client, message: Message):
        target_id = extract_target_user(message, msg_map)
        if not target_id:
            return await message.reply_text("⚠️ Kisi ke message par reply karke `/mute` karein.")
        try:
            await message.chat.restrict_member(target_id, ChatPermissions(can_send_messages=False))
            await message.reply_text(f"🔇 User `[{target_id}]` ko group me **Mute** kar diya gaya.")
        except Exception as e:
            await message.reply_text(f"❌ Mute error: `{e}`")

    @bot.on_message(filters.command("unmute") & filters.group)
    async def handle_unmute(client: Client, message: Message):
        target_id = extract_target_user(message, msg_map)
        if not target_id:
            return await message.reply_text("⚠️ User mention karein.")
        try:
            await message.chat.restrict_member(
                target_id,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                ),
            )
            await message.reply_text(f"🔊 User `[{target_id}]` ab **Unmuted** hai.")
        except Exception as e:
            await message.reply_text(f"❌ Unmute error: `{e}`")

    @bot.on_message(filters.command("kick") & filters.group)
    async def handle_kick(client: Client, message: Message):
        target_id = extract_target_user(message, msg_map)
        if not target_id:
            return await message.reply_text("⚠️ User par reply karein.")
        try:
            await message.chat.ban_member(target_id)
            await message.chat.unban_member(target_id)
            await message.reply_text(f"👢 User `[{target_id}]` ko group se **Kick** kar diya gaya.")
        except Exception as e:
            await message.reply_text(f"❌ Kick error: `{e}`")

    @bot.on_message(filters.command("pin") & filters.group)
    async def handle_pin(client: Client, message: Message):
        if not message.reply_to_message:
            return await message.reply_text("📌 Jis message ko pin karna hai uspar reply karein.")
        try:
            await message.reply_to_message.pin()
            notice = await message.reply_text("📌 **Message Pinned Successfully!**")
            asyncio.create_task(auto_delete(notice, 4))
        except Exception as e:
            await message.reply_text(f"❌ Pin error: `{e}`")

    # --- /warn & /resetwarn ---
    @bot.on_message(filters.command("warn") & filters.user(admin_id))
    async def warn_user(client: Client, message: Message):
        target_id = extract_target_user(message, msg_map)
        if not target_id:
            return await message.reply_text("⚠️ User ID do ya message par reply karo.")

        user_warns[target_id] = user_warns.get(target_id, 0) + 1
        cnt = user_warns[target_id]

        if cnt >= 3:
            banned_users.add(target_id)
            user_warns.pop(target_id, None)
            await message.reply_text(f"🚫 User `[{target_id}]` ke 3/3 warnings poore hue. User Banned!")
        else:
            await message.reply_text(f"⚠️ User `[{target_id}]` ko warning di gayi: **{cnt}/3**")

    # --- /help & /lang Commands ---
    @bot.on_message(filters.command("help") & filters.private)
    async def help_command(client: Client, message: Message):
        help_text = (
            "🛠️ **Available Commands Guide**\n\n"
            "**👤 Users:**\n"
            "• Direct message bhejein, aapka message admin tak forward ho jayega.\n"
            "• `/id` - Apna ya chat ka ID check karein.\n"
            "• `/lang` - Bot language choose karein.\n\n"
            "**👑 Admin & Moderation:**\n"
            "• `/admin` - Live dashboard and controls\n"
            "• `/broadcast` - Sabhi users ko ek sath msg bhejein\n"
            "• `/ban`, `/unban`, `/mute`, `/kick`, `/pin` - Group & DM management\n"
            "• `/clone <token>` - Create your own instance"
        )
        await message.reply_text(help_text)

    @bot.on_message(filters.command("lang") & filters.private)
    async def lang_command(client: Client, message: Message):
        lang_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en"), InlineKeyboardButton("हिन्दी 🇮🇳", callback_data="set_lang_hi")]
        ])
        await message.reply_text("🌍 **Select preferred language / अपनी भाषा चुनें:**", reply_markup=lang_buttons)

    # --- Callback Query Central ---
    @bot.on_callback_query()
    async def handle_callbacks(client: Client, query: CallbackQuery):
        data = query.data
        uid = query.from_user.id

        if data == "open_lang":
            await query.message.reply_text(
                "🌍 **Select language:**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en"), InlineKeyboardButton("हिन्दी 🇮🇳", callback_data="set_lang_hi")]
                ])
            )
            await query.answer()
        elif data == "open_help":
            await query.answer()
            await query.message.reply_text("❓ Koi bhi message yahan likhkar bhejein, support team aapse direct connect karegi.")
        elif data == "set_lang_en":
            user_languages[uid] = "en"
            await query.answer("Language set to English!", show_alert=True)
        elif data == "set_lang_hi":
            user_languages[uid] = "hi"
            await query.answer("भाषा हिन्दी सेट हो गई है!", show_alert=True)
        elif data == "live_stats":
            tot_u, tot_g, tot_c = get_db_stats()
            await query.answer(f"Users: {tot_u} | Groups: {tot_g} | Clones: {tot_c}", show_alert=True)
        elif data == "start_bcast":
            await query.answer("Reply to any message with /broadcast to send it to all users.", show_alert=True)
        elif data == "show_banned":
            if not banned_users:
                await query.answer("Koi banned user nahi hai.", show_alert=True)
            else:
                b_list = "\n".join([f"`{x}`" for x in banned_users])
                await query.message.reply_text(f"🚫 **Current Banned Users:**\n\n{b_list}")
                await query.answer()
        elif data == "system_info":
            await query.answer("Engine: Pyrogram v2 Async\nPersistence: SQLite\nKeep-Alive: Aiohttp Active", show_alert=True)
        elif data == "close_panel":
            await query.message.delete()
        else:
            await query.answer()

    # --- User to Admin Private Relay ---
    @bot.on_message(filters.private & ~filters.user(admin_id) & ~filters.command(["start", "help", "admin", "lang", "id", "broadcast"]))
    async def user_forward_handler(client: Client, message: Message):
        user = message.from_user
        save_user(user.id, user.first_name, user.username or "")

        if user.id in banned_users:
            notice = await message.reply_text("🚫 **Aapko is bot par ban kiya gaya hai.**")
            return asyncio.create_task(auto_delete(notice, 4))

        try:
            fwd = await message.forward(admin_id)
            msg_map[fwd.id] = user.id
        except Exception as e:
            return logger.error(f"Forward error: {e}")

        info_text = (
            f"📢 **Message sent by {user.first_name}!!**\n"
            f"[{user.id}](tg://user?id={user.id}) #id{user.id}\n\n"
            f"👉 To answer, reply to this message."
        )
        profile_url = f"https://t.me/{user.username}" if user.username else f"tg://openmessage?user_id={user.id}"
        card = await client.send_message(
            chat_id=admin_id,
            text=info_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 User profile", url=profile_url)]]),
            disable_web_page_preview=True,
        )
        msg_map[card.id] = user.id

        confirm = await message.reply_text("Message sent! ⏱️")
        asyncio.create_task(auto_delete(confirm, 3))

    # --- Admin to User Reply ---
    @bot.on_message(filters.private & filters.user(admin_id) & filters.reply)
    async def reply_handler(client: Client, message: Message):
        target = msg_map.get(message.reply_to_message.id)
        if not target and message.reply_to_message.text:
            match = re.search(r"#id(\d+)", message.reply_to_message.text)
            if match:
                target = int(match.group(1))

        if target:
            try:
                await message.copy(chat_id=target)
                try:
                    await client.send_reaction(chat_id=admin_id, message_id=message.id, emoji="👍")
                except Exception:
                    pass
            except Exception as e:
                await message.reply_text(f"❌ Delivery fail: `{e}`")
        else:
            await message.reply_text("⚠️ User ID nahi mili. User card ya forwarded msg par reply karein.")

    # --- Non-Reply Admin Warning ---
    @bot.on_message(
        filters.private 
        & filters.user(admin_id) 
        & ~filters.reply 
        & ~filters.command(["start", "admin", "help", "lang", "ban", "unban", "warn", "resetwarn", "clone", "broadcast", "stats", "id"])
    )
    async def admin_no_reply_alert(client: Client, message: Message):
        alert = await message.reply_text("⚠️ _Reply to a forwarded message to send a message to that user._")
        asyncio.create_task(auto_delete(alert, delay=4))


# ================= 4. Master Bot & Dynamic Cloning ================= #
master_bot = Client(
    "master_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)
setup_handlers(master_bot, MASTER_ADMINS[0])

@master_bot.on_message(filters.command("clone") & filters.private)
async def clone_bot_command(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("⚠️ Token missing!\nUsage: `/clone 123456789:ABCdef...`")

    token = message.command[1].strip()
    status_msg = await message.reply_text("🔄 Token verify karke naya instance initialize ho raha hai...")

    new_bot = Client(f"clone_{token[:10]}", api_id=API_ID, api_hash=API_HASH, bot_token=token)
    setup_handlers(new_bot, message.from_user.id)

    try:
        await new_bot.start()
        await register_bot_commands(new_bot)
        bot_info = await new_bot.get_me()
        save_clone(token, message.from_user.id)
        active_clients.append(new_bot)
        await status_msg.edit_text(
            f"✅ **Advanced Bot Cloned Successfully!**\n\n"
            f"🤖 **Bot:** @{bot_info.username}\n"
            f"👑 **Owner:** `{message.from_user.id}`\n\n"
            f"Group moderation, live dashboard, aur dynamic forwarding commands active ho gaye hain!"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to launch clone:\n`{e}`")


# ================= 5. Web Keep-Alive & Server Lifecycle ================= #
async def web_handler(request):
    return web.Response(text="Advanced Kasuki Multi-Bot Engine Running 24/7!")

async def start_services():
    server = web.Application()
    server.router.add_get("/", web_handler)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info(f"Keep-Alive Server port {port} par active hai.")

    # Master Launch
    await master_bot.start()
    await register_bot_commands(master_bot)
    active_clients.append(master_bot)
    logger.info("Master bot live!")

    # Recover Clones
    saved_clones = get_clones()
    for token, admin_id in saved_clones:
        try:
            clone_client = Client(f"clone_{token[:10]}", api_id=API_ID, api_hash=API_HASH, bot_token=token)
            setup_handlers(clone_client, admin_id)
            await clone_client.start()
            await register_bot_commands(clone_client)
            active_clients.append(clone_client)
            logger.info(f"Loaded clone for admin {admin_id}")
        except Exception as e:
            logger.error(f"Clone recovery error: {e}")

    await idle()

    for c in active_clients:
        await c.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
