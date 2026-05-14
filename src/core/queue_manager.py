import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from src.core.utils import logger
from src.services.translation import translation_system

class DownloadQueueManager:
    """
    إدارة متقدمة لطوابير التحميل لضمان عدم توقف البوت والتعامل مع ضغط المستخدمين.
    """
    def __init__(self, bot, max_concurrent=15):
        self.bot = bot
        self.max_concurrent = max_concurrent
        self.active_users = {} # {uid: task_info}
        self.queue = deque() # List of task_info
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        
    def submit(self, uid, chat_id, message_id, task_func, *args, **kwargs):
        """
        إرسال مهمة جديدة للطابور.
        """
        with self.lock:
            # منع المستخدم من تشغيل أكثر من عملية تحميل في نفس الوقت
            if uid in self.active_users:
                return "already_processing"
            
            # التحقق مما إذا كان المستخدم موجوداً بالفعل في الطابور
            if any(t['uid'] == uid for t in self.queue):
                return "already_in_queue"
            
            task = {
                'uid': uid,
                'chat_id': chat_id,
                'message_id': message_id,
                'task_func': task_func,
                'args': args,
                'kwargs': kwargs,
                'submitted_at': time.time()
            }
            
            if len(self.active_users) < self.max_concurrent:
                self.active_users[uid] = task
                self.executor.submit(self._run_task, task)
                return "started"
            else:
                self.queue.append(task)
                return len(self.queue)

    def get_status(self):
        """جلب حالة الطابور الحالية"""
        with self.lock:
            return {
                'active_count': len(self.active_users),
                'waiting_count': len(self.queue),
                'max_concurrent': self.max_concurrent
            }

    def cancel_task(self, uid):
        """إلغاء مهمة من الطابور المنتظر"""
        with self.lock:
            original_len = len(self.queue)
            self.queue = deque([t for t in self.queue if t['uid'] != uid])
            return len(self.queue) < original_len

    def _run_task(self, task):
        uid = task['uid']
        try:
            logger.info(f"🚀 Queue: Starting task for UID {uid}")
            task['task_func'](*task['args'], **task['kwargs'])
        except Exception as e:
            logger.error(f"❌ Queue Task Error for UID {uid}: {e}")
        finally:
            self._on_task_finished(uid)

    def _on_task_finished(self, uid):
        with self.lock:
            if uid in self.active_users:
                del self.active_users[uid]
            
            if self.queue:
                next_task = self.queue.popleft()
                next_uid = next_task['uid']
                chat_id = next_task['chat_id']
                
                self.active_users[next_uid] = next_task
                
                # إبلاغ المستخدم بأن دوره قد حان
                try:
                    self.bot.send_message(
                        chat_id, 
                        translation_system.get(next_uid, 'queue_turn_arrived', default="🚀 <b>حان دورك!</b> جاري معالجة طلبك الآن..."),
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                
                self.executor.submit(self._run_task, next_task)

    def get_user_position(self, uid):
        """معرفة ترتيب مستخدم معين في الطابور"""
        with self.lock:
            for i, task in enumerate(self.queue):
                if task['uid'] == uid:
                    return i + 1
        return 0
