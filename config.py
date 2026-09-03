import os

# Telegram API credentials
API_ID = int(os.environ.get("API_ID", "25135658"))
API_HASH = os.environ.get("API_HASH", "8bc184fb03aecc4c50f47c7f5aef3177")

# Bot Token & Owner ID
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8402575719:AAEGZBQNjbXPvExYNVxur8X0akax-0qadck")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7067885693"))

# Video & Button Links
START_VIDEO = os.environ.get("START_VIDEO", "https://files.catbox.moe/v1quvp.mp4")
BUTTON_URL = os.environ.get("BUTTON_URL", "https://t.me/+9TmHlCoc-U9lN2Q1")
