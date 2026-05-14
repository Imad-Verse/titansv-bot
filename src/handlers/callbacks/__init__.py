from telebot import types
import os
import shutil
import sys
from src.core.config import Config
from src.core.loader import bot, BotState
from src.utils.ui import get_error_markup
from src.core.utils import logger
from src.services.translation import translation_system
from src.core.database import get_stats, get_url_by_sid
from src.services.download import process_download, process_local_conversion
from src.handlers.user import help_command, contact_button, send_main_menu, bots_list_command
from src.core.loader import download_queue

ADMIN_CALLBACKS = {
    'refresh_stats',
    'toggle_maint',
    'more_stats',
    'ban_unban_ask',
    'backup_db',
    'check_cookies',
    'pc_status',
    'sys_restart',
    'menu_admin_panel',
    'broadcast_menu',
}

def build_mock_message(call):
    class MockMessage:
        def __init__(self, user, chat):
            self.from_user = user
            self.chat = chat
            self.message_id = 0
            self.text = ""
    return MockMessage(call.from_user, call.message.chat)

@bot.callback_query_handler(func=lambda call: (call.data or "") not in ADMIN_CALLBACKS)
def callback_query(call):
    uid = call.from_user.id
    


    if call.data == 'menu_start_download':
        bot.answer_callback_query(call.id, translation_system.get(uid, 'send_link_prompt'))
        return

    elif call.data == 'menu_help':
        bot.answer_callback_query(call.id)
        help_command(build_mock_message(call))
        return



    elif call.data == 'menu_contact':
        bot.answer_callback_query(call.id)
        contact_button(build_mock_message(call))
        return

    elif call.data == 'menu_bots_list':
        bot.answer_callback_query(call.id)
        bots_list_command(build_mock_message(call))
        return

    elif call.data == 'menu_user_stats':
        from src.handlers.user import stats_command
        bot.answer_callback_query(call.id)
        stats_command(build_mock_message(call))
        return

    elif call.data == 'cancel_broadcast':
        with BotState.lock:
            BotState.is_broadcast_active = False
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        bot.answer_callback_query(call.id, "⚠️ تم إلغاء العملية")
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        send_main_menu(call.message.chat.id, uid, call.from_user.username, call.from_user.first_name)
        return

    elif call.data == 'menu_back_to_main':
        bot.answer_callback_query(call.id)
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        send_main_menu(call.message.chat.id, uid, call.from_user.username, call.from_user.first_name)
        return

    elif call.data.startswith('dl_'):
        # dl_quality|sid
        try:
            quality, sid = call.data.replace("dl_", "").split("|", 1)
            url = get_url_by_sid(sid)
            
            if not url:
                bot.answer_callback_query(call.id, translation_system.get(uid, 'link_expired'), show_alert=True)
                return
                
            # محاكاة رسالة تحتوي على الرابط للبدء بالتحميل
            dummy_message = call.message
            dummy_message.from_user = call.from_user
            
            # حذف رسالة اختيار الجودة
            try: bot.delete_message(call.message.chat.id, call.message.message_id)
            except: pass
            
            status = download_queue.submit(uid, call.message.chat.id, call.message.message_id, process_download, dummy_message, quality, url=url)
            if status == "already_processing":
                bot.answer_callback_query(call.id, translation_system.get(uid, 'already_processing'), show_alert=True)
            elif status == "already_in_queue":
                bot.answer_callback_query(call.id, translation_system.get(uid, 'already_in_queue', default="⚠️ أنت موجود بالفعل في طابور الانتظار!"), show_alert=True)
            elif status == "started":
                bot.answer_callback_query(call.id, translation_system.get(uid, 'starting_download', default="جاري بدء التحميل..."))
            else:
                pos = status
                msg = translation_system.get(uid, 'added_to_queue', pos=pos, default=f"⏳ السيرفر مزدحم حالياً. تم وضع طلبك في الطابور (الترتيب: {pos}). سيبدأ التحميل تلقائياً.")
                bot.answer_callback_query(call.id, "⏳ طابور الانتظار", show_alert=False)
                bot.send_message(call.message.chat.id, msg)
                
        except Exception as e:
            logger.error(f"Callback DL Error: {e}")
            bot.answer_callback_query(call.id, translation_system.get(uid, 'request_processing_failed'), show_alert=True)
        return

    elif call.data == "verify_sub": 
        from src.handlers.user import check_sub
        not_subscribed = check_sub(uid)
        
        if not_subscribed:
             bot.answer_callback_query(call.id, translation_system.get(uid, 'subscription_incomplete'), show_alert=True)
        else:
             bot.answer_callback_query(call.id, translation_system.get(uid, 'subscription_verified'))
             bot.edit_message_text(
                 translation_system.get(uid, 'subscribed_success'),
                 call.message.chat.id, 
                 call.message.message_id, 
                 parse_mode="HTML"
             )



    elif call.data.startswith(('audio_', 'mute_')):
        try:
            action, sid = call.data.split('_', 1)
            # نتحقق من وجود الرابط للتأكد من عدم انتهاء الجلسة
            if not get_url_by_sid(sid):
                bot.answer_callback_query(call.id, translation_system.get(uid, 'link_expired'), show_alert=True)
                return
            
            bot.answer_callback_query(call.id, translation_system.get(uid, "processing"))
            
            dummy_message = call.message
            dummy_message.from_user = call.from_user
            quality = "audio" if action == "audio" else "mute"
            
            status = download_queue.submit(uid, call.message.chat.id, call.message.message_id, process_local_conversion, dummy_message, sid, quality)
            if status == "already_processing":
                bot.send_message(call.message.chat.id, translation_system.get(uid, 'already_processing'))
            elif status == "already_in_queue":
                bot.send_message(call.message.chat.id, translation_system.get(uid, 'already_in_queue', default="⚠️ أنت موجود بالفعل في طابور الانتظار!"))
            elif status != "started":
                pos = status
                msg = translation_system.get(uid, 'added_to_queue', pos=pos, default=f"⏳ السيرفر مزدحم حالياً. تم وضع طلبك في الطابور (الترتيب: {pos}). سيبدأ التحويل تلقائياً.")
                bot.send_message(call.message.chat.id, msg)
            
        except Exception as e:
            logger.error(f"Action {call.data} error: {e}")
            bot.answer_callback_query(call.id, translation_system.get(uid, 'operation_failed'), show_alert=True)

    elif call.data.startswith('copy_link'):
        try:
            _, sid = call.data.split('|', 1)
            url = get_url_by_sid(sid)
            
            if url:
                bot.send_message(call.message.chat.id, url)
                bot.answer_callback_query(call.id, translation_system.get(uid, 'link_sent'))
            else:
                bot.answer_callback_query(call.id, translation_system.get(uid, 'link_missing'), show_alert=True)
        except Exception as e:
            logger.error(f"Copy link error: {e}")
            bot.answer_callback_query(call.id, translation_system.get(uid, 'operation_failed'), show_alert=True)

    elif call.data.startswith('cancel_dl|'):
        try:
            _, sid = call.data.split('|', 1)
            req = BotState.user_requests.get(uid, {})
            if req.get('sid') != sid:
                bot.answer_callback_query(call.id, translation_system.get(uid, 'no_active_download'), show_alert=True)
                return
            event = req.get('cancel_event')
            if event:
                event.set()
            bot.answer_callback_query(call.id, translation_system.get(uid, 'download_cancelled'))
            try:
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            except:
                pass
        except Exception as e:
            logger.error(f"Cancel download error: {e}")
            bot.answer_callback_query(call.id, translation_system.get(uid, 'operation_failed'), show_alert=True)

    elif call.data == "delete_me":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
        except:
            pass
