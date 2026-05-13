import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from src.core.utils import logger
from src.services.translation import translation_system

class DownloadQueueManager:
    """
    Manages background download tasks to prevent blocking the main TeleBot threads
    and handles smart queuing when the server is under high load.
    """
    def __init__(self, bot, max_concurrent=15):
        self.bot = bot
        self.max_concurrent = max_concurrent
        self.active_users = set()
        self.queue = deque()
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        
    def submit(self, uid, chat_id, message_id, task_func, *args, **kwargs):
        """
        Submits a task. Returns:
        - "already_processing" if user is currently downloading.
        - "started" if there is a slot.
        - int (position) if added to the queue.
        """
        with self.lock:
            if uid in self.active_users:
                return "already_processing"
            
            task = {
                'uid': uid,
                'chat_id': chat_id,
                'message_id': message_id,
                'task_func': task_func,
                'args': args,
                'kwargs': kwargs
            }
            
            if len(self.active_users) < self.max_concurrent:
                self.active_users.add(uid)
                self.executor.submit(self._run_task, task)
                return "started"
            else:
                self.queue.append(task)
                return len(self.queue)

    def cancel_task(self, uid):
        """
        Removes a user from the waiting queue if they cancel.
        """
        with self.lock:
            for task in list(self.queue):
                if task['uid'] == uid:
                    self.queue.remove(task)
                    return True
        return False

    def _run_task(self, task):
        uid = task['uid']
        try:
            task['task_func'](*task['args'], **task['kwargs'])
        except Exception as e:
            logger.error(f"Queue Task Error for UID {uid}: {e}")
        finally:
            self._on_task_finished(uid)

    def _on_task_finished(self, uid):
        with self.lock:
            self.active_users.discard(uid)
            if self.queue:
                next_task = self.queue.popleft()
                next_uid = next_task['uid']
                chat_id = next_task['chat_id']
                self.active_users.add(next_uid)
                
                # Notify the next user that their download is starting
                try:
                    self.bot.send_message(
                        chat_id, 
                        translation_system.get(next_uid, 'queue_turn_arrived', default="🚀 حان دورك! جاري معالجة طلبك الآن..."),
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                
                self.executor.submit(self._run_task, next_task)
