import os
import shutil
import sqlite3
import datetime
import time
import logging
from titan_bot.core.config import DB_FILE
from titan_bot.core.loader import monthly_new_users, monthly_downloads, last_reset_date

logger = logging.getLogger("TitanBot")

def _connect_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    try:
        conn.execute('PRAGMA busy_timeout = 30000;')
    except Exception:
        pass
    return conn


def init_db():
    try:
        with _connect_db() as conn:
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.execute('PRAGMA synchronous = NORMAL;')
            conn.execute('PRAGMA foreign_keys = ON;')
            cursor = conn.cursor()
            
            # إنشاء الجداول الأساسية
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
                download_count INTEGER DEFAULT 0)''')
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS monthly_stats (
                month TEXT PRIMARY KEY, 
                users_count INTEGER DEFAULT 0, 
                downloads_count INTEGER DEFAULT 0)''')
            
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
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS broadcast_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broadcast_id TEXT,
                user_id TEXT,
                message_id TEXT
            )''')
            
            # ملاحظة: تم إلغاء جدول القنوات والمجموعات بناءً على طلب المستخدم

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_date ON download_logs(date);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_sid ON download_logs(sid);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_user ON download_logs(user_id);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_download_count ON users(download_count DESC);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_is_banned ON users(is_banned);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_broadcast_id ON broadcast_messages(broadcast_id);')
            conn.commit()
            
            # إصلاح/تحديث الأعمدة إذا لزم الأمر
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]
            
            updates = {
                'username': "TEXT",
                'registration_date': "TEXT",
                'is_banned': "INTEGER DEFAULT 0",
                'language': "TEXT DEFAULT 'ar'",
                'daily_downloads': "INTEGER DEFAULT 0",
                'last_download_date': "TEXT",
                'full_name': "TEXT",
                'join_date': "TEXT",
                'join_date': "TEXT",
                'download_count': "INTEGER DEFAULT 0",
                'default_quality': "TEXT"
            }
            
            for col, definition in updates.items():
                if col not in columns:
                    try:
                        cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
                        logger.info(f"Added missing column {col} to users table")
                    except Exception as e:
                        logger.error(f"Error adding column {col}: {e}")
            
            # تحديث أعمدة download_logs
            cursor.execute("PRAGMA table_info(download_logs)")
            log_columns = [column[1] for column in cursor.fetchall()]
            
            log_updates = {
                'sid': "TEXT",
                'size_mb': "REAL",
                'platform': "TEXT",
                'file_size': "REAL",
                'error_reason': "TEXT",
                'title': "TEXT",
                'msg_id': "TEXT"
            }
            
            for col, definition in log_updates.items():
                if col not in log_columns:
                    try:
                        cursor.execute(f"ALTER TABLE download_logs ADD COLUMN {col} {definition}")
                        logger.info(f"Added missing column {col} to download_logs table")
                    except Exception as e:
                        logger.error(f"Error adding column {col} to download_logs: {e}")

            conn.commit()
            logger.debug("Database initialized successfully with robust schema")
            
    except Exception as e: 
        logger.error(f"DB Init Error: {e}")
        # محاولات الإصلاح والنسخ الاحتياطي في حالة التلف
        try:
            if os.path.exists(DB_FILE):
                backup_file = DB_FILE + ".corrupted_" + str(int(time.time()))
                shutil.copy2(DB_FILE, backup_file)
                logger.info(f"Created backup of corrupted DB: {backup_file}")
                os.remove(DB_FILE)
                init_db() # إعادة المحاولة
        except Exception as e2:
            logger.error(f"Critical DB Repair Failure: {e2}")

def auto_backup_database():
    """إنشاء نسخة احتياطية تلقائية لقاعدة البيانات"""
    from titan_bot.core.config import BACKUPS_DIR
    try:
        if not os.path.exists(BACKUPS_DIR):
            os.makedirs(BACKUPS_DIR, exist_ok=True)
            
        backup_file = os.path.join(BACKUPS_DIR, f"users.db.backup.{int(time.time())}")
        with _connect_db() as src:
            with sqlite3.connect(backup_file) as dst:
                src.backup(dst)
        
        # الاحتفاظ بآخر 5 نسخ فقط
        backups = sorted([f for f in os.listdir(BACKUPS_DIR) if f.startswith('users.db.backup.')])
        for old_backup in backups[:-5]:
            try: os.remove(os.path.join(BACKUPS_DIR, old_backup))
            except: pass
        logger.info(f"✅ Auto-backup created: {os.path.basename(backup_file)}")
    except Exception as e:
        logger.error(f"Auto-backup error: {e}")

def check_and_repair_db():
    """فحص وإصلاح قاعدة البيانات"""
    try:
        with _connect_db() as conn:
            result = conn.execute('PRAGMA integrity_check').fetchone()
            if result[0] != 'ok':
                logger.error(f"Database integrity check failed: {result[0]}")
                return False
            conn.execute('PRAGMA optimize')
            return True
    except Exception as e:
        logger.error(f"Database check error: {e}")
        return False

def is_banned(user_id):
    """Check if user is banned."""
    try:
        with _connect_db() as conn:
            res = conn.execute('SELECT is_banned FROM users WHERE user_id=?', (str(user_id),)).fetchone()
            return res is not None and res[0] == 1
    except Exception as e:
        logger.error(f"Check ban error: {e}")
        return False

def add_user(user_id, username, full_name):
    global monthly_new_users
    try:
        with _connect_db() as conn:
            cursor = conn.cursor()
            # استخدام INSERT OR IGNORE لتفادي الأخطاء إذا كان موجوداً
            cursor.execute('INSERT OR IGNORE INTO users (user_id, join_date, username, full_name) VALUES (?, ?, ?, ?)', 
                           (str(user_id), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username, full_name))
            
            if cursor.rowcount > 0:
                monthly_new_users += 1
                update_monthly_stats(new_users=1)
                logger.info(f"New user added: {user_id}")
                return True
            return False
    except Exception as e:
        logger.error(f"Add user error: {e}")
        return False

def update_monthly_stats(new_users=0, downloads=0):
    current_month = time.strftime('%Y-%m')
    try:
        with _connect_db() as conn:
            conn.execute('''INSERT OR IGNORE INTO monthly_stats (month, users_count, downloads_count)
                            VALUES (?, 0, 0)''', (current_month,))
            if new_users > 0:
                conn.execute('UPDATE monthly_stats SET users_count = users_count + ? WHERE month=?', (new_users, current_month))
            if downloads > 0:
                conn.execute('UPDATE monthly_stats SET downloads_count = downloads_count + ? WHERE month=?', (downloads, current_month))
            conn.commit()
    except Exception as e:
        logger.error(f"Update monthly stats error: {e}")

def reset_monthly_stats():
    global monthly_new_users, monthly_downloads, last_reset_date
    current_month = time.strftime('%Y-%m')
    if current_month != last_reset_date:
        monthly_new_users = 0
        monthly_downloads = 0
        last_reset_date = current_month

def get_stats():
    global monthly_new_users, monthly_downloads
    reset_monthly_stats()
    try:
        with _connect_db() as conn:
            cursor = conn.cursor()
            
            # Total Users (Private Chats)
            total_users = cursor.execute('SELECT COUNT(user_id) FROM users').fetchone()[0]
            
            # New Users Today
            new_users_today = cursor.execute(
                "SELECT COUNT(user_id) FROM users WHERE date(join_date) = date('now', 'localtime')"
            ).fetchone()[0]
            
            current_month_str = time.strftime('%Y-%m')
            active_this_month = cursor.execute(
                "SELECT COUNT(DISTINCT user_id) FROM download_logs WHERE status='success' AND date LIKE ?", 
                (f"{current_month_str}%",)
            ).fetchone()[0]
            
            new_users_row = cursor.execute('SELECT users_count FROM monthly_stats WHERE month=?', (last_reset_date,)).fetchone()
            monthly_new_users = new_users_row[0] if new_users_row else 0
            
            downloads_row = cursor.execute('SELECT downloads_count FROM monthly_stats WHERE month=?', (last_reset_date,)).fetchone()
            monthly_downloads = downloads_row[0] if downloads_row else 0
            
            banned_users = cursor.execute('SELECT COUNT(user_id) FROM users WHERE is_banned=1').fetchone()[0]
            
            today_downloads = cursor.execute(
                "SELECT COUNT(id) FROM download_logs WHERE status='success' AND date(date) = date('now', 'localtime')"
            ).fetchone()[0]
            
            # Total Transfer Size (MB)
            total_size_mb = cursor.execute(
                "SELECT SUM(size_mb) FROM download_logs WHERE status='success'"
            ).fetchone()[0] or 0
            
            return {
                'total_users': total_users,
                'new_users_today': new_users_today,
                'banned_users': banned_users,
                'monthly_new_users': monthly_new_users,
                'monthly_downloads': monthly_downloads,
                'active_this_month': active_this_month,
                'today_downloads': today_downloads,
                'total_size_mb': total_size_mb
            }
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        return {}

def log_download(user_id, url, status, size_mb=0, platform='unknown', title='', msg_id='', sid='', error_reason=''):
    try:
        with _connect_db() as conn:
            conn.execute('''INSERT INTO download_logs (user_id, url, status, date, size_mb, platform, error_reason, title, msg_id, sid)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                         (str(user_id), url, status, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                          size_mb, platform, error_reason, title, msg_id, sid))
            
            if status == 'success':
                conn.execute('UPDATE users SET download_count = download_count + 1, last_download_date=? WHERE user_id=?', 
                             (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(user_id)))
            
            conn.commit()
    except Exception as e:
        logger.error(f"Log download error: {e}")

