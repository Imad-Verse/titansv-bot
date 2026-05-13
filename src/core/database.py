import os
import shutil
import sqlite3
import datetime
import time
import logging
from contextlib import contextmanager
from src.core.config import Config

logger = logging.getLogger("TitanBot")

def _connect_db():
    """إنشاء اتصال مع قاعدة البيانات مع إعدادات الأداء"""
    conn = sqlite3.connect(Config.DB_FILE, timeout=30)
    try:
        conn.execute('PRAGMA busy_timeout = 30000;')
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous = NORMAL;')
        conn.execute('PRAGMA foreign_keys = ON;')
    except Exception:
        pass
    return conn

@contextmanager
def db_session():
    """مدير سياق للتعامل الآمن مع قاعدة البيانات"""
    conn = _connect_db()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """تهيئة قاعدة البيانات وإنشاء الجداول إذا لم تكن موجودة"""
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            
            # جدول المستخدمين
            cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY, 
                username TEXT, 
                registration_date TEXT, 
                is_banned INTEGER DEFAULT 0,
                language TEXT DEFAULT 'ar',
                daily_downloads INTEGER DEFAULT 0,
                last_download_date TEXT,
                full_name TEXT,
                join_date TEXT,
                download_count INTEGER DEFAULT 0,
                default_quality TEXT)''')
            
            # جدول الإحصائيات الشهرية
            cursor.execute('''CREATE TABLE IF NOT EXISTS monthly_stats (
                month TEXT PRIMARY KEY, 
                users_count INTEGER DEFAULT 0, 
                downloads_count INTEGER DEFAULT 0)''')
            
            # جدول سجلات التحميل
            cursor.execute('''CREATE TABLE IF NOT EXISTS download_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                user_id TEXT, 
                date TEXT, 
                url TEXT, 
                status TEXT,
                platform TEXT,
                file_size REAL,
                size_mb REAL,
                error_reason TEXT,
                title TEXT,
                msg_id TEXT,
                sid TEXT)''')
            
            # جدول رسائل البث
            cursor.execute('''CREATE TABLE IF NOT EXISTS broadcast_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broadcast_id TEXT,
                user_id TEXT,
                message_id TEXT)''')

            # جدول التخزين المؤقت (Caching)
            cursor.execute('''CREATE TABLE IF NOT EXISTS media_cache (
                url TEXT, 
                unique_id TEXT,
                quality_type TEXT, 
                file_id TEXT, 
                title TEXT, 
                description TEXT,
                duration TEXT,
                size_mb REAL,
                platform TEXT,
                timestamp TEXT)''')
            
            # إضافة عمود unique_id إذا لم يكن موجوداً (Migration)
            try:
                cursor.execute('ALTER TABLE media_cache ADD COLUMN unique_id TEXT')
            except: pass

            # الفهارس (Indexes) لسرعة البحث
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_date ON download_logs(date);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_sid ON download_logs(sid);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_is_banned ON users(is_banned);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cache_url ON media_cache(url);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cache_unique ON media_cache(unique_id);')
            
            conn.commit()
            logger.info("Database initialized successfully.")
            
    except Exception as e: 
        logger.error(f"DB Init Error: {e}")
        _repair_db_if_corrupted()

def _repair_db_if_corrupted():
    """محاولة إصلاح قاعدة البيانات في حال التلف"""
    try:
        if os.path.exists(Config.DB_FILE):
            backup_file = f"{Config.DB_FILE}.corrupted_{int(time.time())}"
            shutil.copy2(Config.DB_FILE, backup_file)
            os.remove(Config.DB_FILE)
            init_db()
            logger.warning(f"Corrupted DB backed up to {backup_file} and re-initialized.")
    except Exception as e:
        logger.error(f"Critical DB Repair Failure: {e}")

def auto_backup_database():
    """إنشاء نسخة احتياطية لقاعدة البيانات"""
    try:
        Config.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        backup_file = Config.BACKUPS_DIR / f"users.db.backup.{int(time.time())}"
        
        with _connect_db() as src:
            with sqlite3.connect(backup_file) as dst:
                src.backup(dst)
        
        # الحفاظ على آخر 5 نسخ فقط
        backups = sorted(list(Config.BACKUPS_DIR.glob('users.db.backup.*')))
        for old_backup in backups[:-5]:
            try: old_backup.unlink()
            except: pass
        logger.info(f"✅ Auto-backup created: {backup_file.name}")
    except Exception as e:
        logger.error(f"Auto-backup error: {e}")

def is_banned(user_id):
    """التحقق مما إذا كان المستخدم محظوراً"""
    try:
        with db_session() as conn:
            res = conn.execute('SELECT is_banned FROM users WHERE user_id=?', (str(user_id),)).fetchone()
            return res is not None and res[0] == 1
    except Exception:
        return False

def add_user(user_id, username, full_name):
    """إضافة مستخدم جديد وتحديث الإحصائيات"""
    from src.core.loader import BotState
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute('INSERT OR IGNORE INTO users (user_id, join_date, username, full_name, registration_date) VALUES (?, ?, ?, ?, ?)', 
                           (str(user_id), now, username, full_name, now))
            
            if cursor.rowcount > 0:
                with BotState.lock:
                    BotState.monthly_new_users += 1
                update_monthly_stats(new_users=1)
                logger.info(f"New user added: {user_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"Add user error: {e}")
        return False

def delete_user(user_id):
    """حذف مستخدم من قاعدة البيانات"""
    try:
        with db_session() as conn:
            conn.execute('DELETE FROM users WHERE user_id=?', (str(user_id),))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        return False

def check_user_exists(user_id):
    """التحقق من وجود المستخدم"""
    try:
        with db_session() as conn:
            res = conn.execute('SELECT 1 FROM users WHERE user_id=?', (str(user_id),)).fetchone()
            return res is not None
    except Exception:
        return False

def set_user_language(user_id, lang_code):
    """تحديث لغة المستخدم"""
    try:
        with db_session() as conn:
            conn.execute('UPDATE users SET language=? WHERE user_id=?', (lang_code, str(user_id)))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Set user language error: {e}")
        return False

def update_monthly_stats(new_users=0, downloads=0):
    """تحديث الإحصائيات الشهرية في قاعدة البيانات"""
    current_month = time.strftime('%Y-%m')
    try:
        with db_session() as conn:
            conn.execute('''INSERT OR IGNORE INTO monthly_stats (month, users_count, downloads_count)
                            VALUES (?, 0, 0)''', (current_month,))
            if new_users > 0:
                conn.execute('UPDATE monthly_stats SET users_count = users_count + ? WHERE month=?', (new_users, current_month))
            if downloads > 0:
                conn.execute('UPDATE monthly_stats SET downloads_count = downloads_count + ? WHERE month=?', (downloads, current_month))
            conn.commit()
    except Exception as e:
        logger.error(f"Update monthly stats error: {e}")

def get_stats():
    """جلب إحصائيات شاملة للبوت"""
    from src.core.loader import BotState
    current_month = time.strftime('%Y-%m')
    
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            
            total_users = cursor.execute('SELECT COUNT(user_id) FROM users').fetchone()[0]
            new_users_today = cursor.execute(
                "SELECT COUNT(user_id) FROM users WHERE date(join_date) = date('now', 'localtime')"
            ).fetchone()[0]
            
            banned_users = cursor.execute('SELECT COUNT(user_id) FROM users WHERE is_banned=1').fetchone()[0]
            today_downloads = cursor.execute(
                "SELECT COUNT(id) FROM download_logs WHERE status='success' AND date(date) = date('now', 'localtime')"
            ).fetchone()[0]
            
            total_size_mb = cursor.execute(
                "SELECT SUM(size_mb) FROM download_logs WHERE status='success'"
            ).fetchone()[0] or 0
            
            # مزامنة إحصائيات الشهر مع الـ Loader
            m_stats = cursor.execute('SELECT users_count, downloads_count FROM monthly_stats WHERE month=?', (current_month,)).fetchone()
            if m_stats:
                with BotState.lock:
                    BotState.monthly_new_users = m_stats[0]
                    BotState.monthly_downloads = m_stats[1]
            
            return {
                'total_users': total_users,
                'new_users_today': new_users_today,
                'banned_users': banned_users,
                'monthly_new_users': BotState.monthly_new_users,
                'monthly_downloads': BotState.monthly_downloads,
                'today_downloads': today_downloads,
                'total_size_mb': total_size_mb
            }
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        return {}

def get_user_details(user_id):
    """جلب تفاصيل كاملة عن المستخدم"""
    try:
        with db_session() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            res = cursor.execute('SELECT * FROM users WHERE user_id=?', (str(user_id),)).fetchone()
            return dict(res) if res else None
    except Exception as e:
        logger.error(f"Get user details error: {e}")
        return None

def get_top_users(limit=10):
    """جلب قائمة بأكثر المستخدمين استخداماً للبوت"""
    try:
        with db_session() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM users ORDER BY download_count DESC LIMIT ?', (limit,)).fetchall()
            return [dict(row) for row in rows]
    except Exception:
        return []

def get_detailed_stats():
    """جلب إحصائيات تفصيلية (أسبوعية واليوم فاشلة)"""
    try:
        with db_session() as conn:
            cursor = conn.cursor()
            
            # تحميلات الأسبوع (آخر 7 أيام)
            week_dl = cursor.execute(
                "SELECT COUNT(id) FROM download_logs WHERE status='success' AND date >= date('now', '-7 days')"
            ).fetchone()[0]
            
            # فشل اليوم
            failed_today = cursor.execute(
                "SELECT COUNT(id) FROM download_logs WHERE status='failed' AND date(date) = date('now', 'localtime')"
            ).fetchone()[0]
            
            return 0, week_dl, failed_today
    except Exception as e:
        logger.error(f"Get detailed stats error: {e}")
        return 0, 0, 0

def log_download(user_id, url, status, size_mb=0, platform='unknown', title='', msg_id='', sid='', error_reason=''):
    """تسجيل عملية تحميل جديدة"""
    try:
        with db_session() as conn:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute('''INSERT INTO download_logs (user_id, url, status, date, size_mb, platform, error_reason, title, msg_id, sid)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (str(user_id), url, status, now, size_mb, platform, error_reason, title, msg_id, sid))
            
            if status == 'success':
                conn.execute('UPDATE users SET download_count = download_count + 1, last_download_date=? WHERE user_id=?', (now, str(user_id)))
            
            conn.commit()
    except Exception as e:
        logger.error(f"Log download error: {e}")

