import os
import shutil
import time
import logging
import threading
import secrets
from titan_bot.core.config import LOG_FILE, COOKIES_FILES, COOKIES_MAP, BASE_DIR, TITAN_DOWNLOADS, FFMPEG_PATH

def _initialize_ffmpeg():
    """تحقق من توفر FFmpeg وتحديث المسار إذا لزم الأمر"""
    # 1. تحقق إذا كان متاحاً بالفعل في PATH
    if shutil.which("ffmpeg"):
        return True
    
    # 2. تحقق من المسار المخصص (إذا تم تعيينه في .env)
    if FFMPEG_PATH:
        # إذا كان المسار يشير للمجلد الذي يحتوي على ffmpeg.exe
        if os.path.exists(os.path.join(FFMPEG_PATH, "ffmpeg.exe")):
            if FFMPEG_PATH not in os.environ["PATH"]:
                os.environ["PATH"] += os.pathsep + FFMPEG_PATH
            return True
        # إذا كان المسار يشير للملف نفسه مباشرة (اختياري)
        elif os.path.exists(FFMPEG_PATH) and os.path.isfile(FFMPEG_PATH) and "ffmpeg" in FFMPEG_PATH.lower():
            return True
    
    # 3. تحقق من مسارات شائعة أخرى كاحتياط
    fallbacks = [
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "ffmpeg", "bin")
    ]
    for path in fallbacks:
        if os.path.exists(os.path.join(path, "ffmpeg.exe")):
            if path not in os.environ["PATH"]:
                os.environ["PATH"] += os.pathsep + path
            return True
            
    return False

FFMPEG_AVAILABLE = _initialize_ffmpeg()

def check_ffmpeg_available():
    return FFMPEG_AVAILABLE

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TitanBot")

def format_seconds(seconds):
    """تنسيق الوقت"""
    if not seconds: return "00:00"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def delayed_delete(file_path, delay=5):
    """حذف مؤجل للملفات"""
    import threading
    def _delete():
        time.sleep(delay)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Error deleting {file_path}: {e}")
    threading.Thread(target=_delete, daemon=True).start()

def detect_platform_from_url(url):
    """اكتشاف المنصة من الرابط"""
    from urllib.parse import urlparse
    try:
        domain = urlparse(url).netloc.lower()
        if 'instagram' in domain: return 'instagram'
        if 'facebook' in domain or 'fb.watch' in domain or 'fb.com' in domain: return 'facebook'
        if 'tiktok' in domain: return 'tiktok'
        if 'twitter' in domain or 'x.com' in domain: return 'twitter'
        if 'youtube' in domain or 'youtu.be' in domain: return 'youtube'
        if 'pinterest' in domain or 'pin.it' in domain: return 'pinterest'
        if 'threads.net' in domain: return 'threads'
        if 'snapchat' in domain: return 'snapchat'
    except: pass
    return 'other'

def get_cookies_file(url):
    """جلب ملف الكوكيز المناسب"""
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        host = ""
    for domain_key, platform_key in COOKIES_MAP.items():
        if host == domain_key or host.endswith(f".{domain_key}"):
            cookie_file = COOKIES_FILES.get(platform_key)
            if cookie_file and os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 0:
                return cookie_file
    return None

def truncate_text(text, max_length=100):
    """تقصير النص"""
    if not text: return ""
    return text[:max_length] + "..." if len(text) > max_length else text

def check_disk_space(min_gb=1):
    """فحص مساحة القرص"""
    try:
        total, used, free = shutil.disk_usage(BASE_DIR)
        free_gb = free / (2**30)
        return free_gb > min_gb, round(free_gb, 2)
    except:
        return True, 100

def smart_cleanup(max_age_hours=0.5):
    """تنظيف ذكي للملفات القديمة"""
    current_time = time.time()
    count = 0
    # تنظيف مجلد التحميلات الرئيسي
    for root, dirs, files in os.walk(TITAN_DOWNLOADS):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                if (current_time - os.path.getmtime(file_path)) > (max_age_hours * 3600):
                    os.remove(file_path)
                    count += 1
            except Exception as e:
                logger.error(f"Error removing file {file_path}: {e}")
    if count > 0:
        logger.info(f"✅ Cleanup completed: {count} files removed")

def clean_on_startup():
    """تنظيف عند بداية التشغيل"""
    logger.debug("✅ Cleaning old files...")
    smart_cleanup(max_age_hours=1) # حذف الملفات الأقدم من ساعة

def start_cleanup_scheduler(interval_minutes=60):
    """جدولة التنظيف الدوري"""
    def _run():
        while True:
            time.sleep(interval_minutes * 60)
            try:
                smart_cleanup(max_age_hours=1)
            except Exception as e:
                logger.error(f"Scheduled cleanup error: {e}")
    
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    logger.debug("✅ Cleanup scheduler started")

def sanitize_filename(name):
    """تنظيف اسم الملف من الأحرف غير المسموحة"""
    import re
    name = name.replace('\0', '')
    # Keep only alphanumeric, spaces, dots, dashes, underscores
    name = re.sub(r'[^\w\s.-]', '', name)
    return name.strip() or "unnamed_file"

def generate_sid(prefix=""):
    """Generate short unique ids safe for callback_data and filenames."""
    return f"{prefix}{secrets.token_hex(6)}"
