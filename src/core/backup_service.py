import os
import time
import sqlite3
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from src.core.config import Config
from src.core.loader import bot
from src.core.utils import logger

# إعداد المنفذ (Executor) للعمليات الثقيلة
executor = ThreadPoolExecutor(max_workers=3)

class BackupService:
    """خدمة النسخ الاحتياطي الاحترافية لقاعدة البيانات"""

    @staticmethod
    def _get_backup_filename():
        """توليد اسم ملف النسخة الاحتياطية بتنسيق زمني"""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return f"backup_{timestamp}.db"

    @staticmethod
    def _db_backup_worker(src_path, dst_path):
        """وظيفة النسخ الفعلي (تُشغل في Thread)"""
        try:
            # استخدام sqlite3.backup() لضمان سلامة البيانات (Online Backup)
            with sqlite3.connect(src_path) as src_conn:
                # تحسين الأداء
                src_conn.execute("PRAGMA journal_mode=WAL;")
                with sqlite3.connect(dst_path) as dst_conn:
                    src_conn.backup(dst_conn)
            return True
        except Exception as e:
            logger.error(f"Error during sqlite3 backup: {e}")
            return False

    @classmethod
    async def create_backup(cls):
        """إنشاء نسخة احتياطية بشكل غير متزامن"""
        try:
            # التأكد من وجود مجلد النسخ الاحتياطية
            os.makedirs(Config.BACKUPS_DIR, exist_ok=True)
            
            filename = cls._get_backup_filename()
            dst_path = os.path.join(Config.BACKUPS_DIR, filename)
            
            logger.info(f"Starting database backup: {filename}")
            
            # تنفيذ النسخ في executor لمنع تجميد البوت
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                executor, 
                cls._db_backup_worker, 
                str(Config.DB_FILE), 
                dst_path
            )
            
            if success:
                logger.success(f"Backup created successfully: {filename}")
                return dst_path
            else:
                return None
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return None

    @classmethod
    async def cleanup_old_backups(cls, days=7):
        """حذف النسخ الاحتياطية القديمة (أقدم من 7 أيام)"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(executor, cls._cleanup_worker, days)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    @staticmethod
    def _cleanup_worker(days):
        """وظيفة التنظيف الفعلي (تُشغل في Thread)"""
        now = time.time()
        cutoff = now - (days * 86400)
        deleted_count = 0
        
        if not os.path.exists(Config.BACKUPS_DIR):
            return

        for filename in os.listdir(Config.BACKUPS_DIR):
            file_path = os.path.join(Config.BACKUPS_DIR, filename)
            if os.path.isfile(file_path) and filename.startswith("backup_") and filename.endswith(".db"):
                file_time = os.path.getmtime(file_path)
                if file_time < cutoff:
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"Failed to delete old backup {filename}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleanup: Removed {deleted_count} old backups.")

    @classmethod
    async def send_backup_to_admin(cls, file_path):
        """إرسال ملف النسخة الاحتياطية إلى المدير"""
        if not file_path or not os.path.exists(file_path):
            return False
            
        try:
            with open(file_path, 'rb') as f:
                caption = (
                    f"📦 <b>نسخة احتياطية لقاعدة البيانات</b>\n\n"
                    f"📅 التاريخ: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                    f"📂 الملف: <code>{os.path.basename(file_path)}</code>\n"
                    f"⚙️ النظام: <b>TitanSv System</b>"
                )
                bot.send_document(
                    Config.ADMIN_ID, 
                    f, 
                    caption=caption, 
                    parse_mode="HTML"
                )
            return True
        except Exception as e:
            logger.error(f"Failed to send backup to admin: {e}")
            return False

    @classmethod
    def run_backup_task(cls):
        """تشغيل العملية الكاملة في خيط منفصل (لسهولة الاستدعاء من الكود المتزامن)"""
        def _task():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def _async_wrapper():
                path = await cls.create_backup()
                if path:
                    await cls.send_backup_to_admin(path)
                await cls.cleanup_old_backups(days=7)
            
            loop.run_until_complete(_async_wrapper())
            loop.close()

        threading.Thread(target=_task, daemon=True).start()

    @classmethod
    async def perform_full_backup_task(cls):
        """العملية الكاملة (نسخ -> إرسال -> تنظيف) بشكل غير متزامن"""
        path = await cls.create_backup()
        if path:
            await cls.send_backup_to_admin(path)
        await cls.cleanup_old_backups(days=7)