def get_url_by_sid(sid):
    """جلب رابط من خلال معرف الجلسة (sid)"""
    try:
        with db_session() as conn:
            res = conn.execute('SELECT url FROM download_logs WHERE sid=? ORDER BY id DESC LIMIT 1', (sid,)).fetchone()
            return res[0] if res else None
    except Exception:
        return None

def update_download_stats():
    """تحديث عداد التحميلات الشهري"""
    from src.core.loader import BotState
    current_month = time.strftime('%Y-%m')
    try:
        update_monthly_stats(downloads=1)
        with db_session() as conn:
            logs = conn.execute('SELECT downloads_count FROM monthly_stats WHERE month=?', (current_month,)).fetchone()
            if logs:
                with BotState.lock:
                    BotState.monthly_downloads = logs[0]
                return logs[0]
        return 0
    except:
        return 0

def ban_unban(user_id, ban=True):
    """حظر أو إلغاء حظر مستخدم"""
    try:
        with db_session() as conn:
            conn.execute('UPDATE users SET is_banned=? WHERE user_id=?', (1 if ban else 0, str(user_id)))
            conn.commit()
        return True
    except Exception:
        return False

def get_user_languages():
    """تحميل تفضيلات اللغة لكافة المستخدمين"""
    try:
        with db_session() as conn:
            rows = conn.execute("SELECT user_id, language FROM users WHERE language IS NOT NULL AND language != ''").fetchall()
        
        result = []
        for uid, lang in rows:
            try: uid_val = int(uid)
            except: uid_val = uid
            result.append((uid_val, lang))
        return result
    except Exception:
        return []