def get_url_by_sid(sid):
    try:
        with _connect_db() as conn:
            cursor = conn.cursor()
            res = cursor.execute('SELECT url FROM download_logs WHERE sid=? ORDER BY id DESC LIMIT 1', (sid,)).fetchone()
            return res[0] if res else None
    except Exception as e:
        logger.error(f"Get URL by SID error: {e}")
        return None

def update_download_stats():
    # تحديث إحصائيات التحميل الشهرية
    try:
        update_monthly_stats(downloads=1)
        # إرجاع القيمة الجديدة للعداد الشهري
        with _connect_db() as conn:
            logs = conn.execute('SELECT downloads_count FROM monthly_stats WHERE month=?', (last_reset_date,)).fetchone()
            return logs[0] if logs else 0
    except:
        return 0

def delete_user(user_id):
    try:
        with _connect_db() as conn:
            conn.execute('DELETE FROM users WHERE user_id=?', (str(user_id),))
            # حذف السجلات المرتبطة (تمت إضافته في التحسينات الأخيرة)
            conn.execute('DELETE FROM download_logs WHERE user_id=?', (str(user_id),))
            conn.commit()
    except Exception as e:
        logger.error(f"Delete user error: {e}")

def ban_unban(user_id, ban=True):
    try:
        with _connect_db() as conn:
            conn.execute('UPDATE users SET is_banned=? WHERE user_id=?', (1 if ban else 0, str(user_id)))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Ban/Unban error: {e}")
        return False

