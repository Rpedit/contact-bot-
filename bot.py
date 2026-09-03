import os
import re
import sqlite3
import asyncio
import logging
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN, ADMINS, START_VIDEO, BUTTON_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

MASTER_ADMINS = [int(x) for x in ADMINS]
active_clients = []

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

# ================= 2. Helper: Auto-Delete ================= #
async def auto_delete(msg: Message, delay: int = 3):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


# ================= 3. Clone Bot Logic Generator ================= #
def setup_handlers(bot: Client, admin_id: int):
    msg_map = {}
    banned_users = set()
    user_warns = {}

    @bot.on_message(filters.command("start") & filters.private)
    async def start(client: Client, message: Message):
        user = message.from_user
        caption_text = (
            f"HEY 👤 **{user.first_name}**,\n\n"
            f"I'M THE OWNER OF 🔍 **HD PRO SEARCH BOT**\n\n"
            f"🎬 **NEW MOVIES / SERIES BOTS DEKHNA HO TO NICHE DIYE GAYE BUTTON PE CLICK KARE** 👇\n\n"
            f"⚠️ **AEK SE BHI ZYADA FAST & ADVANCED MOVIE SEARCH BOTS AVAILABLE!**"
        )
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("⚡ Fast Movie Bots List ↗", url=BUTTON_URL)]])

        try:
            await message.reply_video(video=START_VIDEO, caption=caption_text, reply_markup=buttons)
        except Exception:
            await message.reply_text(text=caption_text, reply_markup=buttons)

        if user.id == admin_id:
            admin_panel = (
                "👆 This is the message your users will see.\n\n"
                "👇 This is the message you see as an administrator.\n\n"
                "👑 **You are the administrator of this bot!**"
            )
            await message.reply_text(admin_panel)

    @bot.on_message(filters.private & filters.user(admin_id) & filters.command("ban"))
    async def ban(client: Client, message: Message):
        target = None
        if len(message.command) > 1 and message.command[1].isdigit():
            target = int(message.command[1])
        elif message.reply_to_message and message.reply_to_message.id in msg_map:
            target = msg_map[message.reply_to_message.id]

        if target:
            banned_users.add(target)
            await message.reply_text(f"🚫 User `[{target}]` ko Ban kar diya.")
        else:
            await message.reply_text("⚠️ User ID do ya forwarded message par reply karo.")

    @bot.on_message(filters.private & filters.user(admin_id) & filters.command("unban"))
    async def unban(client: Client, message: Message):
        target = int(message.command[1]) if len(message.command) > 1 and message.command[1].isdigit() else None
        if target and target in banned_users:
            banned_users.remove(target)
            await message.reply_text(f"✅ User `[{target}]` Unban ho gaya.")
        else:
            await message.reply_text("⚠️ Valid user ID do.")

    @bot.on_message(filters.private & ~filters.user(admin_id) & ~filters.command("start"))
    async def forward_to_admin(client: Client, message: Message):
        user = message.from_user
        if user.id in banned_users:
            notice = await message.reply_text("🚫 **Aap is bot par banned hain.**")
            asyncio.create_task(auto_delete(notice, 4))
            return

        fwd = await message.forward(admin_id)
        msg_map[fwd.id] = user.id

        info_text = (
            f"📢 **Message sent by {user.first_name}!!**\n"
            f"[{user.id}](tg://user?id={user.id}) #id{user.id}\n\n"
            f"👉 Reply to answer."
        )
        profile_url = f"https://t.me/{user.username}" if user.username else f"tg://openmessage?user_id={user.id}"
        card = await client.send_message(
            chat_id=admin_id,
            text=info_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 User profile", url=profile_url)]]),
            disable_web_page_preview=True
        )
        msg_map[card.id] = user.id

        confirm = await message.reply_text("Message sent! ⏱️")
        asyncio.create_task(auto_delete(confirm, 3))

    @bot.on_message(filters.private & filters.user(admin_id) & filters.reply)
    async def reply_user(client: Client, message: Message):
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
                await message.reply_text(f"❌ Delivery failed: `{e}`")


# ================= 4. Master Bot System ================= #
master_bot = Client(
    "master_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)
setup_handlers(master_bot, MASTER_ADMINS[0])

@master_bot.on_message(filters.command("clone") & filters.private)
async def clone_command(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ Token missing!\nUse: `/clone 123456789:ABCdef...`")
        return

    token = message.command[1].strip()
    status_msg = await message.reply_text("🔄 Token verify karke bot boot kiya ja raha hai...")

    new_bot = Client(
        f"clone_{token[:10]}",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=token
    )
    setup_handlers(new_bot, message.from_user.id)

    try:
        await new_bot.start()
        bot_info = await new_bot.get_me()
        save_clone(token, message.from_user.id)
        active_clients.append(new_bot)
        await status_msg.edit_text(
            f"✅ **Bot Clone Success!**\n\n"
            f"🤖 **Bot Name:** @{bot_info.username}\n"
            f"👑 **Owner:** `{message.from_user.id}`\n\n"
            f"Aapka naya bot ready hai, use start karein!"
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Bot start karne me fail ho gaya:\n`{e}`")


# ================= 5. Web Server & Lifecycle Runner ================= #
async def web_handler(request):
    return web.Response(text="Master + Clone Bots Running 24/7!")

async def start_services():
    server = web.Application()
    server.router.add_get("/", web_handler)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()

    # Start Master Bot
    await master_bot.start()
    active_clients.append(master_bot)
    logger.info("Master bot live!")

    # Restore Clones from SQLite
    saved_clones = get_clones()
    for token, admin_id in saved_clones:
        try:
            clone_client = Client(f"clone_{token[:10]}", api_id=API_ID, api_hash=API_HASH, bot_token=token)
            setup_handlers(clone_client, admin_id)
            await clone_client.start()
            active_clients.append(clone_client)
            logger.info(f"Loaded clone for admin {admin_id}")
        except Exception as e:
            logger.error(f"Clone recovery failed for {token[:8]}: {e}")

    await idle()

    for c in active_clients:
        await c.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
