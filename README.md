# Telegram Support & Contact Relay Bot

A fast, lightweight, and asynchronous Telegram Support and Contact Relay bot built with Python, Pyrogram v2, and SQLite.

Developed and maintained by **#rpeditz_07** 🚀

---

## ⚡ Features

- **Direct Message Relay**: User messages are seamlessly forwarded to the bot owner's private chat.
- **One-Click Reply**: Admin can reply directly to any user by swiping on forwarded cards.
- **No External Database**: Powered completely by built-in `SQLite` (`bot.db`).
- **Scoped Commands**: Clean interface for users (only `/start`), full moderation tools for the admin.
- **Broadcasting Tool**: Send mass announcements to all registered users via `/broadcast`.
- **User Moderation**: In-built `/ban` and `/unban` management.
- **24/7 Keep-Alive**: Built-in `aiohttp` web server for uninterrupted hosting on Render, Koyeb, or VPS.

---

## 🛠️ Environment Variables (`config.py`)

| Variable | Description |
|---|---|
| `API_ID` | Telegram App API ID from [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | Telegram App API Hash |
| `BOT_TOKEN` | Bot token obtained from [@BotFather](https://t.me/BotFather) |
| `ADMIN_ID` | Telegram User ID of the owner |
| `START_VIDEO` | Direct link to welcome video/animation |
| `BUTTON_URL` | Channel or support link |

---

## 🚀 Deployment

### Local / VPS
```bash
git clone <your-repo-link>
cd <repo-folder>
pip install -r requirements.txt
python bot.py
