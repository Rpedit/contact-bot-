import os

# Environment variables se values read karega (Render/Koyeb/Local ke liye)
API_ID = int(os.environ.get("API_ID", "25135658"))          # my.telegram.org se lein
API_HASH = os.environ.get("API_HASH", "8bc184fb03aecc4c50f47c7f5aef3177")     # my.telegram.org se lein
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8402575719:AAEGZBQNjbXPvExYNVxur8X0akax-0qadck")   # @BotFather se lein
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7067885693"))     # @userinfobot se mili aapki User ID
