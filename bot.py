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

msg_map = {}


# ================= Helper: Auto-Delete Message ================= #
async def auto_delete_message(msg: Message, delay: int = 3):
    """Message aane ke baad specified seconds me apne aap delete/remove ho jayega"""
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


# ================= 1. /start Handler ================= #
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user = message.from_user

    if user.id == ADMIN_ID:
        await message.reply_text(
            "👑 **Admin Mode Active Hai!**\n\n"
            "Bot bilkul theek kaam kar raha hai.\n"
            "User ban kar test karne ke liye kisi doosre account se message karein."
        )
        return

    caption_text = (
        f"HEY 👨‍💻 {user.mention},\n\n"
        f"I'M THE OWNER OF 💬 **HD PRO SEARCH BOT**\n\n"
        f"👉 NEW MOVIES / SERIES BOTS DEKHNA HO TO NICHE DIYE GAYE BUTTON PE CLICK KARE 👇\n\n"
        f"🔔 AEK SE BHI ZYADA FAST & ADVANCED MOVIE SEARCH BOTS AVAILABLE!"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Fast Movie Bots List ↗", url=BUTTON_URL)]
    ])

    try:
        await message.reply_video(
            video=START_VIDEO,
            caption=caption_text,
            reply_markup=buttons
        )
    except Exception:
        await message.reply_text(
            text=caption_text,
            reply_markup=buttons
        )


# ================= 2. User Message (User -> Admin) ================= #
@app.on_message(filters.private & ~filters.user(ADMIN_ID))
async def user_to_admin(client: Client, message: Message):
    user = message.from_user

    # 1. Forward to Admin
    fwd = await message.forward(ADMIN_ID)
    msg_map[fwd.id] = user.id

    # 2. Details Card
    info_text = (
        f"📢 **Message sent by {user.first_name}!!**\n"
        f"`[{user.id}]` `[#id{user.id}]`\n\n"
        f"👉 To answer, reply to this message."
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

    # 3. User Confirmation (Aayega aur 3 second me auto-delete ho jayega)
    confirm_msg = await message.reply_text("✅ Message sent!")
    asyncio.create_task(auto_delete_message(confirm_msg, delay=3))


# ================= 3. Admin Reply (Admin -> User) ================= #
@app.on_message(filters.private & filters.user(ADMIN_ID) & filters.reply)
async def admin_to_user(client: Client, message: Message):
    replied_msg = message.reply_to_message
    target_user_id = msg_map.get(replied_msg.id)

    if not target_user_id and replied_msg.forward_from:
        target_user_id = replied_msg.forward_from.id

    if not target_user_id:
        text_content = replied_msg.text or replied_msg.caption or ""
        match = re.search(r"#id(\d+)", text_content)
        if match:
            target_user_id = int(match.group(1))

    if target_user_id:
        try:
            await message.copy(chat_id=target_user_id)
            try:
                await message.react("👍")
            except Exception:
                pass
        except Exception as e:
            await message.reply_text(f"❌ Send fail: `{e}`")
    else:
        await message.reply_text("⚠️ User ID nahi mili. Kripya forwarded message ya card par reply karein.")


# ================= 4. Admin Normal Message Handler ================= #
@app.on_message(filters.private & filters.user(ADMIN_ID) & ~filters.reply)
async def admin_normal_msg(client: Client, message: Message):
    await message.reply_text(
        "ℹ️ **Admin Alert:** Aap Admin account se message kar rahe hain.\n\n"
        "User ko jawab bhejne ke liye user ke forwarded message par **Swipe karke Reply** karein."
    )


# ================= 5. Web Server & Runner ================= #
async def web_handler(request):
    return web.Response(text="Bot is running active 24/7!")

async def start_services():
    # Render Web Server
    server = web.Application()
    server.router.add_get("/", web_handler)
    runner = web.AppRunner(server)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server active on port {port}")

    # Start Pyrogram
    await app.start()
    print("Bot Start Ho Gaya!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
