import telebot
import threading
from collections import defaultdict
import time
from titan_bot.core.config import API_TOKEN

# تهيئة البوت
bot = telebot.TeleBot(API_TOKEN)

# Cache bot username to avoid repeated API calls
BOT_USERNAME = None
try:
    BOT_USERNAME = bot.get_me().username
except Exception:
    BOT_USERNAME = None

# المتغيرات العامة والقفل
state_lock = threading.Lock()
active_downloads = set()
MAINTENANCE_MODE = False
REPORT_LOGS = True
monthly_new_users = 0
monthly_downloads = 0
last_reset_date = time.strftime('%Y-%m')
user_requests = defaultdict(dict)
broadcast_active = False

def get_error_markup(user_id):
    from telebot import types
    from titan_bot.services.translation import translation_system
    markup = types.InlineKeyboardMarkup()
    help_text = translation_system.get(user_id, 'main_menu_buttons', key='help')
    contact_text = translation_system.get(user_id, 'contact_dev')
    
    markup.row(
        types.InlineKeyboardButton(help_text, callback_data="menu_help"),
        types.InlineKeyboardButton(contact_text, url="https://t.me/abulharith_imad")
    )
    return markup