def get_detailed_stats():
    """الحصول على إحصائيات تفصيلية (اليوم، الأسبوع، الفشل)"""
    try:
        with _connect_db() as conn:
            cursor = conn.cursor()
            
            # تحميلات اليوم
            today_downloads = cursor.execute(
                "SELECT COUNT(id) FROM download_logs WHERE status='success' AND date(date) = date('now', 'localtime')"
            ).fetchone()[0]
            
            # تحميلات الأسبوع (تقريبية)
            week_downloads = cursor.execute(
                "SELECT COUNT(id) FROM download_logs WHERE status='success' AND date >= date('now', '-7 days')"
            ).fetchone()[0]
            
            # الفشل اليوم
            failed_today = cursor.execute(
                "SELECT COUNT(id) FROM download_logs WHERE status!='success' AND date(date) = date('now', 'localtime')"
            ).fetchone()[0]
            
            return today_downloads, week_downloads, failed_today
    except Exception as e:
        logger.error(f"Detailed stats error: {e}")
        return 0, 0, 0

def get_platform_stats():
    """الحصول على إحصائيات المنصات"""
    try:
        with _connect_db() as conn:
            cursor = conn.cursor()
            rows = cursor.execute('''
                SELECT platform, COUNT(*) as count 
                FROM download_logs 
                WHERE status='success' 
                GROUP BY platform 
                ORDER BY count DESC
            ''').fetchall()
            return rows
    except Exception as e:
        logger.error(f"Platform stats error: {e}")
        return []

def get_user_details(user_id):
    """الحصول على تفاصيل المستخدم"""
    try:
        with _connect_db() as conn:
            cursor = conn.cursor()
            res = cursor.execute('SELECT username, download_count, join_date FROM users WHERE user_id=?', (str(user_id),)).fetchone()
            if res:
                return {
                    'username': res[0],
                    'download_count': res[1],
                    'join_date': res[2]
                }
            return None
    except Exception as e:
        logger.error(f"Get user details error: {e}")
        return None

def get_top_users(limit=8):
    """الحصول على قائمة أكثر المستخدمين نشاطاً"""
    try:
        with _connect_db() as conn:
            cursor = conn.cursor()
            rows = cursor.execute('''
                SELECT user_id, username, download_count 
                FROM users 
                ORDER BY download_count DESC 
                LIMIT ?
            ''', (limit,)).fetchall()
            return rows
    except Exception as e:
        logger.error(f"Get top users error: {e}")
        return []

