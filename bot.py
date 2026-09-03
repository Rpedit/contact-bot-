import os
import re
import asyncio
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID, START_VIDEO, BUTTON_URL

app = Client(
    "contact_relay_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Admin chat message ID -> User ID mapping
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

    user_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Fast Movie Bots List ↗", url=BUTTON_URL)]
    ])

    # 1. Send Welcome Video / Animation
    try:
        await message.reply_video(
            video=START_VIDEO,
            caption=caption_text,
            reply_markup=user_buttons
        )
    except Exception:
        try:
            await message.reply_animation(
                animation=START_VIDEO,
                caption=caption_text,
                reply_markup=user_buttons
            )
        except Exception:
            await message.reply_text(
                text=caption_text,
                reply_markup=user_buttons
            )

    # 2. Agar Admin ne /start kiya ho toh Admin Panel show karega
    if user.id == ADMIN_ID:
        admin_text = (
            "👆 This is the message your users will see.\n\n"
            "👇 This is the message you see as an administrator.\n\n"
            "👑 **You are the administrator of this bot!**"
        )
        admin_buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚙️ Bot settings", callback_data="bot_settings"),
                InlineKeyboardButton("🎧 Support ↗", url="https://t.me/your_support")
            ]
        ])
        await message.reply_text(
            text=admin_text,
            reply_markup=admin_buttons
        )


# ================= 2. User Message (User -> Admin) ================= #
@app.on_message(filters.private & ~filters.user(ADMIN_ID))
async def user_to_admin(client: Client, message: Message):
    user = message.from_user

    # 1. Forward original message to Admin
    fwd = await message.forward(ADMIN_ID)
    msg_map[fwd.id] = user.id

    # 2. Details Card for direct reference & fallback ID parsing
    info_text = (
        f"📢 **Message sent by {user.first_name}**\n"
        f"`[{user.id}]` `[#id{user.id}]`\n\n"
        f"👉 Jawab dene ke liye is message par reply karein."
    )
    info_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 User profile", url=f"tg://user?id={user.id}")]
    ])

    info_msg = await client.send_message(
        chat_id=ADMIN_ID,
        text=info_text,
        reply_markup=info_btn
    )
    msg_map[info_msg.id] = user.id

    # 3. User Confirmation (Popup style: aakar 3-4 second me delete)
    confirm_msg = await message.reply_text("Message sent! ⏱️")
    asyncio.create_task(auto_delete_message(confirm_msg, delay=3))


# ================= 3. Admin Reply (Admin -> User) ================= #
@app.on_message(filters.private & filters.user(ADMIN_ID) & filters.reply)
async def admin_to_user(client: Client, message: Message):
    replied_msg = message.reply_to_message
    target_user_id = msg_map.get(replied_msg.id)

    # Fallback 1: Agar forwarded message se direct user ID milti hai
    if not target_user_id and replied_msg.forward_from:
        target_user_id = replied_msg.forward_from.id

    # Fallback 2: Bot restart hone par card text se ID extract karega
    if not target_user_id:
        text_content = replied_msg.text or replied_msg.caption or ""
        match = re.search(r"#id(\d+)", text_content)
        if match:
            target_user_id = int(match.group(1))

    if target_user_id:
        try:
            await message.copy(chat_id=target_user_id)
            
            # Message copy hone ke baad Admin reply par thumbs up reaction
            try:
                await client.send_reaction(
                    chat_id=ADMIN_ID,
                    message_id=message.id,
                    emoji="👍"
                )
            except Exception:
                pass
        except Exception as e:
            await message.reply_text(f"❌ Send fail: `{e}`")
    else:
        await message.reply_text("⚠️ User ID nahi mili! Forwarded message ya info card par reply karein.")


# ================= 4. Admin Normal Message Handler ================= #
@app.on_message(filters.private & filters.user(ADMIN_ID) & ~filters.reply & ~filters.command("start"))
async def admin_normal_msg(client: Client, message: Message):
    await message.reply_text(
        "ℹ️ **Admin Alert:** Aap direct message kar rahe hain.\n\n"
        "User ko jawab bhejne ke liye user ke forwarded message ya card par **Swipe karke Reply** karein."
    )


# ================= 5. Web Server & Runner ================= #
async def web_handler(request):
    return web.Response(text="Bot is running active 24/7!")

async def start_services():
    # Render / VPS Web Keep-Alive Port
    server = web.Application()
    server.router.add_get("/", web_handler)
    runner = web.AppRunner(server)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server active on port {port}")

    # Start Pyrogram Client
    await app.start()
    print("Bot Start Ho Gaya!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(start_services())
