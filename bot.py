import os
import re
import sqlite3
import asyncio
import logging
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand,
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

# ================= 1. SQLite Database Setup ================= #
DB_FILE = "clones.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS clones (
            token TEXT PRIMARY KEY,
            admin_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

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
    """Specified seconds ke baad message ko auto-delete karta hai"""
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

async def register_bot_commands(client: Client):
    """Native bottom-left menu list set karta hai"""
    try:
        await client.set_bot_commands([
            BotCommand("admin", "👑 Admin panel"),
            BotCommand("start", "🤖 Restart bot"),
            BotCommand("help", "❓ How to use"),
            BotCommand("lang", "🌍 Change language"),
        ])
    except Exception as e:
        logger.warning(f"Failed to register bot commands: {e}")


# ================= 3. Handlers Factory ================= #
def setup_handlers(bot: Client, admin_id: int):
    msg_map = {}
    banned_users = set()
    user_warns = {}

    # --- /start (Restart bot) ---
    @bot.on_message(filters.command("start") & filters.private)
    async def start_handler(client: Client, message: Message):
        user = message.from_user
        caption_text = (
            f"HEY 👤 [**{user.first_name}**](tg://user?id={user.id}),\n\n"
            f"I'M THE OWNER OF 🔍 **HD PRO SEARCH BOT**\n\n"
            f"🎬 **NEW MOVIES / SERIES BOTS DEKHNA HO TO NICHE DIYE GAYE BUTTON PE CLICK KARE** 👇\n\n"
            f"⚠️ **AEK SE BHI ZYADA FAST & ADVANCED MOVIE SEARCH BOTS AVAILABLE!**"
        )
        buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚡ Fast Movie Bots List ↗", url=BUTTON_URL)]]
        )

        try:
            await message.reply_video(video=START_VIDEO, caption=caption_text, reply_markup=buttons)
        except Exception:
            try:
                await message.reply_animation(animation=START_VIDEO, caption=caption_text, reply_markup=buttons)
            except Exception:
                await message.reply_text(text=caption_text, reply_markup=buttons)

        if user.id == admin_id:
            admin_panel_text = (
                "👆 This is the message your users will see.\n\n"
                "👇 This is the message you see as an administrator.\n\n"
                "👑 **You are the administrator of this bot!**"
            )
            admin_buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚙️ Bot settings", callback_data="bot_settings"),
                    InlineKeyboardButton("🎧 Support ↗", url=BUTTON_URL),
                ]
            ])
            await message.reply_text(admin_panel_text, reply_markup=admin_buttons)

    # --- /admin (Admin Panel) ---
    @bot.on_message(filters.command("admin") & filters.private)
    async def admin_panel_handler(client: Client, message: Message):
        if message.from_user.id != admin_id:
            await message.reply_text("⛔ **Access Denied:** Yeh command sirf bot admin ke liye hai.")
            return

        panel_text = (
            "👑 **Admin Control Panel**\n\n"
            f"👤 **Admin ID:** `{admin_id}`\n"
            f"🚫 **Total Banned Users:** `{len(banned_users)}`\n"
            f"⚠️ **Users Under Warning:** `{len(user_warns)}`\n\n"
            "**Quick Commands:**\n"
            "• `/ban <id>` ya reply par `/ban` - User block\n"
            "• `/unban <id>` ya reply par `/unban` - User unblock\n"
            "• `/warn <id>` ya reply par `/warn` - Warning dena\n"
            "• `/resetwarn <id>` - Warnings reset karna"
        )
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📋 Banned List", callback_data="show_banned"),
                InlineKeyboardButton("⚙️ Settings", callback_data="bot_settings"),
            ]
        ])
        await message.reply_text(panel_text, reply_markup=buttons)

    # --- /help (How to use) ---
    @bot.on_message(filters.command("help") & filters.private)
    async def help_command_handler(client: Client, message: Message):
        lang = user_languages.get(message.from_user.id, "en")
        
        if message.from_user.id == admin_id:
            text = (
                "🛠️ **Admin Help Manual**\n\n"
                "1. **User Messages:** Jab user message karega toh unka msg aapko forward hoga.\n"
                "2. **Replying:** Forwarded message ya info card par **Swipe karke Reply** karein.\n"
                "3. **Moderation:** Reply karke `/ban`, `/unban`, ya `/warn` use kar sakte hain.\n"
                "4. **Dashboard:** Status check karne ke liye `/admin` use karein."
            )
        else:
            if lang == "hi":
                text = (
                    "❓ **उपयोग कैसे करें?**\n\n"
                    "• आप इस चैट में कोई भी सवाल या संदेश भेज सकते हैं।\n"
                    "• आपका संदेश सीधे एडमिन तक पहुँच जाएगा।\n"
                    "• एडमिन का जवाब आपको यहीं प्राप्त होगा।"
                )
            else:
                text = (
                    "❓ **How to use this bot?**\n\n"
                    "• Type and send any question or message in this chat.\n"
                    "• Your query is delivered directly to the bot owner.\n"
                    "• You will receive their reply right here."
                )
        await message.reply_text(text)

    # --- /lang (Change language) ---
    @bot.on_message(filters.command("lang") & filters.private)
    async def language_handler(client: Client, message: Message):
        lang_buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en"),
                InlineKeyboardButton("हिन्दी 🇮🇳", callback_data="set_lang_hi"),
            ]
        ])
        await message.reply_text("🌍 **Select your preferred language / अपनी भाषा चुनें:**", reply_markup=lang_buttons)

    # --- Ban / Unban / Warn Handlers ---
    @bot.on_message(filters.command("ban") & filters.private & filters.user(admin_id))
    async def ban_handler(client: Client, message: Message):
        target = None
        if len(message.command) > 1 and message.command[1].isdigit():
            target = int(message.command[1])
        elif message.reply_to_message and message.reply_to_message.id in msg_map:
            target = msg_map[message.reply_to_message.id]

        if target:
            banned_users.add(target)
            await message.reply_text(f"🚫 User `[{target}]` ko **Ban** kar diya gaya.")
        else:
            await message.reply_text("⚠️ User ID enter karein ya user card par reply karein.")

    @bot.on_message(filters.command("unban") & filters.private & filters.user(admin_id))
    async def unban_handler(client: Client, message: Message):
        target = int(message.command[1]) if len(message.command) > 1 and message.command[1].isdigit() else None
        if target and target in banned_users:
            banned_users.remove(target)
            await message.reply_text(f"✅ User `[{target}]` ko **Unban** kar diya gaya.")
        else:
            await message.reply_text("⚠️ Valid user ID enter karein.")

    @bot.on_message(filters.command("warn") & filters.private & filters.user(admin_id))
    async def warn_handler(client: Client, message: Message):
        target = None
        if len(message.command) > 1 and message.command[1].isdigit():
            target = int(message.command[1])
        elif message.reply_to_message and message.reply_to_message.id in msg_map:
            target = msg_map[message.reply_to_message.id]

        if not target:
            await message.reply_text("⚠️ User ID dein ya card par reply karein.")
            return

        current_warns = user_warns.get(target, 0) + 1
        user_warns[target] = current_warns

        if current_warns >= 3:
            banned_users.add(target)
            user_warns.pop(target, None)
            await message.reply_text(f"🚫 User `[{target}]` ke 3 warnings complete. User banned!")
            try:
                await client.send_message(target, "⚠️ 3 warnings hone par aapko bot se ban kar diya gaya hai.")
            except Exception:
                pass
        else:
            await message.reply_text(f"⚠️ User `[{target}]` warned: **{current_warns}/3**")
            try:
                await client.send_message(target, f"⚠️ Warning received: **{current_warns}/3**")
            except Exception:
                pass

    @bot.on_message(filters.command("resetwarn") & filters.private & filters.user(admin_id))
    async def resetwarn_handler(client: Client, message: Message):
        target = int(message.command[1]) if len(message.command) > 1 and message.command[1].isdigit() else None
        if target:
            user_warns.pop(target, None)
            await message.reply_text(f"✅ User `[{target}]` warnings reset.")
        else:
            await message.reply_text("⚠️ User ID dein: `/resetwarn 123456789`")

    # --- Callback Queries ---
    @bot.on_callback_query()
    async def callback_queries(client: Client, query: CallbackQuery):
        data = query.data
        uid = query.from_user.id

        if data == "set_lang_en":
            user_languages[uid] = "en"
            await query.answer("Language set to English! 🇬🇧", show_alert=True)
            await query.message.edit_text("✅ Language updated to **English**.")
        elif data == "set_lang_hi":
            user_languages[uid] = "hi"
            await query.answer("भाषा हिन्दी सेट हो गई है! 🇮🇳", show_alert=True)
            await query.message.edit_text("✅ आपकी भाषा **हिन्दी** सेट कर दी गई है।")
        elif data == "bot_settings":
            await query.answer("Bot status: Running smoothly 24/7.", show_alert=True)
        elif data == "show_banned":
            if not banned_users:
                await query.answer("Ban list empty hai.", show_alert=True)
            else:
                banned_list = "\n".join([f"`{u}`" for u in banned_users])
                await query.message.reply_text(f"🚫 **Current Banned Users:**\n\n{banned_list}")
                await query.answer()
        else:
            await query.answer()

    # --- User Messages (User -> Admin) ---
    @bot.on_message(filters.private & ~filters.user(admin_id) & ~filters.command(["start", "help", "admin", "lang"]))
    async def user_forward_handler(client: Client, message: Message):
        user = message.from_user

        if user.id in banned_users:
            notice = await message.reply_text("🚫 **Aapko is bot par ban kiya gaya hai.**")
            asyncio.create_task(auto_delete(notice, 4))
            return

        try:
            fwd = await message.forward(admin_id)
            msg_map[fwd.id] = user.id
        except Exception as e:
            logger.error(f"Forwarding error: {e}")
            return

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

    # --- Admin Reply (Admin -> User) ---
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
                await message.reply_text(f"❌ Reply send fail: `{e}`")
        else:
            await message.reply_text("⚠️ User ID nahi mili. Message ya card par reply karein.")

    # --- Admin Warning when sending message without replying ---
    @bot.on_message(
        filters.private 
        & filters.user(admin_id) 
        & ~filters.reply 
        & ~filters.command(["start", "admin", "help", "lang", "ban", "unban", "warn", "resetwarn", "clone"])
    )
    async def admin_no_reply_alert(client: Client, message: Message):
        alert = await message.reply_text("⚠️ _Reply to a forwarded message to send a message to that user._")
        asyncio.create_task(auto_delete(alert, delay=4))


