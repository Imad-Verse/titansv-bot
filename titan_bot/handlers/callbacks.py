from telebot import types
import os
import shutil
import sys
from titan_bot.core.loader import bot, get_error_markup
import titan_bot.core.loader as loader
from titan_bot.core.config import ADMIN_ID, BASE_DIR, RESTART_LOG, DB_FILE
from titan_bot.services.translation import translation_system
from titan_bot.core.database import get_stats
from titan_bot.handlers.user import help_command, language_command, contact_button, send_main_menu, bots_list_command
from titan_bot.core.utils import logger
import titan_bot.services.download as download_service

ADMIN_CALLBACKS = {
    'refresh_stats',
    'toggle_maint',
    'more_stats',
    'ban_unban_ask',
    'backup_db',
    'check_cookies',
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
    
    if call.data.startswith('lang_'):
        lang_code = call.data.split('_')[1]
        translation_system.set_language(uid, lang_code)
        try:
            import sqlite3
            with sqlite3.connect(DB_FILE, timeout=30) as conn:
                try:
                    conn.execute("PRAGMA busy_timeout = 30000;")
                except Exception:
                    pass
                conn.execute('UPDATE users SET language=? WHERE user_id=?', (lang_code, str(uid)))
                conn.commit()
        except:
            pass
        
        msg = translation_system.get(uid, 'language_set', language=translation_system.LANGUAGES[lang_code])
        bot.answer_callback_query(call.id, msg)
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        send_main_menu(call.message.chat.id, uid, call.from_user.username, call.from_user.first_name)
        return

    elif call.data == 'menu_start_download':
        bot.answer_callback_query(call.id, translation_system.get(uid, 'send_link_prompt'))
        return

    elif call.data == 'menu_help':
        bot.answer_callback_query(call.id)
        help_command(build_mock_message(call))
        return

    elif call.data == 'menu_language':
        bot.answer_callback_query(call.id)
        language_command(build_mock_message(call))
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
        from titan_bot.handlers.user import stats_command
        bot.answer_callback_query(call.id)
        stats_command(build_mock_message(call))
        return

    elif call.data == 'cancel_broadcast':
        with loader.state_lock:
            loader.broadcast_active = False
        bot.answer_callback_query(call.id, "⚠️ جاري إلغاء الإذاعة...")
        return

    elif call.data == 'menu_back_to_main':
        bot.answer_callback_query(call.id)
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        send_main_menu(call.message.chat.id, uid, call.from_user.username, call.from_user.first_name)
        return

    elif call.data == 'menu_admin_panel' and uid == ADMIN_ID:
        from titan_bot.handlers.admin import send_admin_panel
        bot.answer_callback_query(call.id)
        send_admin_panel(call.message.chat.id)
        return

    elif call.data == 'broadcast_menu' and uid == ADMIN_ID:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("📢 لكل المستخدمين", callback_data="bc_all_users"),
            types.InlineKeyboardButton("👤 لمستخدم محدد", callback_data="bc_specific_user"),
            types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_broadcast_menu")
        )
        bot.edit_message_text("📢 <b>اختر نوع الإذاعة:</b>", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")

    elif call.data == 'bc_all_users' and uid == ADMIN_ID:
        if loader.broadcast_active:
             bot.answer_callback_query(call.id, "⚠️ هناك إذاعة نشطة بالفعل!", show_alert=True)
             return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_broadcast"))
        msg = bot.edit_message_text("📝 <b>أرسل الآن الرسالة للجميع:</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
        bot.register_next_step_handler(msg, download_service.perform_all_broadcast)

    elif call.data == 'bc_specific_user' and uid == ADMIN_ID:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="cancel_broadcast"))
        msg = bot.edit_message_text("👤 <b>أرسل الآيدي (ID) للمستخدم المستهدف:</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
        bot.register_next_step_handler(msg, ask_broadcast_id_step)
        
    elif call.data == 'cancel_broadcast_menu' and uid == ADMIN_ID:
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass

    elif call.data == 'refresh_stats' and uid == ADMIN_ID:
        # NOTE: This is usually handled by admin.py because it's in ADMIN_CALLBACKS.
        # This block is reached only if ADMIN_CALLBACKS filter logic changes.
        from titan_bot.handlers.admin import send_admin_panel
        bot.answer_callback_query(call.id)
        send_admin_panel(call.message.chat.id, call.message.message_id)

    elif call.data == "pc_status" and uid == ADMIN_ID:
        total, used, free = shutil.disk_usage(BASE_DIR)
        disk_percent = (used / total) * 100
        free_gb = free / (2**30)
        status_msg = f"🖥 <b>حالة السيرفر:</b>\n💾 <b>القرص:</b> {disk_percent:.1f}% ({free_gb:.2f} GB free)"
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, status_msg, parse_mode="HTML")

    elif call.data == "sys_restart" and uid == ADMIN_ID:
        bot.answer_callback_query(call.id, "🔁 إعادة تشغيل...")
        with open(RESTART_LOG, "w") as f: f.write(str(call.message.chat.id))
        os.execl(sys.executable, sys.executable, *sys.argv)

    elif call.data.startswith('dl_'):
        # dl_quality|sid
        try:
            quality, sid = call.data.replace("dl_", "").split("|", 1)
            
            from titan_bot.core.database import get_url_by_sid
            url = get_url_by_sid(sid)
            
            if not url:
                bot.answer_callback_query(call.id, translation_system.get(uid, 'link_expired'), show_alert=True)
                return
                
            # محاكاة رسالة تحتوي على الرابط للبدء بالتحميل
            dummy_message = call.message
            dummy_message.text = url
            dummy_message.from_user = call.from_user
            
            # حذف رسالة اختيار الجودة
            try: bot.delete_message(call.message.chat.id, call.message.message_id)
            except: pass
            
            from titan_bot.services.download import process_download
            process_download(dummy_message, quality)
        except Exception as e:
            logger.error(f"Callback DL Error: {e}")
            bot.answer_callback_query(call.id, translation_system.get(uid, 'request_processing_failed'), show_alert=True)
        return

    elif call.data == 'cancel_broadcast':
        bot.answer_callback_query(call.id, "تم الإلغاء")
        bot.clear_step_handler_by_chat_id(call.message.chat.id)
        loader.broadcast_active = False 
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass

    elif call.data == "verify_sub": 
        from titan_bot.handlers.user import check_sub
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
            from titan_bot.core.database import get_url_by_sid
            url = get_url_by_sid(sid)
            
            if not url:
                bot.answer_callback_query(call.id, translation_system.get(uid, 'link_expired'), show_alert=True)
                return
            
            bot.answer_callback_query(call.id, translation_system.get(uid, "processing"))
            
            # محاكاة رسالة لبدء التحميل
            dummy_message = call.message
            dummy_message.text = url
            dummy_message.from_user = call.from_user
            
            quality = "audio" if action == "audio" else "mute"
            
            from titan_bot.services.download import process_local_conversion
            process_local_conversion(dummy_message, sid, quality)
            
        except Exception as e:
            logger.error(f"Action {call.data} error: {e}")
            bot.answer_callback_query(call.id, translation_system.get(uid, 'operation_failed'), show_alert=True)

    elif call.data.startswith('copy_link'):
        try:
            _, sid = call.data.split('|', 1)
            from titan_bot.core.database import get_url_by_sid
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
            req = loader.user_requests.get(uid, {})
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
        except:
            pass
        try:
            bot.answer_callback_query(call.id)
        except:
            pass

def ask_broadcast_id_step(message):
    if message.text == '/cancel' or message.text == '❌ إلغاء':
        bot.send_message(message.chat.id, "✅ تم الإلغاء")
        return
        
    uid = message.text.strip()
    if not uid.isdigit():
        bot.send_message(message.chat.id, translation_system.get(message.from_user.id, 'id_must_be_numeric'))
        bot.register_next_step_handler(message, ask_broadcast_id_step)
        return
        
    msg = bot.send_message(message.chat.id, f"📝 <b>أرسل الرسالة التي تريد إرسالها إلى {uid}:</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, lambda m: download_service.perform_specific_broadcast(m, uid))
