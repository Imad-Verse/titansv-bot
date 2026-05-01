import os
import sys
from dotenv import load_dotenv

# تحميل المتغيرات
load_dotenv()

def _split_env_list(value):
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]

def _get_int_env(name, default):
    try:
        return int(os.getenv(name, default))
    except Exception:
        return default

# التوكن
API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not API_TOKEN:
    print("CRITICAL: TELEGRAM_BOT_TOKEN not found in .env file! Exiting...")
    sys.exit(1)

ADMIN_ID = int(os.getenv('ADMIN_ID', 362464035))

# المسارات
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# مجلد السجلات
LOGS_DIR = os.path.join(BASE_DIR, "logs")
# المجلد التنظيمي للتحميلات - تم نقله للجذر
TITAN_DOWNLOADS = os.path.join(BASE_DIR, "downloads")
# مسارات التحميل (متوافقة مع TitanSv_bot.py)
ADMIN_DIR = os.path.join(TITAN_DOWNLOADS, "admin_downloads")
USERS_DIR = os.path.join(TITAN_DOWNLOADS, "users_downloads")
BACKUPS_DIR = os.path.join(BASE_DIR, "data", "backups")
COOKIES_DIR = os.path.join(BASE_DIR, "cookies")

# إنشاء المجلدات
for d in [TITAN_DOWNLOADS, ADMIN_DIR, USERS_DIR, BACKUPS_DIR, COOKIES_DIR, LOGS_DIR]:
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

# ملفات البيانات
DB_FILE = os.path.join(BASE_DIR, "data", "users.db")
LOG_FILE = os.path.join(LOGS_DIR, "bot.log")
RESTART_LOG = os.path.join(LOGS_DIR, "restart_log.txt")

# توقيع البوت
BOT_SIG = "🤖 العملاق للتحميل | @TitanSv_bot"

# إعدادات ملفات الكوكيز (أسماء الملفات الفعلية)
COOKIES_FILES = {
    'instagram': os.path.join(COOKIES_DIR, 'www.instagram.com_cookies.txt'),
    'facebook': os.path.join(COOKIES_DIR, 'www.facebook.com_cookies.txt'),
    'tiktok': os.path.join(COOKIES_DIR, 'www.tiktok.com_cookies.txt'),
    'twitter': os.path.join(COOKIES_DIR, 'x.com_cookies.txt'),
    'youtube': os.path.join(COOKIES_DIR, 'www.youtube.com_cookies.txt'),
    'threads': os.path.join(COOKIES_DIR, 'www.instagram.com_cookies.txt')
}

COOKIES_MAP = {
    'instagram.com': 'instagram',
    'instagr.am': 'instagram',
    'ig.me': 'instagram',
    'facebook.com': 'facebook', 
    'fb.watch': 'facebook',
    'fb.com': 'facebook',
    'tiktok.com': 'tiktok',
    'twitter.com': 'twitter',
    'x.com': 'twitter',
    'youtube.com': 'youtube',
    'youtu.be': 'youtube',
    'threads.net': 'threads'
}

# قنوات الاشتراك الإجباري
DEFAULT_CHANNELS = ['@chiliashop_dz', '@alShehabDz']
CHANNELS = _split_env_list(os.getenv('CHANNELS', '')) or DEFAULT_CHANNELS

# Limits
MAX_FILE_SIZE_MB = _get_int_env('MAX_FILE_SIZE_MB', 2048)
MAX_FILE_SIZE = _get_int_env('MAX_FILE_SIZE', 0)
if MAX_FILE_SIZE <= 0:
    MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
TELEGRAM_UPLOAD_LIMIT_MB = _get_int_env('TELEGRAM_UPLOAD_LIMIT_MB', 20)
TELEGRAM_UPLOAD_LIMIT = _get_int_env('TELEGRAM_UPLOAD_LIMIT', 0)
if TELEGRAM_UPLOAD_LIMIT <= 0:
    TELEGRAM_UPLOAD_LIMIT = TELEGRAM_UPLOAD_LIMIT_MB * 1024 * 1024
MAX_VIDEO_DURATION = _get_int_env('MAX_VIDEO_DURATION', 7200) # 2 Hours

# Allowed platforms
DEFAULT_ALLOWED_PLATFORMS = [
    'youtube', 'instagram', 'facebook', 'tiktok', 'twitter', 'pinterest', 'threads', 'snapchat'
]
ALLOWED_PLATFORMS = [p.lower() for p in (_split_env_list(os.getenv('ALLOWED_PLATFORMS', '')) or DEFAULT_ALLOWED_PLATFORMS)]
