import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# تحميل المتغيرات من ملف .env
load_dotenv()

class Config:
    """إعدادات البوت المركزية باستخدام نظام الكلاسات و Pathlib"""
    
    # --- التوكن والتحقق ---
    API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not API_TOKEN or ":" not in API_TOKEN:
        print("CRITICAL: TELEGRAM_BOT_TOKEN is invalid or not found in .env!")
        sys.exit(1)

    ADMIN_ID = int(os.getenv('ADMIN_ID', 362464035))
    LOG_LEVEL = os.getenv('TITAN_LOG_LEVEL', 'INFO').upper()

    # --- Local Telegram API Server ---
    LOCAL_SERVER_URL = os.getenv('LOCAL_SERVER_URL', 'http://localhost:8081')
    USE_LOCAL_SERVER = os.getenv('USE_LOCAL_SERVER', 'False').lower() == 'true'

    # --- المسارات (Pathlib) ---
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    
    LOGS_DIR = BASE_DIR / "logs"
    DATA_DIR = BASE_DIR / "data"
    BACKUPS_DIR = DATA_DIR / "backups"
    COOKIES_DIR = BASE_DIR / "cookies"
    TITAN_DOWNLOADS = BASE_DIR / "downloads"
    
    ADMIN_DOWNLOADS = TITAN_DOWNLOADS / "admin_downloads"
    USERS_DOWNLOADS = TITAN_DOWNLOADS / "users_downloads"
    
    DB_FILE = DATA_DIR / "users.db"
    LOG_FILE = LOGS_DIR / "bot.log"
    RESTART_LOG = LOGS_DIR / "restart_log.txt"

    # --- توقيع البوت ---
    BOT_SIG = "🤖 العملاق للتحميل | @TitanSv_bot"

    # --- نظام البروكسي (Proxy Rotation) ---
    PROXIES_FILE = DATA_DIR / "proxies.txt"
    PROXIES_URL = os.getenv('PROXIES_URL', '')
    USE_PROXIES = os.getenv('USE_PROXIES', 'False').lower() == 'true'

    # --- إعدادات الوسائط والكوكيز ---
    COOKIES_FILES = {
        'instagram': COOKIES_DIR / 'instagram.com_cookies.txt',
        'facebook': COOKIES_DIR / 'facebook.com_cookies.txt',
        'tiktok': COOKIES_DIR / 'tiktok.com_cookies.txt',
        'twitter': COOKIES_DIR / 'twitter.com_cookies.txt',
        'youtube': COOKIES_DIR / 'youtube.com_cookies.txt',
        'threads': COOKIES_DIR / 'instagram.com_cookies.txt'
    }

    COOKIES_MAP = {
        'instagram.com': 'instagram', 'instagr.am': 'instagram', 'ig.me': 'instagram',
        'facebook.com': 'facebook', 'fb.watch': 'facebook', 'fb.com': 'facebook',
        'tiktok.com': 'tiktok', 'twitter.com': 'twitter', 'x.com': 'twitter',
        'youtube.com': 'youtube', 'youtu.be': 'youtube', 'threads.net': 'threads'
    }

    # --- قنوات الاشتراك الإجباري ---
    _raw_channels = os.getenv('CHANNELS', '@chiliashop_dz,@alShehabDz')
    CHANNELS = [v.strip() for v in _raw_channels.split(",") if v.strip()]

    # --- القيود (Limits) ---
    MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', 2048))
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', MAX_FILE_SIZE_MB * 1024 * 1024))
    
    TELEGRAM_UPLOAD_LIMIT_MB = int(os.getenv('TELEGRAM_UPLOAD_LIMIT_MB', 50))
    TELEGRAM_UPLOAD_LIMIT = int(os.getenv('TELEGRAM_UPLOAD_LIMIT', TELEGRAM_UPLOAD_LIMIT_MB * 1024 * 1024))
    
    DOCUMENT_THRESHOLD_MB = int(os.getenv('DOCUMENT_THRESHOLD_MB', 50))
    DOCUMENT_THRESHOLD = DOCUMENT_THRESHOLD_MB * 1024 * 1024
    
    MAX_VIDEO_DURATION = int(os.getenv('MAX_VIDEO_DURATION', 7200)) # 2 Hours

    # --- المنصات المسموح بها ---
    _default_platforms = 'youtube,instagram,facebook,tiktok,twitter,pinterest,threads,snapchat'
    _raw_platforms = os.getenv('ALLOWED_PLATFORMS', _default_platforms)
    ALLOWED_PLATFORMS = [p.strip().lower() for p in _raw_platforms.split(",") if p.strip()]

    # --- المسارات الخارجية ---
    FFMPEG_PATH = Path(os.getenv('FFMPEG_PATH')) if os.getenv('FFMPEG_PATH') else None

    @classmethod
    def initialize_directories(cls):
        """إنشاء كافة المجلدات المطلوبة عند بدء التشغيل"""
        directories = [
            cls.LOGS_DIR, cls.DATA_DIR, cls.BACKUPS_DIR, 
            cls.COOKIES_DIR, cls.TITAN_DOWNLOADS, 
            cls.ADMIN_DOWNLOADS, cls.USERS_DOWNLOADS
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

# تنفيذ إنشاء المجلدات فور الاستيراد (للحفاظ على التوافق)
Config.initialize_directories()


