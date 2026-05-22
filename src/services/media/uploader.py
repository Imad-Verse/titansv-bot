import os
from telebot import types
from src.core.loader import bot
from src.services.translation import translation_system

class ProgressFileReader:
    def __init__(self, filename, callback, *args, **kwargs):
        self.filename = filename
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.size = os.path.getsize(filename)
        self.file = open(filename, 'rb')
        self.read_bytes = 0

    def read(self, size=-1):
        data = self.file.read(size)
        self.read_bytes += len(data)
        if self.callback:
            percent = int((self.read_bytes / self.size) * 100) if self.size > 0 else 0
            self.callback(percent, *self.args, **self.kwargs)
        return data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.file.close()

    def __getattr__(self, attr):
        return getattr(self.file, attr)

    def __iter__(self):
        return self

    def __next__(self):
        data = self.file.readline()
        if not data:
            raise StopIteration
        self.read_bytes += len(data)
        if self.callback:
            percent = int((self.read_bytes / self.size) * 100) if self.size > 0 else 0
            self.callback(percent, *self.args, **self.kwargs)
        return data

    def __len__(self):
        return self.size

def upload_progress_callback(percent, msg_id, chat_id, text, last_percent_dict):
    """تحديث شريط التقدم الفعلي أثناء الرفع"""
    if percent - last_percent_dict['value'] >= 10 or percent >= 100:
        if update_progress_message(msg_id, chat_id, text, percent):
            last_percent_dict['value'] = percent

def create_progress_message(chat_id, text, percent=0, markup=None):
    try:
        bar = "▰" * int(percent / 10) + "▱" * (10 - int(percent / 10))
        msg = bot.send_message(chat_id, f"{text}\n{bar} {percent}%", reply_markup=markup)
        return msg
    except:
        return None

def update_progress_message(msg_id, chat_id, text, percent, markup=None):
    try:
        bar = "▰" * int(percent / 10) + "▱" * (10 - int(percent / 10))
        bot.edit_message_text(f"{text}\n{bar} {percent}%", chat_id, msg_id, reply_markup=markup)
        return True
    except:
        return False

def _delete_progress_message(chat_id, progress_msg):
    try:
        if progress_msg:
            bot.delete_message(chat_id, progress_msg.message_id)
    except:
        pass