def get_user_language(user_id):
    """جلب لغة مستخدم معين"""
    try:
        with db_session() as conn:
            res = conn.execute('SELECT language FROM users WHERE user_id=?', (str(user_id),)).fetchone()
            return res[0] if res and res[0] else 'ar'
    except Exception:
        return 'ar'

def set_user_pref(user_id, key, value):
    """تحديث إعداد خاص بالمستخدم بأمان"""
    allowed_columns = {'default_quality': 'default_quality'}
    column = allowed_columns.get(key)
    if not column: return False
        
    try:
        with db_session() as conn:
            conn.execute(f'UPDATE users SET {column}=? WHERE user_id=?', (value, str(user_id)))
            conn.commit()
            return True
    except Exception:
        return False

def get_user_pref(user_id, key):
    """جلب إعداد خاص بالمستخدم"""
    allowed_columns = {'default_quality': 'default_quality'}
    column = allowed_columns.get(key)
    if not column: return None
        
    try:
        with db_session() as conn:
            res = conn.execute(f'SELECT {column} FROM users WHERE user_id=?', (str(user_id),)).fetchone()
            return res[0] if res else None
    except Exception:
        return None

def get_active_user_ids():
    """جلب قائمة بكل المستخدمين النشطين"""
    try:
        with db_session() as conn:
            rows = conn.execute('SELECT user_id FROM users WHERE is_banned=0').fetchall()
            return [row[0] for row in rows]
    except Exception:
        return []

