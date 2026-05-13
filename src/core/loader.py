import telebot
import threading
import time
from collections import defaultdict
from telebot import apihelper
from src.core.config import Config

# تهيئة البوت باستخدام التوكن من الإعدادات الجديدة
if Config.USE_LOCAL_SERVER:
    apihelper.API_URL = f"{Config.LOCAL_SERVER_URL}/bot{{0}}/{{1}}"
    apihelper.FILE_URL = f"{Config.LOCAL_SERVER_URL}/file/bot{{0}}/{{1}}"

bot = telebot.TeleBot(Config.API_TOKEN)

class BotState:
    """إدارة حالة البوت والمتغيرات العالمية بشكل منظم"""
    
    # قفل للتزامن بين الخيوط
    lock = threading.Lock()
    
    # الحالات العامة
    is_maintenance = False
    is_broadcast_active = False
    report_logs = True
    
    # إحصائيات الجلسة الحالية
    monthly_new_users = 0
    monthly_downloads = 0
    last_reset_date = time.strftime('%Y-%m')
    
    # تتبع العمليات
    active_downloads = set()
    user_requests = defaultdict(dict)
    
    # معلومات البوت
    username = None

    @classmethod
    def initialize(cls):
        """جلب معلومات البوت عند التشغيل"""
        try:
            me = bot.get_me()
            cls.username = me.username
        except Exception:
            cls.username = None

# تهيئة حالة البوت
BotState.initialize()

