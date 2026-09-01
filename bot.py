import re
from pyrogram import Client, filters
from pyrogram.types import Message
from config import API_ID, API_HASH, BOT_TOKEN, ADMIN_ID

app = Client(
    "report_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Admin message ID aur User ID ko memory me link karne ke liye
report_db = {}


# --- /start Command ---
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.reply_text(
            "👑 **Admin Control Active!**\n\n"
            "Jab koi user issue ya report bhejega, wo yahan aayega.\n"
            "Aapko bas us report message par **Swipe / Reply** karna hai."
        )
    else:
        await message.reply_text(
            "👋 **Namaste!**\n\n"
            "Aapko jo bhi issue, query ya report bhejni hai, yahan message ya photo/video ke sath bhej dijiye.\n"
            "Humari team jald hi check karke aapko reply karegi."
        )


# --- User Incoming Report (User -> Admin) ---
@app.on_message(filters.private & ~filters.user(ADMIN_ID))
async def handle_user_report(client: Client, message: Message):
    user = message.from_user
    username = f"@{user.username}" if user.username else "No Username"
    user_info = f"👤 **From:** {user.first_name} ({username})\n🆔 **User ID:** `{user.id}`"

    if message.text:
        admin_msg = await client.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 **Nayi Report Aayi!**\n\n{user_info}\n\n📝 **Report:**\n{message.text}"
        )
    else:
        caption = f"🚨 **Nayi Report Aayi!**\n\n{user_info}\n\n📝 **Caption:**\n{message.caption or 'No Caption'}"
        admin_msg = await message.copy(chat_id=ADMIN_ID, caption=caption)

    # Database mapping store karein
    report_db[admin_msg.id] = user.id

    await message.reply_text("✅ **Aapki report submit ho gayi hai!** Jald hi jawab diya jayega.")


# --- Admin Reply Handler (Admin -> User) ---
@app.on_message(filters.private & filters.user(ADMIN_ID) & filters.reply)
async def handle_admin_reply(client: Client, message: Message):
    replied_msg = message.reply_to_message
    target_user_id = report_db.get(replied_msg.id)

    # Restart fallback: Text/caption se User ID extract karna
    if not target_user_id:
        text_content = replied_msg.text or replied_msg.caption or ""
        match = re.search(r"User ID:\*\* `(\d+)`", text_content)
        if match:
            target_user_id = int(match.group(1))

    if target_user_id:
        try:
            if message.text:
                await client.send_message(
                    chat_id=target_user_id,
                    text=f"📩 **Admin Response (Aapki Report Ka Jawab):**\n\n{message.text}"
                )
            else:
                caption = f"📩 **Admin Response:**\n\n{message.caption or ''}"
                await message.copy(chat_id=target_user_id, caption=caption)

            await message.reply_text("✅ Reply successfully user ko bhej diya gaya!")
        except Exception as e:
            await message.reply_text(f"❌ Error: `{e}`")
    else:
        await message.reply_text("⚠️ Is message ka User ID nahi mila. Kripya user ki aayi hui report par hi reply karein.")


print("Bot Start Ho Raha Hai...")
app.run()