# ================= 4. Master Bot & Cloning System ================= #
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
        await message.reply_text("⚠️ Token missing!\nUsage: `/clone 123456789:ABCdef...`")
        return

    token = message.command[1].strip()
    status_msg = await message.reply_text("🔄 Token verify karke bot initialize ho raha hai...")

    new_bot = Client(
        f"clone_{token[:10]}",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=token,
    )
    setup_handlers(new_bot, message.from_user.id)

    try:
        await new_bot.start()
        await register_bot_commands(new_bot)
        bot_info = await new_bot.get_me()
        save_clone(token, message.from_user.id)
        active_clients.append(new_bot)
        await status_msg.edit_text(
            f"✅ **Bot Cloned Successfully!**\n\n"
            f"🤖 **Bot:** @{bot_info.username}\n"
            f"👑 **Owner:** `{message.from_user.id}`\n\n"
            f"Aapka naya bot live hai aur sabhi menu commands active hain!"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Bot start karne me error aaya:\n`{e}`")


# ================= 5. Keep-Alive Web Server & Runner ================= #
async def web_handler(request):
    return web.Response(text="Contact Relay & Cloning Service Running 24/7!")

async def start_services():
    server = web.Application()
    server.router.add_get("/", web_handler)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()

    # Launch Master Bot
    await master_bot.start()
    await register_bot_commands(master_bot)
    active_clients.append(master_bot)
    logger.info("Master bot running!")

    # Recover Clones from SQLite
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
            logger.error(f"Clone recovery error ({token[:8]}): {e}")

    await idle()

    for c in active_clients:
        await c.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
