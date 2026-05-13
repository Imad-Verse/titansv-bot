import os
import shutil
import time
import logging
import threading
from src.core.config import Config

# استيراد الدوال المساعدة العامة
from src.utils.helpers import (
    format_seconds, detect_platform_from_url, truncate_text, 
    sanitize_filename, generate_sid, clean_url, format_size,
    get_media_unique_id
)

import logging
from datetime import datetime
from rich.console import Console
from rich.theme import Theme
from src.core.config import Config
from datetime import datetime
from rich.console import Console
from rich.theme import Theme
from src.core.config import Config

# --- إعداد نظام التسجيل الاحترافي (Professional Logging System) ---
custom_theme = Theme({
    "info": "cyan",
    "warning": "bold yellow",
    "error": "bold red",
    "success": "bold green",
    "wait": "bold magenta",
})

console = Console(theme=custom_theme)
LEVEL_MAP = {"DEBUG": 10, "INFO": 20, "SUCCESS": 25, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

# File Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(Config.LOG_FILE, encoding='utf-8')]
)

class TitanLogger:
    def __init__(self, name="TitanBot"):
        self.logger = logging.getLogger(name)
        self.current_level = LEVEL_MAP.get(Config.LOG_LEVEL, 20)

    def _should_print(self, level_name):
        return LEVEL_MAP.get(level_name, 20) >= self.current_level

    def info(self, msg):
        self.logger.info(msg)
        if self._should_print("INFO"):
            console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim] ℹ️ {msg}", style="info")

    def success(self, msg):
        self.logger.info(f"SUCCESS: {msg}")
        if self._should_print("SUCCESS"):
            console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim] ✅ {msg}", style="success")

    def warning(self, msg):
        self.logger.warning(msg)
        if self._should_print("WARNING"):
            console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim] ⚠️ {msg}", style="warning")

    def error(self, msg):
        self.logger.error(msg)
        if self._should_print("ERROR"):
            console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim] ❌ {msg}", style="error")

    def critical(self, msg):
        self.logger.critical(msg)
        console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim] 💀 [bold red]{msg}[/bold red]")

    def debug(self, msg):
        self.logger.debug(msg)
        if self._should_print("DEBUG"):
            console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim] 🔍 {msg}", style="dim")

logger = TitanLogger()

def _initialize_ffmpeg():
    """التحقق من توفر FFmpeg وإعداده في بيئة النظام"""
    # 1. التحقق في PATH النظام
    if shutil.which("ffmpeg"):
        return True
    
    # 2. التحقق من المسار المخصص في الإعدادات
    if Config.FFMPEG_PATH:
        p = Config.FFMPEG_PATH / ("ffmpeg.exe" if os.name == 'nt' else "ffmpeg")
        if p.exists():
            ffmpeg_bin = str(Config.FFMPEG_PATH)
            if ffmpeg_bin not in os.environ["PATH"]:
                os.environ["PATH"] += os.pathsep + ffmpeg_bin
            return True
    
    # 3. التحقق من المسارات الشائعة (Windows)
    if os.name == 'nt':
        from pathlib import Path
        fallbacks = [
            Path(r"C:\ffmpeg\bin"),
            Path(r"C:\Program Files\ffmpeg\bin"),
            Path(os.path.expanduser("~")) / "AppData" / "Local" / "ffmpeg" / "bin"
        ]
        for path in fallbacks:
            if (path / "ffmpeg.exe").exists():
                path_str = str(path)
                if path_str not in os.environ["PATH"]:
                    os.environ["PATH"] += os.pathsep + path_str
                return True
            
    return False

FFMPEG_AVAILABLE = _initialize_ffmpeg()

def check_ffmpeg_available():
    return FFMPEG_AVAILABLE

def delayed_delete(file_path, delay=5):
    """حذف مؤجل للملفات لتجنب تعليق النظام"""
    def _delete():
        time.sleep(delay)
        try:
            from pathlib import Path
            p = Path(file_path).resolve()
            if p.exists():
                p.unlink()
        except Exception as e:
            logger.error(f"Error deleting {file_path}: {e}")
    
    threading.Thread(target=_delete, daemon=True).start()

def get_cookies_path(platform):
    """جلب مسار ملف الكوكيز بناءً على اسم المنصة"""
    path = Config.COOKIES_FILES.get(platform)
    if path and path.exists():
        return str(path)
    return None

def get_cookies_file(url):
    """تحديد ملف الكوكيز المناسب للرابط المعطى"""
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        host = ""

    # سجل تتبع لمعرفة الرابط الذي يتم فحصه
    logger.info(f"Checking cookies for host: {host}")

    for domain, platform in Config.COOKIES_MAP.items():
        if host == domain or host.endswith(f".{domain}"):
            cookie_path = Config.COOKIES_FILES.get(platform)
            
            # سجل تتبع لمعرفة المسار الذي يبحث فيه البوت
            if cookie_path:
                if cookie_path.exists():
                    if cookie_path.stat().st_size > 0:
                        logger.info(f"Cookie file FOUND and ACTIVE: {cookie_path}")
                        return cookie_path
                    else:
                        logger.error(f"Cookie file found but is EMPTY: {cookie_path}")
                else:
                    logger.info(f"Cookie file NOT FOUND at: {cookie_path}")
            
    return None

def check_disk_space(min_gb=1):
    """التأكد من وجود مساحة كافية على القرص"""
    try:
        total, used, free = shutil.disk_usage(Config.BASE_DIR)
        free_gb = free / (1024**3)
        return free_gb > min_gb, round(free_gb, 2)
    except Exception:
        return True, 100

def smart_cleanup(max_age_hours=0.5):
    """تنظيف ذكي وشامل للملفات المؤقتة"""
    current_time = time.time()
    deleted_count = 0
    
    try:
        if not Config.TITAN_DOWNLOADS.exists():
            return

        for item in Config.TITAN_DOWNLOADS.rglob('*'):
            if item.is_file():
                try:
                    if (current_time - item.stat().st_mtime) > (max_age_hours * 3600):
                        item.unlink()
                        deleted_count += 1
                except Exception:
                    continue
        
        if deleted_count > 0:
            logger.info(f"♻️ Cleanup: Removed {deleted_count} old files.")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def clean_on_startup():
    """تنظيف أولي عند بدء التشغيل"""
    smart_cleanup(max_age_hours=1)

def start_cleanup_scheduler(interval_minutes=60):
    """تشغيل مجدول لعملية التنظيف في الخلفية"""
    def _worker():
        while True:
            time.sleep(interval_minutes * 60)
            smart_cleanup(max_age_hours=1)
            
    threading.Thread(target=_worker, daemon=True).start()
    logger.debug("✅ Cleanup scheduler initialized.")