def log_broadcast_messages_batch(messages_batch):
    """تسجيل مجموعة من رسائل البث دفعة واحدة"""
    if not messages_batch: return
    try:
        with db_session() as conn:
            conn.executemany('INSERT INTO broadcast_messages (broadcast_id, user_id, message_id) VALUES (?, ?, ?)', messages_batch)
            conn.commit()
    except Exception as e:
        logger.error(f"Log broadcast batch error: {e}")

def get_broadcast_messages(broadcast_id):
    """جلب رسائل بث معينة"""
    try:
        with db_session() as conn:
            rows = conn.execute('SELECT user_id, message_id FROM broadcast_messages WHERE broadcast_id=?', (str(broadcast_id),)).fetchall()
            return rows
    except Exception:
        return []

def get_total_users_count():
    """جلب إجمالي عدد المستخدمين"""
    try:
        with db_session() as conn:
            res = conn.execute('SELECT COUNT(user_id) FROM users').fetchone()
            return res[0] if res else 0
    except Exception:
        return 0

def get_user_rank(user_id):
    """جلب رتبة المستخدم بناءً على عدد التحميلات"""
    try:
        with db_session() as conn:
            # الرتبة هي عدد المستخدمين الذين لديهم تحميلات أكثر + 1
            res = conn.execute('''
                SELECT COUNT(*) + 1 FROM users 
                WHERE download_count > (SELECT download_count FROM users WHERE user_id = ?)
            ''', (str(user_id),)).fetchone()
            return res[0] if res else 0
    except Exception:
        return 0

def delete_broadcast_messages_db(broadcast_id):
    """حذف سجلات رسائل البث"""
    try:
        with db_session() as conn:
            conn.execute('DELETE FROM broadcast_messages WHERE broadcast_id=?', (str(broadcast_id),))
            conn.commit()
    except Exception:
        pass

def get_cached_media(url, quality_type):
    """جلب بيانات الوسائط المخزنة مؤقتاً باستخدام المعرف الفريد"""
    from src.core.utils import get_media_unique_id
    unique_id = get_media_unique_id(url)
    
    try:
        with db_session() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # نحاول البحث بالـ unique_id أولاً، ثم بالـ url كخطة بديلة
            res = cursor.execute('SELECT * FROM media_cache WHERE unique_id=? AND quality_type=?', (unique_id, quality_type)).fetchone()
            if not res:
                res = cursor.execute('SELECT * FROM media_cache WHERE url=? AND quality_type=?', (url, quality_type)).fetchone()
            return dict(res) if res else None
    except Exception as e:
        logger.error(f"Get cache error: {e}")
        return None

def save_to_cache(url, quality_type, file_id, title='', description='', duration='', size_mb=0, platform='unknown'):
    """حفظ وسائط في التخزين المؤقت"""
    from src.core.utils import get_media_unique_id
    unique_id = get_media_unique_id(url)
    
    try:
        with db_session() as conn:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # نحذف أي سجل قديم بنفس المعرف والجودة قبل الإضافة لضمان التحديث
            conn.execute('DELETE FROM media_cache WHERE (unique_id=? OR url=?) AND quality_type=?', (unique_id, url, quality_type))
            
            conn.execute('''INSERT INTO media_cache 
                            (url, unique_id, quality_type, file_id, title, description, duration, size_mb, platform, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (url, unique_id, quality_type, file_id, title, description, duration, size_mb, platform, now))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Save cache error: {e}")
        return False