def get_user_languages():
    """Load user language preferences."""
    try:
        with _connect_db() as conn:
            rows = conn.execute(
                "SELECT user_id, language FROM users WHERE language IS NOT NULL AND language != ''"
            ).fetchall()
        result = []
        for uid, lang in rows:
            if not lang:
                continue
            try:
                uid_val = int(uid)
            except Exception:
                uid_val = uid
            result.append((uid_val, lang))
        return result
    except Exception as e:
        logger.error(f"Load user languages error: {e}")
        return []

def check_user_exists(user_id):
    """التحقق من وجود المستخدم في قاعدة البيانات"""
    try:
        with _connect_db() as conn:
            # استخدام 1 بدلاً من * للأداء
            res = conn.execute('SELECT 1 FROM users WHERE user_id=?', (str(user_id),)).fetchone()
            return res is not None
    except Exception as e:
        logger.error(f"Check user exist error: {e}")
        return False
def set_user_pref(user_id, key, value):
    """Set a user preference safely."""
    # خارطة للمفاتيح المسموح بها لتجنب حقن SQL
    allowed_columns = {
        'default_quality': 'default_quality'
    }
    
    column = allowed_columns.get(key)
    if not column:
        return False
        
    try:
        with _connect_db() as conn:
            # استخدام اسم العمود من القائمة البيضاء مباشرة
            conn.execute(f'UPDATE users SET {column}=? WHERE user_id=?', (value, str(user_id)))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Set user pref error: {e}")
        return False

def get_user_pref(user_id, key):
    """Get a user preference safely."""
    allowed_columns = {
        'default_quality': 'default_quality'
    }
    
    column = allowed_columns.get(key)
    if not column:
        return None
        
    try:
        with _connect_db() as conn:
            res = conn.execute(f'SELECT {column} FROM users WHERE user_id=?', (str(user_id),)).fetchone()
            return res[0] if res else None
    except Exception as e:
        logger.error(f"Get user pref error: {e}")
        return None

def get_user_rank(user_id):
    """الحصول على رتبة المستخدم بناءً على عدد التحميلات"""
    try:
        with _connect_db() as conn:
            cursor = conn.cursor()
            # ترتيب المستخدمين حسب التحميلات ومعرفة مكانه
            query = """
                SELECT rank FROM (
                    SELECT user_id, RANK() OVER (ORDER BY download_count DESC) as rank
                    FROM users
                ) WHERE user_id = ?
            """
            res = cursor.execute(query, (str(user_id),)).fetchone()
            return res[0] if res else 0
    except Exception as e:
        # Fallback if window functions are not supported
        try:
            with _connect_db() as conn:
                user_count = conn.execute('SELECT download_count FROM users WHERE user_id=?', (str(user_id),)).fetchone()
                if not user_count: return 0
                rank = conn.execute('SELECT COUNT(*) + 1 FROM users WHERE download_count > ?', (user_count[0],)).fetchone()
                return rank[0]
        except:
            return 0

def get_total_users_count():
    """الحصول على إجمالي عدد المستخدمين"""
    try:
        with _connect_db() as conn:
            res = conn.execute('SELECT COUNT(*) FROM users').fetchone()
            return res[0] if res else 0
    except Exception as e:
        logger.error(f"Get total users count error: {e}")
        return 0

def log_broadcast_messages_batch(messages_batch):
    """messages_batch is a list of tuples: (broadcast_id, user_id, message_id)"""
    if not messages_batch: return
    try:
        with _connect_db() as conn:
            conn.executemany('INSERT INTO broadcast_messages (broadcast_id, user_id, message_id) VALUES (?, ?, ?)', messages_batch)
            conn.commit()
    except Exception as e:
        logger.error(f"Log broadcast batch error: {e}")

def get_broadcast_messages(broadcast_id):
    try:
        with _connect_db() as conn:
            cursor = conn.cursor()
            rows = cursor.execute('SELECT user_id, message_id FROM broadcast_messages WHERE broadcast_id=?', (str(broadcast_id),)).fetchall()
            return rows
    except Exception as e:
        logger.error(f"Get broadcast messages error: {e}")
        return []

def delete_broadcast_messages_db(broadcast_id):
    try:
        with _connect_db() as conn:
            conn.execute('DELETE FROM broadcast_messages WHERE broadcast_id=?', (str(broadcast_id),))
            conn.commit()
    except Exception as e:
        logger.error(f"Delete broadcast messages error: {e}")
