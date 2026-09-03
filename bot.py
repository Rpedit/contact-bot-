import os
import re
import asyncio
import logging
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID, START_VIDEO, BUTTON_URL

# Logging setup (isse terminal me error saaf dikhega)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Ensure ADMIN_ID is integer
ADMIN = int(ADMIN_ID)

app = Client(
    "contact_relay_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# Admin message ID -> User ID mapping
msg_map = {}


# ================= Helper: Auto-Delete Message ================= #
async def auto_delete_message(msg: Message, delay: int = 3):
    """Specified seconds ke baad message ko auto-delete karta hai"""
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


# ================= 1. /start Handler ================= #
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user = message.from_user

    caption_text = (
        f"HEY 👤 **{user.first_name}**,\n\n"
        f"I'M THE OWNER OF 🔍 **HD PRO SEARCH BOT**\n\n"
        f"🎬 **NEW MOVIES / SERIES BOTS DEKHNA HO TO NICHE DIYE GAYE BUTTON PE CLICK KARE** 👇\n\n"
        f"⚠️ **AEK SE BHI ZYADA FAST & ADVANCED MOVIE SEARCH BOTS AVAILABLE!**"
    )

    user_buttons = InlineKeyboardMarkup(
        [[InlineKeyboardButton("⚡ Fast Movie Bots List ↗", url=BUTTON_URL)]]
    )

    # Send Welcome Video / Animation / Text
    sent = False
    if START_VIDEO:
        try:
            await message.reply_video(
                video=START_VIDEO,
                caption=caption_text,
                reply_markup=user_buttons,
            )
            sent = True
        except Exception as e:
            logger.warning(f"Video send failed: {e}")
            try:
                await message.reply_animation(
                    animation=START_VIDEO,
                    caption=caption_text,
                    reply_markup=user_buttons,
                )
                sent = True
            except Exception as e:
                logger.warning(f"Animation send failed: {e}")

    if not sent:
        await message.reply_text(
            text=caption_text,
            reply_markup=user_buttons,
        )

    # Admin Panel (Agar user khud Admin hai)
    if user.id == ADMIN:
        admin_text = (
            "👆 This is the message your users will see.\n\n"
            "👇 This is the message you see as an administrator.\n\n"
            "👑 **You are the administrator of this bot!**"
        )
        admin_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("⚙️ Bot settings", callback_data="bot_settings"),
                    InlineKeyboardButton("🎧 Support ↗", url=BUTTON_URL),
                ]
            ]
        )
        await message.reply_text(
            text=admin_text,
            reply_markup=admin_buttons,
        )


# ================= 2. Callback Query Handler ================= #
@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    if query.data == "bot_settings":
        await query.answer("Bot is working properly! All settings are default.", show_alert=True)
    else:
        await query.answer()


# ================= 3. User Message (User -> Admin) ================= #
@app.on_message(filters.private & ~filters.user(ADMIN) & ~filters.command(["start", "help"]))
async def user_to_admin(client: Client, message: Message):
    user = message.from_user

    # 1. Forward original message to Admin
    try:
        fwd = await message.forward(ADMIN)
        msg_map[fwd.id] = user.id
    except Exception as e:
        logger.error(f"Forward failed: {e}")
        return

    # 2. Details Card for Admin
    info_text = (
        f"📢 **Message sent by {user.first_name}**\n"
        f"`[{user.id}]` `[#id{user.id}]`\n\n"
        f"👉 Jawab dene ke liye is message par reply karein."
    )
    info_btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("👤 User profile", url=f"tg://user?id={user.id}")]]
    )

    info_msg = await client.send_message(
        chat_id=ADMIN,
        text=info_text,
        reply_markup=info_btn,
    )
    msg_map[info_msg.id] = user.id

    # 3. User Temporary Confirmation (Auto-delete after 3 sec)
    confirm_msg = await message.reply_text("Message sent! ⏱️")
    asyncio.create_task(auto_delete_message(confirm_msg, delay=3))


# ================= 4. Admin Reply (Admin -> User) ================= #
@app.on_message(filters.private & filters.user(ADMIN) & filters.reply)
async def admin_to_user(client: Client, message: Message):
    replied_msg = message.reply_to_message
    target_user_id = msg_map.get(replied_msg.id)

    # Fallback 1: Forward source
    if not target_user_id and replied_msg.forward_from:
        target_user_id = replied_msg.forward_from.id

    # Fallback 2: Extract from text
    if not target_user_id:
        text_content = replied_msg.text or replied_msg.caption or ""
        match = re.search(r"#id(\d+)", text_content)
        if match:
            target_user_id = int(match.group(1))

    if target_user_id:
        try:
            await message.copy(chat_id=target_user_id)
            try:
                await client.send_reaction(
                    chat_id=ADMIN,
                    message_id=message.id,
                    emoji="👍",
                )
            except Exception:
                pass
        except Exception as e:
            await message.reply_text(f"❌ Send fail: `{e}`")
    else:
        await message.reply_text("⚠️ User ID nahi mili. Message ya card par reply karein.")


# ================= 5. Admin Normal Message Handler ================= #
@app.on_message(filters.private & filters.user(ADMIN) & ~filters.reply & ~filters.command(["start", "help"]))
async def admin_normal_msg(client: Client, message: Message):
    await message.reply_text(
        "ℹ️ **Admin Alert:** Aap direct message kar rahe hain.\n\n"
        "User ko jawab bhejne ke liye uske forwarded message ya info card par **Reply** karein."
    )


# ================= 6. Web Server & Runner ================= #
async def web_handler(request):
    return web.Response(text="Bot is running active 24/7!")

async def start_services():
    # Web keep-alive for Koyeb / Render
    server = web.Application()
    server.router.add_get("/", web_handler)
    runner = web.AppRunner(server)
    await runner.setup()

    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Web server active on port {port}")

    # Pyrogram start
    await app.start()
    logger.info("Pyrogram Client started successfully!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
