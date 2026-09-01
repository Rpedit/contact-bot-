import os

# Environment variables se values read karega (Render/Koyeb/Local ke liye)
API_ID = int(os.environ.get("API_ID", "12345678"))          # my.telegram.org se lein
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")     # my.telegram.org se lein
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")   # @BotFather se lein
ADMIN_ID = int(os.environ.get("ADMIN_ID", "987654321"))     # @userinfobot se mili aapki User ID
