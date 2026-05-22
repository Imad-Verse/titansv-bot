import time
import telebot
from telebot import types
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.core.config import Config
from src.core.loader import bot, BotState
from src.core.utils import logger, get_bot_username
from src.core.database import (
    delete_user, get_active_user_ids, get_total_users_count,
    log_broadcast_messages_batch
)


def perform_all_broadcast(message):
    uid = message.from_user.id
    stats = {'suc': 0, 'fail': 0, 'processed': 0}

    with BotState.lock:
        if BotState.is_broadcast_active:
            bot.reply_to(message, "⚠️ هناك إذاعة نشطة بالفعل! يرجى الانتظار حتى تنتهي.")
            return
        BotState.is_broadcast_active = True
    
    st = None
    try:
        broadcast_id = str(int(time.time() * 1000))
        st = bot.send_message(message.chat.id, "🚀 جاري بدء الإذاعة...")
        
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("👨‍💻 راسل المطور", url="https://t.me/abulharith_imad"),
            types.InlineKeyboardButton("📢 شارك البوت", url=f"https://t.me/share/url?url=https://t.me/{get_bot_username()}")
        )
        
        header_msg = "📢 <b>رسالة جديدة من الإدارة:</b>"
        content_type = message.content_type
        content_data = None
        caption = ""
        
        if content_type == 'text':
            content_data = message.text
        elif content_type in ['photo', 'video', 'document', 'audio']:
            content_data = getattr(message, content_type)[-1].file_id if content_type == 'photo' else getattr(message, content_type).file_id
            caption = message.caption or ''
        else:
            bot.edit_message_text("❌ نوع الوسائط غير مدعوم.", message.chat.id, st.message_id)
            with BotState.lock: BotState.is_broadcast_active = False
            return

        def send_wrapper(user_id):
            if not BotState.is_broadcast_active: return
            try:
                time.sleep(0.15)
                msg_obj = None
                if content_type == 'text':
                    full_text = f"{header_msg}\n\n\"{content_data}\"\n\n{Config.BOT_SIG}"
                    msg_obj = bot.send_message(int(user_id), full_text, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'photo':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                    msg_obj = bot.send_photo(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'video':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                    msg_obj = bot.send_video(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'document':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                    msg_obj = bot.send_document(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'audio':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                    msg_obj = bot.send_audio(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                stats['suc'] += 1
                return (str(user_id), str(msg_obj.message_id)) if msg_obj else None
            except telebot.apihelper.ApiTelegramException as e:
                stats['fail'] += 1
                if e.error_code in [403, 400]:
                    try: delete_user(user_id)
                    except: pass
            except Exception:
                stats['fail'] += 1
            stats['processed'] += 1

        def user_generator():
            user_ids = get_active_user_ids()
            for user_id in user_ids:
                yield user_id

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            total_estimate = get_total_users_count()

            start_time = time.time()
            last_update_time = start_time
            batch_data = []

            for user_id in user_generator():
                if not BotState.is_broadcast_active: 
                    break
                
                future = executor.submit(send_wrapper, user_id)
                futures.append(future)
                
                if len(futures) > 50:
                    done = [f for f in futures if f.done()]
                    for f in done:
                        try:
                            res = f.result()
                            if res:
                                batch_data.append((broadcast_id, res[0], res[1]))
                        except: pass
                        futures.remove(f)
                    
                    if len(batch_data) >= 200:
                        log_broadcast_messages_batch(batch_data)
                        batch_data.clear()
                
                current_time = time.time()
                if (current_time - last_update_time >= 2) or (stats['processed'] > 0 and stats['processed'] % 20 == 0):
                    try:
                        perc = (stats['processed'] / total_estimate * 100) if total_estimate > 0 else 0
                        bar = "▰" * int(perc / 10) + "▱" * (10 - int(perc / 10))
                        
                        elapsed = current_time - start_time
                        if stats['processed'] > 0:
                            avg_time = elapsed / stats['processed']
                            remaining = (total_estimate - stats['processed']) * avg_time
                            rem_text = f"⏳ المتبقي: {int(remaining)} ثانية"
                        else:
                            rem_text = "⏳ جاري الحساب..."

                        markup_cancel = types.InlineKeyboardMarkup()
                        markup_cancel.add(types.InlineKeyboardButton("❌ إلغاء البث فوراً", callback_data="cancel_broadcast"))

                        bot.edit_message_text(
                            f"🚀 <b>جاري النشر الجماعي...</b>\n\n"
                            f"{bar} {perc:.1f}%\n"
                            f"✅ ناجح: {stats['suc']}\n"
                            f"❌ فاشل: {stats['fail']}\n"
                            f"📊 المعالجة: {stats['processed']}/{total_estimate}\n"
                            f"{rem_text}",
                            message.chat.id, st.message_id, parse_mode="HTML", reply_markup=markup_cancel
                        )
                        last_update_time = current_time
                    except: pass
            
            for f in as_completed(futures):
                try:
                    res = f.result()
                    if res:
                        batch_data.append((broadcast_id, res[0], res[1]))
                except: pass
                
            if batch_data:
                log_broadcast_messages_batch(batch_data)
    
    except Exception as e:
        logger.error(f"Broadcast Error: {e}")
        try: bot.send_message(message.chat.id, f"❌ تعذر إكمال الإذاعة بسبب خطأ: {e}")
        except: pass
    
    finally:
        is_cancelled = not BotState.is_broadcast_active
        with BotState.lock:
            BotState.is_broadcast_active = False

        from src.core.database import delete_broadcast_messages_db
        markup_final = types.InlineKeyboardMarkup()
        markup_final.row(
            types.InlineKeyboardButton("✏️ تعديل الإذاعة", callback_data=f"edit_broadcast_start|{broadcast_id}"),
            types.InlineKeyboardButton("🗑 حذف الإذاعة", callback_data=f"delete_broadcast|{broadcast_id}")
        )
        
        status_text = "✅ <b>تم الانتهاء!</b>" if not is_cancelled else "⚠️ <b>تم إلغاء البث يدوياً!</b>"
        final_msg = (f"{status_text}\n\n"
                     f"✅ ناجح: {stats['suc']}\n"
                     f"❌ فاشل: {stats['fail']}\n"
                     f"📊 الإجمالي: {stats['processed']}/{total_estimate}")
        
        if st:
            try: bot.edit_message_text(final_msg, message.chat.id, st.message_id, parse_mode="HTML", reply_markup=markup_final)
            except: bot.send_message(message.chat.id, final_msg, parse_mode="HTML", reply_markup=markup_final)
        else:
            try: bot.send_message(message.chat.id, final_msg, parse_mode="HTML", reply_markup=markup_final)
            except: pass

def perform_specific_broadcast(message, target_user_id):
    if message.text == '/cancel':
        bot.send_message(message.chat.id, "❌ تم الإلغاء")
        return
        
    from src.core.database import check_user_exists
    if not check_user_exists(target_user_id):
        bot.reply_to(message, f"❌ المستخدم <code>{target_user_id}</code> غير موجود في قاعدة البيانات.", parse_mode="HTML")
        return

    try:
        content_type = message.content_type
        content_data = None
        caption = message.caption
        
        header_msg = "📢 <b>رسالة جديدة من الإدارة:</b>"
        
        if content_type == 'text':
            content_data = message.text
            full_text = f"{header_msg}\n\n\"{content_data}\"\n\n{Config.BOT_SIG}"
        elif content_type == 'photo':
            content_data = message.photo[-1].file_id
        elif content_type == 'video':
            content_data = message.video.file_id
        elif content_type == 'document':
            content_data = message.document.file_id
        elif content_type == 'audio':
            content_data = message.audio.file_id
            
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🗑 إخفاء", callback_data="delete_me"))
        
        try:
            if content_type == 'text':
                bot.send_message(int(target_user_id), full_text, parse_mode="HTML", reply_markup=markup)
            elif content_type == 'photo':
                full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                bot.send_photo(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
            elif content_type == 'video':
                full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                bot.send_video(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
            elif content_type == 'document':
                full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                bot.send_document(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
            elif content_type == 'audio':
                full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                bot.send_audio(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                
            bot.reply_to(message, f"✅ تم الإرسال بنجاح للمستخدم: <code>{target_user_id}</code>", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Specific Broadcast Send Error to {target_user_id}: {e}")
            bot.reply_to(message, "❌ تعذر إرسال الرسالة إلى هذا المستخدم.")
            
    except Exception as e:
        logger.error(f"Specific Broadcast Error: {e}")
        bot.reply_to(message, "❌ تعذر تجهيز رسالة الإذاعة لهذا المستخدم.")
